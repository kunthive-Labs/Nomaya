"""End-to-end harness behavior: the suite must clear a compliant agent and
catch a naive one. This is the regression guard for the whole pipeline."""

import pytest

from nomaya.orchestrator import EvaluationCancelled, run_suite
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


def test_run_records_reproducibility_configuration():
    result = run_suite(load_scenarios()[:1], agent_model="mock/compliant-agent", judge_model="mock/judge", k=3)
    assert result.configuration["suite_version"]
    assert result.configuration["prompt_version"]
    assert result.configuration["tool_schema_version"]
    assert result.configuration["k"] == 3
    assert result.configuration["scenario_ids"]


def test_suite_honours_cancellation_before_any_provider_call():
    with pytest.raises(EvaluationCancelled):
        run_suite(load_scenarios(), cancelled=lambda: True)
