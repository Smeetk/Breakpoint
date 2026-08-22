"""
BREAKPOINT — Entry Point
Run modes:
  python -m backend.main --mock                      # demo with fake browser
  python -m backend.main --url http://localhost:3000  # real browser
  python -m backend.main --api --mock                 # FastAPI server
  python -m backend.main --api --port 8001            # API on custom port
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING")
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import box

from backend.agent.agent import BreakpointAgent
from backend.browser.mock import MockBrowserController
from backend.browser.tools import BrowserTools
from backend.schemas.models import AgentEvent, EventType

console = Console()


# ---------------------------------------------------------------------------
# Rich terminal display
# ---------------------------------------------------------------------------

_STEP_COUNT = 0

def print_event(event: AgentEvent) -> None:
    global _STEP_COUNT
    t = event.type if isinstance(event.type, str) else event.type.value
    msg = event.message

    if t == "agent_start":
        console.print()
        console.print(Panel.fit(
            f"[bold white]🔍  BREAKPOINT[/bold white]\n"
            f"[dim]Autonomous Browser Investigation Agent[/dim]\n\n"
            f"[cyan]Goal:[/cyan] {msg.replace('Investigation started', '').strip() or event.data.get('goal', '')}",
            border_style="bright_blue",
            padding=(1, 3),
        ))
        console.print()

    elif t == "agent_action":
        _STEP_COUNT += 1
        action = event.data.get("action", "")
        reason = event.data.get("reason", "")
        url = event.data.get("url", "")

        action_colors = {
            "navigate": "cyan", "click": "yellow", "type": "green",
            "back": "dim", "forward": "dim", "refresh": "dim",
            "observe": "blue", "screenshot": "magenta",
        }
        color = action_colors.get(action, "white")

        url_part = f" [dim]→ {url}[/dim]" if url else ""
        console.print(
            f"  [dim]{_STEP_COUNT:>2}.[/dim] [{color}]{action:<10}[/{color}]  [white]{reason}[/white]{url_part}"
        )

    elif t == "anomaly":
        console.print()
        console.print(Panel(
            f"[bold yellow]⚠   ANOMALY DETECTED[/bold yellow]\n\n"
            f"[white]{msg}[/white]\n\n"
            f"[dim]Category: {event.data.get('bug_category', 'unknown')} | "
            f"Confidence: {event.data.get('confidence', '?')}[/dim]",
            border_style="yellow",
            padding=(0, 2),
        ))
        console.print()

    elif t == "hypothesis":
        console.print(Panel(
            f"[bold magenta]💡  HYPOTHESIS FORMED[/bold magenta]\n\n"
            f"[white]{event.data.get('statement', msg)}[/white]\n\n"
            f"[dim]ID: {event.data.get('hypothesis_id', '?')} | "
            f"Confidence: {event.data.get('confidence', '?')} | "
            f"Severity: {event.data.get('severity', '?')}[/dim]",
            border_style="magenta",
            padding=(0, 2),
        ))
        console.print()

    elif t == "experiment_start":
        steps = event.data.get("steps", "?")
        console.print(f"  [cyan]🧪  Experiment designed — {steps} steps[/cyan]")
        console.print()

    elif t == "reproduction":
        attempt = event.data.get("attempt", "?")
        total = event.data.get("total", "?")
        passed = event.data.get("passed")

        if passed is None:
            console.print(f"  [white]🔄  Reproducing {attempt}/{total}...[/white]")
        elif passed:
            console.print(f"  [green]✓   Reproduction {attempt}/{total}  PASS[/green]")
        else:
            console.print(f"  [red]✗   Reproduction {attempt}/{total}  FAIL[/red]")

    elif t == "bug_confirmed":
        data = event.data
        title = data.get("title", "Bug found")
        confidence = str(data.get("confidence", "")).replace("Confidence.", "")
        severity = str(data.get("severity", "")).replace("Severity.", "").upper()
        repro = f"{data.get('reproduction_successes', '?')}/{data.get('reproduction_attempts', '?')}"

        console.print()
        console.print(Panel(
            f"[bold red]🐛  BUG CONFIRMED[/bold red]\n\n"
            f"[bold white]{title}[/bold white]\n\n"
            f"[cyan]Confidence:[/cyan]  {confidence}\n"
            f"[cyan]Severity:[/cyan]   {severity}\n"
            f"[cyan]Reproduced:[/cyan] {repro}\n\n"
            f"[dim]Expected:[/dim] {data.get('expected', '')[:80]}\n"
            f"[dim]Actual:  [/dim] {data.get('actual', '')[:80]}",
            border_style="red",
            title=f"[red]{data.get('id', 'BUG')}[/red]",
            padding=(0, 2),
        ))
        console.print()

    elif t == "agent_finish":
        data = event.data
        bugs = data.get("confirmed_bugs", 0)
        steps = data.get("steps", 0)
        elapsed = data.get("elapsed_s", "?")
        console.print(Rule(style="bright_blue"))
        console.print(
            f"  [dim]Investigation complete — "
            f"{bugs} bug(s) confirmed | "
            f"{steps} steps | "
            f"{elapsed}s[/dim]"
        )

    elif t == "error":
        console.print(f"  [red]ERROR: {msg}[/red]")


# ---------------------------------------------------------------------------
# Final summary panel
# ---------------------------------------------------------------------------

def print_final_summary(state, elapsed: float) -> None:
    console.print()
    console.print(Rule("[bold bright_blue]BREAKPOINT REPORT[/bold bright_blue]"))
    console.print()

    if not state.confirmed_bugs:
        console.print(Panel(
            f"[yellow]No confirmed bugs found.[/yellow]\n"
            f"Status: {state.status} | Steps: {state.step_count} | "
            f"Hypotheses explored: {len(state.hypotheses)}",
            border_style="yellow",
        ))
        return

    for bug in state.confirmed_bugs:
        s = bug.to_summary()
        confidence = str(s.get("confidence", "")).replace("Confidence.", "")
        severity = str(s.get("severity", "")).replace("Severity.", "").upper()
        repro = f"{s.get('reproduction_successes')}/{s.get('reproduction_attempts')}"

        # Steps table
        steps_text = "\n".join(
            f"  [dim]{i+1}.[/dim] {step}"
            for i, step in enumerate(s.get("steps", []))
        )

        console.print(Panel(
            f"[bold red]🐛  {s['title']}[/bold red]\n\n"
            f"[cyan]Hypothesis:[/cyan] {s.get('hypothesis', '')[:120]}\n\n"
            f"[cyan]Expected:[/cyan]  {s.get('expected', '')[:100]}\n"
            f"[red]Actual:  [/red]  {s.get('actual', '')[:100]}\n\n"
            f"[cyan]Reproduced:[/cyan] {repro}  |  "
            f"[cyan]Confidence:[/cyan] {confidence}  |  "
            f"[cyan]Severity:[/cyan] {severity}\n\n"
            f"[bold white]Reproduction Steps:[/bold white]\n{steps_text}",
            border_style="red",
            title=f"[bold red]{s['id']}[/bold red]",
            padding=(1, 2),
        ))
        console.print()

    console.print(
        f"  [dim]Total: {len(state.confirmed_bugs)} bug(s) | "
        f"{state.step_count} steps | {elapsed:.1f}s[/dim]"
    )
    console.print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="BREAKPOINT — Autonomous Browser Investigation")
    parser.add_argument("--goal", default="Find something wrong with this web application.",
                        help="Investigation goal")
    parser.add_argument("--url", default="http://localhost:3000", help="Target URL")
    parser.add_argument("--mock", action="store_true", help="Use mock browser")
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--output", help="Save result JSON to file")
    parser.add_argument("--api", action="store_true", help="Launch as FastAPI server")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # ── API server mode ────────────────────────────────────────────────
    if args.api:
        try:
            import uvicorn
            from backend.server import create_app
        except ImportError:
            console.print("[red]uvicorn not installed. Run: pip install uvicorn fastapi[/red]")
            sys.exit(1)

        app = create_app(mock=args.mock)
        console.print(Panel(
            f"[bold cyan]BREAKPOINT API[/bold cyan]\n"
            f"[white]http://localhost:{args.port}[/white]\n\n"
            f"[dim]POST /api/run         — start investigation\n"
            f"GET  /api/run/{{id}}/stream — SSE event stream\n"
            f"GET  /api/run/{{id}}/result — final result JSON\n"
            f"GET  /api/run/{{id}}/test   — download Playwright test[/dim]",
            border_style="cyan",
        ))
        config = uvicorn.Config(app, host="0.0.0.0", port=args.port, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()
        return

    # ── CLI mode ───────────────────────────────────────────────────────
    if args.mock:
        controller = MockBrowserController()
    else:
        try:
            from backend.browser.controller import BrowserController
            controller = BrowserController()
            if hasattr(controller, "start"):
                await controller.start()
        except Exception as exc:
            console.print(f"[yellow]Browser failed ({exc}). Falling back to mock.[/yellow]")
            controller = MockBrowserController()

    browser = BrowserTools(controller)
    agent = BreakpointAgent(
        browser=browser,
        event_callback=print_event,
        max_steps=args.max_steps,
    )

    console.print(f"[dim]Goal:[/dim] {args.goal}")
    console.print(f"[dim]Target:[/dim] {args.url}")
    if args.mock:
        console.print("[dim]Mode: mock browser[/dim]")
    console.print()

    start = time.time()
    try:
        state = await agent.run(goal=args.goal, start_url=args.url)
    finally:
        if hasattr(controller, "stop"):
            try:
                await controller.stop()
            except Exception:
                pass

    elapsed = time.time() - start
    print_final_summary(state, elapsed)

    if args.output and state.confirmed_bugs:
        result = {
            "run_summary": {
                "status": str(state.status),
                "steps": state.step_count,
                "elapsed_s": round(elapsed, 1),
                "bugs_found": len(state.confirmed_bugs),
            },
            "bugs": [b.to_summary() for b in state.confirmed_bugs],
        }
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        console.print(f"[dim]Result saved → {args.output}[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
