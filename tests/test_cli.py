"""CLI behavior via Typer's CliRunner (mock mode only — no network)."""

from typer.testing import CliRunner

from nomaya.cli import app

runner = CliRunner()


def test_run_compliant_passes_gates(tmp_db):
    result = runner.invoke(
        app,
        [
            "run",
            "--agent",
            "mock/compliant-agent",
            "--fail-under",
            "1.0",
            "--fail-under-weighted",
            "1.0",
            "--no-report",
            "--no-save",
        ],
    )
    assert result.exit_code == 0
    assert "Weighted score" in result.output


def test_run_naive_fails_pass_rate_gate(tmp_db):
    result = runner.invoke(
        app,
        ["run", "--agent", "mock/naive-agent", "--fail-under", "1.0", "--no-report", "--no-save"],
    )
    assert result.exit_code == 1


def test_run_naive_fails_weighted_gate(tmp_db):
    result = runner.invoke(
        app,
        ["run", "--agent", "mock/naive-agent", "--fail-under-weighted", "0.5", "--no-report", "--no-save"],
    )
    assert result.exit_code == 1


def test_run_with_unknown_tag_exits_nonzero(tmp_db):
    result = runner.invoke(app, ["run", "--tags", "no-such-tag", "--no-report", "--no-save"])
    assert result.exit_code == 1


def test_scenarios_lists_dora(tmp_db):
    result = runner.invoke(app, ["scenarios"])
    assert result.exit_code == 0
    # rich truncates wide cells, so match a prefix rather than the full id
    assert "dora_incident" in result.output


def test_regulations_lists_registry(tmp_db):
    result = runner.invoke(app, ["regulations"])
    assert result.exit_code == 0
    assert "DORA" in result.output


def test_list_empty_then_populated(tmp_db):
    assert "No runs yet" in runner.invoke(app, ["list"]).output
    save = runner.invoke(app, ["run", "--agent", "mock/compliant-agent", "--tags", "privacy", "--no-report"])
    assert save.exit_code == 0
    listed = runner.invoke(app, ["list"])
    assert listed.exit_code == 0
    assert "Run history" in listed.output
    assert "No runs yet" not in listed.output


def test_show_unknown_run_exits_nonzero(tmp_db):
    result = runner.invoke(app, ["show", "no-such-run"])
    assert result.exit_code == 1
