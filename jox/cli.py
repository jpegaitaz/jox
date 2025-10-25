# jox/cli.py
from __future__ import annotations

import os
import asyncio
from typing import Optional
import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

from dotenv import load_dotenv
load_dotenv()  # load .env early

from jox.utils.logging import setup_logger
from jox.settings import SETTINGS
from jox.cv.parse import parse_cv
from jox.orchestrator.memory import add_entry, load_entries
from jox.workflows.quick_and_ready import run_quick_and_ready

app = typer.Typer(add_completion=False)
console = Console()


def _print_ai_guard_banner(ai_target: Optional[int], ai_max_iters: Optional[int]) -> None:
    console.print()
    console.print(
        "[bold white on blue]  AI-GUARD ENABLED  [/bold white on blue]  "
        f"[dim]target={ai_target if ai_target is not None else '—'}%"
        f", max-iters={ai_max_iters if ai_max_iters is not None else '—'}[/dim]"
    )
    console.print(
        "[dim]We’ll try to reduce AI-likeness on generated CV/CL text using iterative humanization passes.[/dim]"
    )
    console.print()


def _render_ai_guard_summary(traces: list[dict]) -> None:
    if not traces:
        console.print("[dim]AI-Guard: no trace data returned.[/dim]")
        return

    table = Table(title="AI-Guard Optimization Summary", show_lines=False)
    table.add_column("Job Title", style="bold", overflow="fold", ratio=3)
    table.add_column("Company", overflow="fold", ratio=2)
    table.add_column("Part", justify="center")
    table.add_column("Baseline → Final", justify="center")
    table.add_column("Iters", justify="right")

    def _rows_for(section: dict[str, any], part_label: str):
        # section is like {"label": "...", "target": 35, "max_iters": 4, "runs": [{"iter":0,"score":...}, ...]}
        runs = section.get("runs") or []
        if not runs:
            return "—", "—"
        baseline = runs[0].get("score", "—")
        final = runs[-1].get("score", "—")
        iters = runs[-1].get("iter", 0)
        arrow = "→"
        score_str = f"{baseline:.1f}% {arrow} {final:.1f}%" if isinstance(baseline, (int, float)) and isinstance(final, (int, float)) else "—"
        return score_str, str(iters)

    for item in traces:
        title = item.get("title") or "—"
        company = item.get("company") or "—"
        guard = item.get("ai_guard") or {}
        cv_logs: dict = guard.get("cv") or {}
        cl_logs: dict = guard.get("cover_letter") or {}

        # CV fields (collapse to one representative row if we have many)
        cv_parts = [("CV:" + k, v) for k, v in cv_logs.items()]
        if cv_parts:
            # show the most informative: the one with the largest delta
            deltas = []
            for label, sec in cv_parts:
                runs = (sec or {}).get("runs") or []
                if len(runs) >= 2 and isinstance(runs[0].get("score"), (int, float)) and isinstance(runs[-1].get("score"), (int, float)):
                    deltas.append((abs(runs[-1]["score"] - runs[0]["score"]), label, sec))
            if deltas:
                _, best_label, best_sec = sorted(deltas, key=lambda x: x[0], reverse=True)[0]
                score_str, iters = _rows_for(best_sec, best_label)
                table.add_row(title, company, best_label, score_str, iters)

        # Cover Letter fields
        cl_parts = [("CL:" + k, v) for k, v in cl_logs.items()]
        if cl_parts:
            deltas = []
            for label, sec in cl_parts:
                runs = (sec or {}).get("runs") or []
                if len(runs) >= 2 and isinstance(runs[0].get("score"), (int, float)) and isinstance(runs[-1].get("score"), (int, float)):
                    deltas.append((abs(runs[-1]["score"] - runs[0]["score"]), label, sec))
            if deltas:
                _, best_label, best_sec = sorted(deltas, key=lambda x: x[0], reverse=True)[0]
                score_str, iters = _rows_for(best_sec, best_label)
                table.add_row(title, company, best_label, score_str, iters)

    console.print()
    console.print(table)
    console.print()


@app.command()
def main(
    workflow: Optional[str] = typer.Option(None, help="Workflow to run (quick-and-ready)"),
    ai_target: Optional[int] = typer.Option(
        None,
        help="Target maximum AI-likeness percentage for optimization (e.g., 35).",
    ),
    ai_max_iters: Optional[int] = typer.Option(
        None,
        help="Maximum optimization iterations to reduce AI-likeness (e.g., 4).",
    ),
):
    # Be defensive: some old configs may not define log_json
    setup_logger(SETTINGS.log_level, getattr(SETTINGS, "log_json", False))
    console.print("[bold cyan]Welcome to JOX[/bold cyan]")

    # First connection prompt to create an entry
    entries = load_entries()
    if not entries:
        if Confirm.ask("Create your first memory entry now?", default=True):
            topic = Prompt.ask("Entry Topic")
            desc = Prompt.ask("Entry Description")
            add_entry(topic, desc)
            console.print("[green]Entry saved.[/green]")

    # UX flow 1: Upload CV
    cv_path = Prompt.ask("Upload CV (path to .pdf or .docx)")
    cv = parse_cv(cv_path)
    console.print(f"Detected candidate name: [bold]{cv.get('name','Unknown')}[/bold]")

    # UX flow 2: Function, Role, Location (country/city/region)
    function = Prompt.ask("Target Function (e.g., Data Science)")
    role = Prompt.ask("Target Role Title (e.g., ML Engineer)")
    country = Prompt.ask("Target Country/Location (e.g., Switzerland or Geneva)")

    # Let the user pick the job source (affects which MCP adapter is used)
    default_source = os.getenv("JOB_SOURCE", getattr(SETTINGS, "job_source", "indeed")) or "indeed"
    job_source = Prompt.ask(
        "Choose job source",
        choices=["indeed", "jobup", "jobs"],  # ← added "jobs"
        default=default_source if default_source in {"indeed","jobup","jobs"} else "indeed",
        show_choices=True,
    )
    # Apply selection for this run
    os.environ["JOB_SOURCE"] = job_source
    try:
        setattr(SETTINGS, "job_source", job_source)
    except Exception:
        pass  # SETTINGS may be frozen; env var still honored

    # Default workflow
    if not workflow:
        workflow = "quick-and-ready"

    if workflow == "quick-and-ready":
        if ai_target is not None or ai_max_iters is not None:
            _print_ai_guard_banner(ai_target, ai_max_iters)

        console.print("[yellow]Running Workflow-1: QuickAndReady ...[/yellow]")
        result = asyncio.run(
            run_quick_and_ready(
                cv,
                function,
                role,
                country,
                ai_target=ai_target,
                ai_max_iters=ai_max_iters,
            )
        )
        console.print("[green]Done.[/green]")
        console.print(f"Session Report: {result.get('report_path')}")
        console.print(f"Generated: {result.get('number_of_outputs_generated')} files.")

        # Summarize AI-Guard deltas, if any
        if ai_target is not None or ai_max_iters is not None:
            traces = result.get("ai_guard_traces") or []
            _render_ai_guard_summary(traces)
    else:
        console.print(f"[red]Unknown workflow: {workflow}[/red]")


if __name__ == "__main__":
    app()
