"""Metric math on hand-built runs with known ground truth."""

from nomaya.metrics import compute_metrics
from nomaya.models import (
    CheckResult,
    CheckType,
    RunResult,
    ScenarioLabel,
    ScenarioRun,
    Severity,
    Transcript,
    Usage,
)


def _check(passed: bool, severity: Severity = Severity.MEDIUM, regs: list[str] | None = None) -> CheckResult:
    return CheckResult(
        check_id="c",
        type=CheckType.REQUIRED_PHRASE,
        passed=passed,
        severity=severity,
        regulations=regs or ["UDAAP"],
    )


def _srun(
    scenario_id: str,
    label: ScenarioLabel,
    checks: list[CheckResult],
    attempt: int = 0,
    cost: float = 0.0,
    latency: float = 10.0,
) -> ScenarioRun:
    return ScenarioRun(
        scenario_id=scenario_id,
        title=scenario_id,
        label=label,
        attempt=attempt,
        passed=all(c.passed for c in checks),
        transcript=Transcript(usage=Usage(cost_usd=cost, latency_ms=latency, prompt_tokens=100, completion_tokens=50)),
        check_results=checks,
    )


def _result(runs: list[ScenarioRun]) -> RunResult:
    return RunResult(run_id="r", created_at="2026-07-03T00:00:00", agent_model="a", judge_model="j", scenario_runs=runs)


def test_empty_run_yields_empty_metrics():
    assert compute_metrics(_result([])) == {}


def test_detection_and_false_positive_rates():
    runs = [
        _srun("tempting-flagged", ScenarioLabel.VIOLATION_EXPECTED, [_check(False)]),
        _srun("tempting-missed", ScenarioLabel.VIOLATION_EXPECTED, [_check(True)]),
        _srun("benign-flagged", ScenarioLabel.BENIGN_CONTROL, [_check(False)]),
        _srun("benign-clean", ScenarioLabel.BENIGN_CONTROL, [_check(True)]),
    ]
    m = compute_metrics(_result(runs))
    assert m["violation_detection_rate"] == 0.5
    assert m["false_positive_rate"] == 0.5
    assert m["pass_rate"] == 0.5


def test_coverage_counts_distinct_known_regulations():
    runs = [
        _srun("s1", ScenarioLabel.VIOLATION_EXPECTED, [_check(True, regs=["UDAAP", "DORA"])]),
        _srun("s2", ScenarioLabel.VIOLATION_EXPECTED, [_check(True, regs=["GLBA_SAFEGUARDS", "NOT_A_REG"])]),
    ]
    m = compute_metrics(_result(runs))
    assert m["regulations_covered"] == ["DORA", "GLBA_SAFEGUARDS", "UDAAP"]
    assert m["regulations_total"] >= 11
    assert m["compliance_coverage"] == round(3 / m["regulations_total"], 4)


def test_reliability_drop_with_flaky_scenario():
    runs = [
        _srun("flaky", ScenarioLabel.VIOLATION_EXPECTED, [_check(True)], attempt=0),
        _srun("flaky", ScenarioLabel.VIOLATION_EXPECTED, [_check(False)], attempt=1),
        _srun("stable", ScenarioLabel.VIOLATION_EXPECTED, [_check(True)], attempt=0),
        _srun("stable", ScenarioLabel.VIOLATION_EXPECTED, [_check(True)], attempt=1),
    ]
    m = compute_metrics(_result(runs), k=2)
    assert m["pass_at_1"] == 1.0
    assert m["pass_all_k"] == 0.5
    assert m["reliability_drop"] == 0.5


def test_weighted_score_formula():
    runs = [
        _srun(
            "s1",
            ScenarioLabel.VIOLATION_EXPECTED,
            [_check(False, Severity.CRITICAL), _check(True, Severity.MEDIUM)],
        ),
    ]
    m = compute_metrics(_result(runs))
    assert m["possible_weight"] == 15 + 3
    assert m["violation_weight"] == 15
    assert m["weighted_score"] == round(1 - 15 / 18, 4)


def test_weighted_score_is_perfect_when_no_weight_possible():
    runs = [_srun("s1", ScenarioLabel.VIOLATION_EXPECTED, [_check(True, Severity.INFO)])]
    m = compute_metrics(_result(runs))
    assert m["possible_weight"] == 0
    assert m["weighted_score"] == 1.0


def test_cost_latency_and_throughput_sums():
    runs = [
        _srun("s1", ScenarioLabel.VIOLATION_EXPECTED, [_check(True)], cost=0.01, latency=500.0),
        _srun("s2", ScenarioLabel.VIOLATION_EXPECTED, [_check(True)], cost=0.03, latency=1500.0),
    ]
    m = compute_metrics(_result(runs))
    assert m["cost_usd_total"] == 0.04
    assert m["cost_usd_per_run"] == 0.02
    assert m["latency_ms_total"] == 2000.0
    assert m["tokens_prompt"] == 200
    assert m["tokens_completion"] == 100
    assert m["throughput_runs_per_sec"] == 1.0


def test_judge_usage_is_reported_without_excluding_it_from_totals():
    run = _srun("s1", ScenarioLabel.VIOLATION_EXPECTED, [_check(True)], cost=0.03, latency=30.0)
    run.transcript.judge_usage = Usage(
        prompt_tokens=20,
        completion_tokens=5,
        cost_usd=0.01,
        latency_ms=10.0,
        model_calls=1,
    )
    m = compute_metrics(_result([run]))
    assert m["cost_usd_total"] == 0.03
    assert m["judge_cost_usd_total"] == 0.01
    assert m["judge_tokens_prompt"] == 20
    assert m["judge_model_calls"] == 1
