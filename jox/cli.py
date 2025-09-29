from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm

from jox.utils.logging import setup_logger
from jox.settings import SETTINGS
from jox.cv.parse import parse_cv
from jox.orchestrator.memory import add_entry, load_entries
from jox.workflows.quick_and_ready import run_quick_and_ready

app = typer.Typer(add_completion=False)
console = Console()

@app.command()
def main(workflow: Optional[str] = typer.Option(None, help="Workflow to run (quick-and-ready)")):
    setup_logger(SETTINGS.log_level, SETTINGS.log_json)
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

    # UX flow 2: Function, Role, Country
    function = Prompt.ask("Target Function (e.g., Data Science)")
    role = Prompt.ask("Target Role Title (e.g., ML Engineer)")
    country = Prompt.ask("Target Country (e.g., Switzerland)")

    if not workflow:
        workflow = "quick-and-ready"

    if workflow == "quick-and-ready":
        console.print("[yellow]Running Workflow-1: QuickAndReady ...[/yellow]")
        result = asyncio.run(run_quick_and_ready(cv, function, role, country))
        console.print("[green]Done.[/green]")
        console.print(f"Session Report: {result.get('report_path')}")
        console.print(f"Generated: {result.get('number_of_outputs_generated')} files.")
    else:
        console.print(f"[red]Unknown workflow: {workflow}[/red]")

if __name__ == "__main__":
    app()
