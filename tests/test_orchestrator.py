"""End-to-end harness behavior: the suite must clear a compliant agent and
catch a naive one. This is the regression guard for the whole pipeline."""

from nomaya.orchestrator import run_suite
from nomaya.scenarios import load_scenarios


def test_compliant_agent_passes_clean():
    scenarios = load_scenarios()
    result = run_suite(scenarios, agent_model="mock/compliant-agent", judge_model="mock/judge")
    m = result.metrics
    assert m["pass_rate"] == 1.0, "compliant agent should pass every scenario"
    assert m["false_positive_rate"] == 0.0, "compliant agent must not be falsely flagged"
    assert m["total_violations"] == 0


def test_naive_agent_is_caught():
    scenarios = load_scenarios()
    result = run_suite(scenarios, agent_model="mock/naive-agent", judge_model="mock/judge")
    m = result.metrics
    assert m["violation_detection_rate"] == 1.0, "every tempting scenario should be flagged"
    assert m["total_violations"] > 0
    # benign controls should still pass even for the naive agent -> no false positives
    assert m["false_positive_rate"] == 0.0


def test_coverage_and_reliability_fields_present():
    scenarios = load_scenarios()
    result = run_suite(scenarios, agent_model="mock/compliant-agent", k=3)
    m = result.metrics
    assert 0.0 <= m["compliance_coverage"] <= 1.0
    assert m["k"] == 3
    assert m["pass_all_k"] == m["pass_at_1"]  # deterministic mock -> no reliability drop
