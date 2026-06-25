"""Metrics edge cases — empty suites and no division-by-zero."""

from __future__ import annotations

from nomaya.metrics import compute_metrics
from nomaya.models import RunResult
from nomaya.orchestrator import run_suite
from nomaya.scenarios import load_scenarios


def test_empty_run_yields_empty_metrics():
    run = RunResult(run_id="r", created_at="t", agent_model="mock/x", judge_model="mock/j")
    assert compute_metrics(run) == {}


def test_metrics_are_bounded_and_present():
    run = run_suite(load_scenarios(), agent_model="mock/compliant-agent", judge_model="mock/judge")
    m = run.metrics
    for key in ("pass_rate", "violation_detection_rate", "false_positive_rate", "compliance_coverage"):
        assert 0.0 <= m[key] <= 1.0
    assert m["cost_usd_per_run"] >= 0.0
    assert m["throughput_runs_per_sec"] >= 0.0  # no div-by-zero even with ~0 latency


def test_pass_at_k_gap_is_zero_for_deterministic_mock():
    run = run_suite(load_scenarios(), agent_model="mock/compliant-agent", k=4)
    m = run.metrics
    assert m["k"] == 4
    assert m["reliability_drop"] == 0.0
    assert m["pass_all_k"] == m["pass_at_1"]
