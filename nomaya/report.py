"""Reporting — render a RunResult to JSON and a standalone HTML report.

The HTML report is self-contained (inline CSS) so it can be attached to a CI run
or emailed to a compliance reviewer without a server.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, select_autoescape

from .config import REPORTS_DIR, settings
from .models import RunResult
from .redaction import redact_run
from .regulations import get_regulation

_HTML = Environment(autoescape=select_autoescape(default=True, default_for_string=True)).from_string(
    """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
<title>Nomaya — {{ run.run_id }}</title>
<style>
  :root { --ok:#0f9d58; --bad:#d23f31; --ink:#1a1d24; --mut:#6b7280; --line:#e6e8eb; --bg:#f7f8fa; }
  * { box-sizing:border-box; } body { font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; margin:0; color:var(--ink); background:var(--bg); }
  .wrap { max-width:1040px; margin:0 auto; padding:32px 20px 80px; }
  h1 { font-size:24px; margin:0 0 4px; } .sub { color:var(--mut); margin:0 0 24px; font-size:13px; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:28px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
  .card .k { color:var(--mut); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  .card .v { font-size:22px; font-weight:650; margin-top:4px; }
  table { width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); border-radius:12px; overflow:hidden; }
  th,td { text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); font-size:14px; vertical-align:top; }
  th { background:#fbfcfd; color:var(--mut); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.03em; }
  .pass { color:var(--ok); font-weight:650; } .fail { color:var(--bad); font-weight:650; }
  .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; background:#eef1f4; color:var(--mut); margin:1px 2px; }
  .pill.fail { background:#fdecea; color:var(--bad); }
  .ev { color:var(--mut); font-size:12px; } h2 { font-size:16px; margin:32px 0 10px; }
  .bar { height:8px; background:#eef1f4; border-radius:999px; overflow:hidden; }
  .bar > span { display:block; height:100%; background:var(--ok); }
  @media (prefers-color-scheme: dark) {
    :root { --ink:#f7f8fa; --mut:#9ca3af; --line:#374151; --bg:#111827; }
    .card, table { background:#1f2937; }
    th { background:#111827; }
    .pill { background:#374151; color:#f7f8fa; }
    .pill.fail { background:#7f1d1d; color:#fecaca; }
  }
</style></head><body><div class="wrap">
  <h1>Nomaya — Finance Compliance Agent Evaluation</h1>
  <p class="sub">Run <b>{{ run.run_id }}</b> · agent <b>{{ run.agent_model }}</b> · judge <b>{{ run.judge_model }}</b> · {{ run.created_at }}</p>

  <div class="cards">
    <div class="card"><div class="k">Pass rate</div><div class="v">{{ (m.pass_rate*100)|round(1) }}%</div>
      <div class="bar"><span style="width:{{ (m.pass_rate*100)|round(1) }}%"></span></div></div>
    <div class="card"><div class="k">Detection rate</div><div class="v">{{ (m.violation_detection_rate*100)|round(1) }}%</div></div>
    <div class="card"><div class="k">False positives</div><div class="v">{{ (m.false_positive_rate*100)|round(1) }}%</div></div>
    <div class="card"><div class="k">Weighted score</div><div class="v">{{ (m.get('weighted_score', 1)*100)|round(1) }}%</div>
      <div class="ev">violation weight {{ m.get('violation_weight', 0) }}/{{ m.get('possible_weight', 0) }}</div></div>
    <div class="card"><div class="k">Coverage</div><div class="v">{{ (m.compliance_coverage*100)|round(0) }}%</div>
      <div class="ev">{{ m.regulations_covered|length }}/{{ m.regulations_total }} regs</div></div>
    <div class="card"><div class="k">pass@k → reliability</div><div class="v">{{ (m.pass_all_k*100)|round(0) }}%</div>
      <div class="ev">drop {{ (m.reliability_drop*100)|round(0) }}pts (k={{ m.k }})</div></div>
    <div class="card"><div class="k">Cost / run</div><div class="v">${{ '%.4f'|format(m.cost_usd_per_run) }}</div>
      <div class="ev">{{ m.throughput_runs_per_sec }} runs/s</div></div>
  </div>

  {% if m.violations_by_regulation %}
  <h2>Violations by regulation</h2>
  <table><thead><tr><th>Regulation</th><th>Authority</th><th>Count</th></tr></thead><tbody>
  {% for reg, n in m.violations_by_regulation.items() %}
    <tr><td><b>{{ reg_name(reg) }}</b></td><td class="ev">{{ reg_auth(reg) }}</td><td class="fail">{{ n }}</td></tr>
  {% endfor %}
  </tbody></table>
  {% endif %}

  <h2>Scenario results</h2>
  <table><thead><tr><th>Scenario</th><th>Label</th><th>Result</th><th>Checks</th></tr></thead><tbody>
  {% for s in run.scenario_runs %}
    <tr>
      <td><b>{{ s.title }}</b><div class="ev">{{ s.scenario_id }}{% if m.k > 1 %} · attempt {{ s.attempt+1 }}{% endif %}</div></td>
      <td class="ev">{{ s.label.value }}</td>
      <td class="{{ 'pass' if s.passed else 'fail' }}">{{ 'PASS' if s.passed else 'FAIL' }}</td>
      <td>{% for c in s.check_results %}<span class="pill {{ '' if c.passed else 'fail' }}" title="{{ c.message }} {{ c.evidence }}">{{ c.check_id }} {{ '✓' if c.passed else '✕' }}</span>{% endfor %}</td>
    </tr>
  {% endfor %}
  </tbody></table>
</div></body></html>"""
)


def _report_run(run: RunResult) -> RunResult:
    return redact_run(run) if settings.storage_redact_pii else run


def render_html(run: RunResult) -> str:
    """Render a report from a safe copy; the in-memory run is never modified."""
    run = _report_run(run)
    return _HTML.render(
        run=run,
        m=run.metrics,
        reg_name=lambda r: get_regulation(r).name,
        reg_auth=lambda r: get_regulation(r).authority,
    )


def write_reports(run: RunResult, out_dir: str | Path | None = None) -> dict[str, str]:
    """Write redacted-by-default, standalone report artifacts."""
    run = _report_run(run)
    out = Path(out_dir) if out_dir is not None else REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    html_path = out / f"{run.run_id}.html"
    json_path = out / f"{run.run_id}.json"
    html_path.write_text(render_html(run))
    json_path.write_text(run.model_dump_json(indent=2))
    return {"html": str(html_path), "json": str(json_path)}
