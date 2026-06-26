"""Scenario playbook and regulation registry loaders."""

from nomaya.regulations import get_regulation, load_registry
from nomaya.scenarios import load_scenarios


def test_loads_all_playbooks_sorted():
    scenarios = load_scenarios()
    assert len(scenarios) == 11
    ids = [s.id for s in scenarios]
    assert ids[0] == "loan_early_payoff"  # files load in sorted filename order
    assert "dora_incident_communication" in ids


def test_tag_filter():
    assert len(load_scenarios(tags=["dora"])) == 1
    assert load_scenarios(tags=["no-such-tag"]) == []
    assert len(load_scenarios(tags=["core"])) >= 1


def test_registry_has_eleven_regulations():
    registry = load_registry()
    assert len(registry) == 11
    assert "DORA" in registry


def test_get_regulation_falls_back_for_unknown_id():
    reg = get_regulation("MADE_UP")
    assert reg.id == "MADE_UP" and reg.name == "MADE_UP"


def test_every_referenced_regulation_exists_in_registry():
    """Cross-reference integrity: playbooks must only cite registered regulations."""
    registry = set(load_registry())
    for scenario in load_scenarios():
        unknown = set(scenario.regulations) - registry
        assert not unknown, f"{scenario.id} cites unregistered regulations: {unknown}"
        for check in scenario.checks:
            unknown = set(check.regulations) - registry
            assert not unknown, f"{scenario.id}/{check.id} cites unregistered regulations: {unknown}"


def test_every_regulation_is_exercised_by_some_check():
    """Keeps compliance coverage honest — no registry entry may go unreferenced."""
    referenced: set[str] = set()
    for scenario in load_scenarios():
        for check in scenario.checks:
            referenced.update(check.regulations)
    unreferenced = set(load_registry()) - referenced
    assert not unreferenced, f"regulations with no covering check: {unreferenced}"
