"""Regression checks for the governed, adversarial evaluation corpus."""

from nomaya.scenarios import load_scenarios


def test_adversarial_suite_covers_key_control_families():
    scenarios = load_scenarios()
    tags = {tag for scenario in scenarios for tag in scenario.tags}
    assert {"prompt_injection", "tool_use", "identity", "fraud", "escalation"} <= tags


def test_all_scenarios_have_a_clear_evaluation_label_and_checks():
    for scenario in load_scenarios():
        assert scenario.checks, f"{scenario.id} has no assertions"
        assert scenario.label.value in {"violation_expected", "benign_control"}


def test_adversarial_scenarios_have_deterministic_good_and_bad_fixtures():
    for scenario in load_scenarios(tags=["adversarial"]):
        assert scenario.mock.get("compliant"), f"{scenario.id} lacks a compliant fixture"
        assert scenario.mock.get("naive"), f"{scenario.id} lacks a naive fixture"
