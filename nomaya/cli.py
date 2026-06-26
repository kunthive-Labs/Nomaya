"""Nomaya command-line interface.

nomaya run            # evaluate the suite against the configured agent
nomaya scenarios      # list available scenario playbooks
nomaya regulations    # list the regulation registry
nomaya list           # list past runs
nomaya show <run_id>  # show metrics for a run
nomaya serve          # start the dashboard API
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from . import store
from .config import settings
from .orchestrator import run_suite
from .report import write_reports
from .scenarios import load_scenarios

app = typer.Typer(add_completion=False, help="Nomaya — finance compliance agent evaluation suite.")
console = Console()


@app.command()
def run(
    agent: str = typer.Option(None, help="Agent-under-test model (LiteLLM string or mock/...)."),
    judge: str = typer.Option(None, help="LLM-judge model."),
    k: int = typer.Option(1, help="Attempts per scenario (for pass@k reliability)."),
    tags: str = typer.Option(None, help="Comma-separated tag filter."),
    report: bool = typer.Option(True, help="Write HTML + JSON reports."),
    save: bool = typer.Option(True, help="Persist the run to the SQLite history."),
    fail_under: float = typer.Option(0.0, help="Exit non-zero if pass rate is below this (for CI gating)."),
    fail_under_weighted: float = typer.Option(
        0.0, help="Exit non-zero if the severity-weighted compliance score is below this."
    ),
):
    """Evaluate the scenario suite against an agent."""
    agent = agent or settings.agent_model
    judge = judge or settings.judge_model
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    scenarios = load_scenarios(tags=tag_list)
    if not scenarios:
        console.print("[red]No scenarios found.[/red]")
        raise typer.Exit(1)

    console.print(
        f"Running [bold]{len(scenarios)}[/bold] scenarios × k={k} "
        f"· agent=[cyan]{agent}[/cyan] judge=[cyan]{judge}[/cyan]"
    )
    result = run_suite(scenarios, agent_model=agent, judge_model=judge, k=k)
    m = result.metrics

    _metrics_table(m)

    table = Table(title="Scenario results", show_lines=False)
    table.add_column("Scenario")
    table.add_column("Label")
    table.add_column("Result")
    table.add_column("Failed checks")
    for s in result.scenario_runs:
        failed = ", ".join(c.check_id for c in s.violations) or "—"
        res = "[green]PASS[/green]" if s.passed else "[red]FAIL[/red]"
        table.add_row(s.scenario_id, s.label.value, res, failed)
    console.print(table)

    if save:
        store.save_run(result)
        console.print(f"Saved run [bold]{result.run_id}[/bold] to {settings.db_path}")
    if report:
        paths = write_reports(result)
        console.print(f"Report: [link]{paths['html']}[/link]")

    if fail_under and m.get("pass_rate", 0) < fail_under:
        console.print(f"[red]Pass rate {m['pass_rate']:.2%} < gate {fail_under:.2%}[/red]")
        raise typer.Exit(1)
    if fail_under_weighted and m.get("weighted_score", 0) < fail_under_weighted:
        console.print(f"[red]Weighted score {m['weighted_score']:.2%} < gate {fail_under_weighted:.2%}[/red]")
        raise typer.Exit(1)


def _metrics_table(m: dict) -> None:
    t = Table(title="Metrics")
    t.add_column("Metric")
    t.add_column("Value", justify="right")
    t.add_row("Pass rate", f"{m.get('pass_rate', 0):.1%}")
    t.add_row("Violation detection rate", f"{m.get('violation_detection_rate', 0):.1%}")
    t.add_row("False-positive rate", f"{m.get('false_positive_rate', 0):.1%}")
    t.add_row(
        "Compliance coverage",
        f"{m.get('compliance_coverage', 0):.0%} "
        f"({len(m.get('regulations_covered', []))}/{m.get('regulations_total', 0)})",
    )
    t.add_row("pass@1 / pass@k", f"{m.get('pass_at_1', 0):.0%} / {m.get('pass_all_k', 0):.0%}")
    t.add_row("Reliability drop", f"{m.get('reliability_drop', 0):.0%}")
    t.add_row("Total violations", str(m.get("total_violations", 0)))
    t.add_row(
        "Weighted score",
        f"{m.get('weighted_score', 1):.1%} (weight {m.get('violation_weight', 0)}/{m.get('possible_weight', 0)})",
    )
    t.add_row("Cost / run", f"${m.get('cost_usd_per_run', 0):.4f}")
    t.add_row("Throughput", f"{m.get('throughput_runs_per_sec', 0)} runs/s")
    console.print(t)


@app.command()
def scenarios():
    """List available scenario playbooks."""
    t = Table(title="Scenarios")
    t.add_column("ID")
    t.add_column("Title")
    t.add_column("Label")
    t.add_column("Regulations")
    for s in load_scenarios():
        t.add_row(s.id, s.title, s.label.value, ", ".join(s.regulations))
    console.print(t)


@app.command()
def regulations():
    """List the regulation registry."""
    from .regulations import load_registry

    t = Table(title="Regulation registry")
    t.add_column("ID")
    t.add_column("Name")
    t.add_column("Authority")
    for reg in load_registry().values():
        t.add_row(reg.id, reg.name, reg.authority)
    console.print(t)


@app.command(name="list")
def list_runs(limit: int = 20):
    """List past runs."""
    rows = store.list_runs(limit=limit)
    if not rows:
        console.print("No runs yet. Try [bold]nomaya run[/bold].")
        return
    t = Table(title="Run history")
    t.add_column("Run ID")
    t.add_column("When")
    t.add_column("Agent")
    t.add_column("Pass rate", justify="right")
    t.add_column("Violations", justify="right")
    for r in rows:
        pr = f"{r['pass_rate']:.0%}" if r["pass_rate"] is not None else "—"
        t.add_row(r["run_id"], r["created_at"][:19], r["agent_model"], pr, str(r["violations"]))
    console.print(t)


@app.command()
def show(run_id: str):
    """Show metrics for a stored run."""
    run = store.get_run(run_id)
    if not run:
        console.print(f"[red]Run {run_id} not found.[/red]")
        raise typer.Exit(1)
    _metrics_table(run.metrics)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Start the dashboard API server."""
    import uvicorn

    uvicorn.run("nomaya.api:api", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
