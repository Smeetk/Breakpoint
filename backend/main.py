"""
BREAKPOINT — Main Entry Point
Run with:
    python -m backend.main
    python -m backend.main --goal "Find something wrong" --url http://localhost:3000
    python -m backend.main --mock  # Use fake browser for testing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

load_dotenv()

# Set up logging before imports
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from backend.agent.agent import BreakpointAgent
from backend.browser.mock import MockBrowserController
from backend.browser.tools import BrowserTools
from backend.schemas.models import AgentEvent, EventType

console = Console()


# ---------------------------------------------------------------------------
# Event display (for terminal — Person 4 will do this in the UI)
# ---------------------------------------------------------------------------

def print_event(event: AgentEvent) -> None:
    t = event.type
    msg = event.message

    if t == EventType.AGENT_START:
        console.print(Panel(f"[bold cyan]🔍 BREAKPOINT INVESTIGATION STARTED[/bold cyan]\n{msg}", style="cyan"))
    elif t == EventType.AGENT_ACTION:
        console.print(f"  [dim]→[/dim] [yellow]{msg}[/yellow]")
    elif t == EventType.ANOMALY:
        console.print(Panel(f"[bold yellow]⚠️  ANOMALY DETECTED[/bold yellow]\n{msg}", style="yellow"))
    elif t == EventType.HYPOTHESIS:
        console.print(Panel(f"[bold magenta]💡 HYPOTHESIS FORMED[/bold magenta]\n{msg}", style="magenta"))
    elif t == EventType.EXPERIMENT_START:
        console.print(f"  [cyan]🧪 Designing experiment: {msg}[/cyan]")
    elif t == EventType.REPRODUCTION:
        data = event.data
        attempt = data.get("attempt", "?")
        total = data.get("total", "?")
        console.print(f"  [green]🔄 Reproduction {attempt}/{total}...[/green]")
    elif t == EventType.BUG_CONFIRMED:
        console.print(Panel(
            f"[bold red]🐛 BUG CONFIRMED[/bold red]\n{msg}",
            style="red",
            title="BREAKPOINT RESULT",
        ))
    elif t == EventType.AGENT_FINISH:
        console.print(f"\n[dim]Investigation complete: {msg}[/dim]")
    elif t == EventType.ERROR:
        console.print(f"  [red]ERROR: {msg}[/red]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="BREAKPOINT — Autonomous Browser Investigation")
    parser.add_argument("--goal", default="Find something wrong with this web application.",
                        help="Investigation goal")
    parser.add_argument("--url", default="http://localhost:3000",
                        help="Target application URL")
    parser.add_argument("--mock", action="store_true",
                        help="Use mock browser (no Playwright required)")
    parser.add_argument("--max-steps", type=int, default=40,
                        help="Maximum agent steps")
    parser.add_argument("--output", help="Save result JSON to file")
    args = parser.parse_args()

    # Browser selection
    if args.mock:
        console.print("[cyan]Using mock browser (scripted scenario)[/cyan]")
        controller = MockBrowserController()
    else:
        try:
            from backend.browser.controller import BrowserController
            controller = BrowserController()
            await controller.start()  # type: ignore[attr-defined]
        except Exception as exc:
            console.print(f"[red]Failed to start browser controller: {exc}[/red]")
            console.print("[yellow]Falling back to mock browser.[/yellow]")
            controller = MockBrowserController()

    browser = BrowserTools(controller)
    agent = BreakpointAgent(
        browser=browser,
        event_callback=print_event,
        max_steps=args.max_steps,
    )

    console.print(f"\n[bold]Goal:[/bold] {args.goal}")
    console.print(f"[bold]Target:[/bold] {args.url}\n")

    try:
        state = await agent.run(goal=args.goal, start_url=args.url)
    finally:
        if hasattr(controller, "stop"):
            try:
                await controller.stop()
            except Exception:
                pass

    # Print final result
    console.print("\n" + "=" * 60)
    if state.confirmed_bugs:
        bug = state.confirmed_bugs[0]
        summary = bug.to_summary()
        console.print(Panel(
            f"[bold red]BUG CONFIRMED[/bold red]\n\n"
            f"[bold]Title:[/bold] {summary['title']}\n"
            f"[bold]Confidence:[/bold] {summary['confidence']}\n"
            f"[bold]Hypothesis:[/bold] {summary['hypothesis']}\n\n"
            f"[bold]Expected:[/bold] {summary['expected']}\n"
            f"[bold]Actual:[/bold] {summary['actual']}\n\n"
            f"[bold]Reproduced:[/bold] {summary['reproduction_successes']}/{summary['reproduction_attempts']}\n\n"
            f"[bold]Steps:[/bold]\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(summary['steps'])),
            title="BREAKPOINT RESULT",
            style="red",
        ))

        if args.output:
            with open(args.output, "w") as f:
                json.dump(summary, f, indent=2, default=str)
            console.print(f"[dim]Result saved to {args.output}[/dim]")
    else:
        console.print(f"[yellow]No confirmed bugs found. Status: {state.status}[/yellow]")
        console.print(f"[dim]Steps taken: {state.step_count} | Hypotheses: {len(state.hypotheses)}[/dim]")

    console.print(f"\n[dim]Total steps: {state.step_count} | Events: {len(state.events)}[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
