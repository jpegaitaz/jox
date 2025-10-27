# jox/cli.py
from __future__ import annotations

import os
import sys
import time
import asyncio
import logging
from typing import Optional, List, Dict, Any

import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme
from rich.live import Live

from dotenv import load_dotenv
load_dotenv()  # load .env early

from jox.utils.logging import setup_logger
from jox.settings import SETTINGS
from jox.cv.parse import parse_cv
from jox.orchestrator.memory import add_entry, load_entries
from jox.workflows.quick_and_ready import run_quick_and_ready

# Quiet noisy HTTP logs
logging.getLogger("httpx").setLevel(logging.WARNING)

app = typer.Typer(add_completion=False)

# -----------------------
# Rich Theme (blue + green)
# -----------------------
JOX_THEME = Theme({
    # generic
    "info": "blue",
    "success": "green",
    "warning": "yellow",
    "error": "bold red",
    # prompts
    "prompt": "bold blue",
    "prompt.choices": "blue",
    "prompt.default": "dim blue",
    # banner + ai-guard
    "banner": "bold blue",
    "ai.banner": "bold white on blue",
    # tables
    "table.title": "bold blue",
    "table.header": "green",
})
console = Console(theme=JOX_THEME)

# -----------------------
# ASCII Banner for JOX
# -----------------------
BANNER_ASCII = r"""
      ██╗ ██████╗ ██╗    ██╗
      ██║██╔═══██╗ ██║  ██╔╝
      ██║██║   ██║   ███╔╝
 ██   ██║██║   ██║ ██╔═ ██╗
 ╚█████╔╝╚██████╔╝██║    ██╗
  ╚════╝  ╚═════╝ ╚═╝    ╚═╝
  by DarkMatter

============================
Job Orchestrator eXpress
(search • score • tailor • guard)

"""

def _print_ascii_banner(console: Console) -> None:
    """Animated banner; disable with JOX_NO_BANNER=1. Speed via JOX_CPS."""
    if os.getenv("JOX_NO_BANNER", "").strip().lower() in {"1", "true", "yes"}:
        return

    text = BANNER_ASCII + "\nWelcome to JOX"
    cps = int(os.getenv("JOX_CPS", "80"))  # characters per second
    delay = 1 / max(1, cps)

    typed = ""
    with Live(console=console, refresh_per_second=60) as live:
        for ch in text:
            typed += ch
            panel = Panel(Text(typed, style="bold green"), border_style="black", padding=(0, 2))
            live.update(panel)
            time.sleep(delay)

def _prompt_memory_entries() -> None:
    """
    Always offer to add memory entries on each run.
    Non-blocking; supports adding multiple entries in a row.
    """
    try:
        existing = load_entries()
    except Exception:
        existing = []

    if existing:
        last = existing[-1] if isinstance(existing[-1], dict) else {}
        last_topic = (last.get("topic") or last.get("title") or "—") if isinstance(last, dict) else "—"
        count_str = "entry" if len(existing) == 1 else "entries"
        console.print(f"[dim]You have {len(existing)} memory {count_str} (last: {last_topic}).[/dim]")

    while Confirm.ask("Add a new memory entry now?", default=False):
        topic = Prompt.ask("Entry Topic")
        desc = Prompt.ask("Entry Description")
        try:
            add_entry(topic, desc)
            console.print("[success]Entry saved.[/success]")
        except Exception as e:
            console.print(f"[error]Could not save entry: {e}[/error]")

        if not Confirm.ask("Add another entry?", default=False):
            break

def _print_ai_guard_banner(ai_target: Optional[int], ai_max_iters: Optional[int]) -> None:
    console.print()
    console.print(
        "[ai.banner]  AI-GUARD ENABLED  [/ai.banner]  "
        f"[dim]target={ai_target if ai_target is not None else '—'}%, "
        f"max-iters={ai_max_iters if ai_max_iters is not None else '—'}[/dim]"
    )
    console.print(
        "[dim]We’ll try to reduce AI-likeness on generated CV/CL text using iterative humanization passes.[/dim]"
    )
    console.print()

def _render_ai_guard_summary(traces: List[Dict[str, Any]]) -> None:
    if not traces:
        console.print("[dim]AI-Guard: no trace data returned.[/dim]")
        return

    table = Table(
        title="AI-Guard Optimization Summary",
        show_lines=False,
        title_style="table.title",
        header_style="table.header",
    )
    table.add_column("Job Title", style="bold", overflow="fold", ratio=3)
    table.add_column("Company", overflow="fold", ratio=2)
    table.add_column("Part", justify="center")
    table.add_column("Baseline → Final", justify="center")
    table.add_column("Iters", justify="right")

    def _rows_for(section: Dict[str, Any]):
        runs = section.get("runs") or []
        if not runs:
            return "—", "—"
        baseline = runs[0].get("score", "—")
        final = runs[-1].get("score", "—")
        iters = runs[-1].get("iter", 0)
        score_str = f"{baseline:.1f}% → {final:.1f}%" if isinstance(baseline, (int, float)) and isinstance(final, (int, float)) else "—"
        return score_str, str(iters)

    for item in traces:
        title = item.get("title") or "—"
        company = item.get("company") or "—"
        guard = item.get("ai_guard") or {}
        cv_logs: Dict[str, Any] = guard.get("cv") or {}
        cl_logs: Dict[str, Any] = guard.get("cover_letter") or {}

        # CV: show the part with the largest delta (if any)
        cv_parts = [("CV:" + k, v) for k, v in cv_logs.items()]
        if cv_parts:
            deltas = []
            for label, sec in cv_parts:
                runs = (sec or {}).get("runs") or []
                if len(runs) >= 2 and isinstance(runs[0].get("score"), (int, float)) and isinstance(runs[-1].get("score"), (int, float)):
                    deltas.append((abs(runs[-1]["score"] - runs[0]["score"]), label, sec))
            if deltas:
                _, best_label, best_sec = sorted(deltas, key=lambda x: x[0], reverse=True)[0]
                score_str, iters = _rows_for(best_sec)
                table.add_row(title, company, best_label, score_str, iters)

        # Cover Letter: same idea
        cl_parts = [("CL:" + k, v) for k, v in cl_logs.items()]
        if cl_parts:
            deltas = []
            for label, sec in cl_parts:
                runs = (sec or {}).get("runs") or []
                if len(runs) >= 2 and isinstance(runs[0].get("score"), (int, float)) and isinstance(runs[-1].get("score"), (int, float)):
                    deltas.append((abs(runs[-1].get("score", 0) - runs[0].get("score", 0)), label, sec))
            if deltas:
                _, best_label, best_sec = sorted(deltas, key=lambda x: x[0], reverse=True)[0]
                score_str, iters = _rows_for(best_sec)
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

    # ASCII banner (can disable via env)
    _print_ascii_banner(console)
    console.print("")  # neat break line

    # 🔁 Always offer to add memory entries
    _prompt_memory_entries()

    # UX flow 1: Upload CV
    cv_path = Prompt.ask("Upload CV (path to .pdf or .docx)")
    cv = parse_cv(cv_path)
    console.print(f"Detected candidate name: [bold]{cv.get('name','Unknown')}[/bold]")

    # UX flow 2: Function, Role, Location
    function = Prompt.ask("Target Function (e.g., Data Science)")
    role     = Prompt.ask("Target Role Title (e.g., ML Engineer)")
    country  = Prompt.ask("Target Country/Location (e.g., Switzerland or Geneva)")

    # Job source selection
    default_source = os.getenv("JOB_SOURCE", getattr(SETTINGS, "job_source", "indeed")) or "indeed"
    if default_source not in {"indeed", "jobup", "jobs"}:
        default_source = "indeed"
    job_source = Prompt.ask(
        "Choose job source",
        choices=["indeed", "jobup", "jobs"],
        default=default_source,
        show_choices=True,
    )
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

        console.print("[warning]Running Workflow-1: QuickAndReady ...[/warning]")
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
        console.print("[success]Done.[/success]")
        console.print(f"Session Report: {result.get('report_path')}")
        console.print(f"Generated: {result.get('number_of_outputs_generated')} files.")

        if ai_target is not None or ai_max_iters is not None:
            traces = result.get("ai_guard_traces") or []
            _render_ai_guard_summary(traces)
    else:
        console.print(f"[error]Unknown workflow: {workflow}[/error]")

if __name__ == "__main__":
    app()
