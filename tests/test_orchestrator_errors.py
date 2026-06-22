"""Resilience: a failing scenario is isolated as an errored run; the suite still
completes, and a transient provider error is retried rather than fatal."""

from __future__ import annotations

from nomaya.orchestrator import run_suite
from nomaya.scenarios import load_scenarios


def test_one_failing_scenario_does_not_abort_the_suite(monkeypatch):
    scenarios = load_scenarios()[:3]
    target = scenarios[1].id

    # Make exactly one scenario blow up inside the runner.
    import nomaya.orchestrator as orch
    real_run_scenario = orch.run_scenario

    def boom(scenario, agent, judge, attempt=0):
        if scenario.id == target:
            raise RuntimeError("simulated provider meltdown")
        return real_run_scenario(scenario, agent, judge, attempt=attempt)

    monkeypatch.setattr(orch, "run_scenario", boom)

    result = run_suite(scenarios, agent_model="mock/compliant-agent", judge_model="mock/judge")

    assert len(result.scenario_runs) == 3, "every scenario still produces a run"
    errored = [r for r in result.scenario_runs if r.error]
    assert len(errored) == 1
    assert errored[0].scenario_id == target
    assert errored[0].passed is False
    assert "meltdown" in errored[0].error


def test_errored_run_counts_as_failure_in_metrics(monkeypatch):
    scenarios = load_scenarios()[:2]
    import nomaya.orchestrator as orch

    monkeypatch.setattr(
        orch, "run_scenario",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")),
    )
    result = run_suite(scenarios, agent_model="mock/compliant-agent")
    assert result.metrics["pass_rate"] == 0.0
    assert all(r.error for r in result.scenario_runs)
