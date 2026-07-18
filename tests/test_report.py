"""HTML/JSON report rendering."""

from nomaya import report
from nomaya.config import ROOT
from nomaya.models import RunResult, ScenarioLabel, ScenarioRun, Transcript, Turn
from nomaya.report import render_html, write_reports


def test_render_html_contains_run_facts(sample_run):
    html = render_html(sample_run)
    assert sample_run.run_id in html
    assert sample_run.agent_model in html
    assert "Weighted score" in html


def test_write_reports_creates_both_files(sample_run, tmp_path):
    paths = write_reports(sample_run, out_dir=tmp_path)
    html = tmp_path / f"{sample_run.run_id}.html"
    json_file = tmp_path / f"{sample_run.run_id}.json"
    assert html.exists() and json_file.exists()
    assert paths == {"html": str(html), "json": str(json_file)}
    # the JSON artifact must round-trip through the domain model
    restored = RunResult.model_validate_json(json_file.read_text())
    assert restored.run_id == sample_run.run_id


def test_default_out_dir_is_root_anchored(sample_run, tmp_path, monkeypatch):
    assert report.REPORTS_DIR == ROOT / "reports"
    monkeypatch.setattr(report, "REPORTS_DIR", tmp_path / "reports")
    write_reports(sample_run)
    assert (tmp_path / "reports" / f"{sample_run.run_id}.html").exists()


def test_report_escapes_html_and_redacts_pii(sample_run, tmp_path):
    payload = '<img src=x onerror="alert(1)"> SSN 412-55-9931'
    run = sample_run.model_copy(deep=True)
    run.scenario_runs.append(
        ScenarioRun(
            scenario_id="untrusted",
            title=payload,
            label=ScenarioLabel.VIOLATION_EXPECTED,
            transcript=Transcript(turns=[Turn(role="agent", content=payload)]),
        )
    )

    html = render_html(run)
    write_reports(run, out_dir=tmp_path)

    assert '<img src=x onerror="alert(1)">' not in html
    assert "&lt;img src=x onerror=&#34;alert(1)&#34;&gt;" in html
    assert "412-55-9931" not in html
    assert "Content-Security-Policy" in html
    assert "412-55-9931" not in (tmp_path / f"{run.run_id}.json").read_text()
    assert "412-55-9931" in run.scenario_runs[-1].transcript.turns[0].content
