"""
BREAKPOINT — FastAPI Server with SSE
Gives Person 4 a real-time event stream to drive the dashboard.

Endpoints:
  POST /api/run              → start investigation, returns {run_id}
  GET  /api/run/{run_id}/stream  → SSE stream of AgentEvent objects
  GET  /api/run/{run_id}/result  → final result (ConfirmedBug JSON)
  GET  /api/run/{run_id}/test    → generated Playwright test file
  GET  /api/health           → health check
  GET  /api/runs             → list all runs
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

log = logging.getLogger("breakpoint.server")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    goal: str = "Find something wrong with this web application."
    url: str = "http://localhost:3000"
    mock: bool = False
    max_steps: int = 40


class RunStatus(BaseModel):
    run_id: str
    status: str
    started_at: str
    steps: int = 0
    bugs_found: int = 0
    message: str = ""


# ---------------------------------------------------------------------------
# In-memory run registry
# ---------------------------------------------------------------------------

_runs: dict[str, dict[str, Any]] = {}


def _new_run(run_id: str, request: RunRequest) -> dict:
    return {
        "run_id": run_id,
        "request": request,
        "status": "starting",
        "started_at": datetime.utcnow().isoformat(),
        "events": [],
        "event_queue": asyncio.Queue(),
        "state": None,
        "test_path": None,
        "task": None,
    }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(mock: bool = False) -> FastAPI:
    app = FastAPI(
        title="BREAKPOINT API",
        description="Autonomous browser investigation agent",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ──────────────────────────────────────────────────────────

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "service": "BREAKPOINT", "version": "1.0.0"}

    @app.get("/api/runs")
    async def list_runs():
        return [
            {
                "run_id": r["run_id"],
                "status": r["status"],
                "started_at": r["started_at"],
                "bugs_found": len(r["state"].confirmed_bugs) if r["state"] else 0,
                "steps": r["state"].step_count if r["state"] else 0,
            }
            for r in _runs.values()
        ]

    @app.post("/api/run", response_model=RunStatus)
    async def start_run(request: RunRequest):
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        run = _new_run(run_id, request)
        _runs[run_id] = run

        # Launch agent as background task
        task = asyncio.create_task(_execute_run(run_id, request, use_mock=mock or request.mock))
        run["task"] = task

        log.info("[SERVER] Started run %s | goal=%s", run_id, request.goal)
        return RunStatus(
            run_id=run_id,
            status="starting",
            started_at=run["started_at"],
            message="Investigation started",
        )

    @app.get("/api/run/{run_id}/stream")
    async def stream_events(run_id: str):
        if run_id not in _runs:
            raise HTTPException(status_code=404, detail="Run not found")

        async def event_generator() -> AsyncGenerator[str, None]:
            run = _runs[run_id]
            queue: asyncio.Queue = run["event_queue"]

            # First send all buffered events (for reconnects)
            for event in run["events"]:
                yield _format_sse(event)

            # Then stream new events as they arrive
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if event is None:  # sentinel — run complete
                        yield _format_sse({"type": "stream_end", "message": "Investigation complete"})
                        break
                    yield _format_sse(event)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # SSE keepalive ping

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/run/{run_id}/result")
    async def get_result(run_id: str):
        if run_id not in _runs:
            raise HTTPException(status_code=404, detail="Run not found")
        run = _runs[run_id]
        if run["status"] not in ("complete", "failed"):
            return {"status": run["status"], "message": "Still running"}
        state = run["state"]
        if not state:
            return {"status": "failed", "bugs": []}
        return {
            "status": run["status"],
            "run_id": run_id,
            "steps": state.step_count,
            "bugs": [b.to_summary() for b in state.confirmed_bugs],
            "hypotheses": len(state.hypotheses),
            "test_path": run.get("test_path"),
        }

    @app.get("/api/run/{run_id}/test")
    async def get_test_file(run_id: str):
        if run_id not in _runs:
            raise HTTPException(status_code=404, detail="Run not found")
        run = _runs[run_id]
        test_path = run.get("test_path")
        if not test_path or not os.path.exists(test_path):
            raise HTTPException(status_code=404, detail="Test file not yet generated")
        return FileResponse(test_path, filename=os.path.basename(test_path))

    return app


# ---------------------------------------------------------------------------
# Run executor (background task)
# ---------------------------------------------------------------------------

async def _execute_run(run_id: str, request: RunRequest, use_mock: bool) -> None:
    from backend.agent.agent import BreakpointAgent
    from backend.agent.testgen import generate_playwright_test
    from backend.browser.tools import BrowserTools
    from backend.schemas.models import AgentEvent

    run = _runs[run_id]
    queue: asyncio.Queue = run["event_queue"]

    def on_event(event: AgentEvent) -> None:
        payload = {
            "id": event.id,
            "type": event.type if isinstance(event.type, str) else event.type.value,
            "message": event.message,
            "data": event.data,
            "timestamp": event.timestamp.isoformat(),
        }
        run["events"].append(payload)
        queue.put_nowait(payload)

    try:
        run["status"] = "running"

        # Browser setup
        if use_mock:
            from backend.browser.mock import MockBrowserController
            controller = MockBrowserController()
        else:
            from backend.browser.controller import BrowserController
            controller = BrowserController()
            if hasattr(controller, "start"):
                await controller.start()

        browser = BrowserTools(controller)
        agent = BreakpointAgent(
            browser=browser,
            event_callback=on_event,
            max_steps=request.max_steps,
        )

        state = await agent.run(goal=request.goal, start_url=request.url)
        run["state"] = state
        run["status"] = "complete"

        # Generate Playwright test for first confirmed bug
        if state.confirmed_bugs:
            bug = state.confirmed_bugs[0]
            test_path = await generate_playwright_test(
                bug=bug,
                recorded_actions=state.actions_taken,
                base_url=request.url,
                output_dir=f"/tmp/breakpoint_tests/{run_id}",
            )
            run["test_path"] = test_path
            on_event(AgentEvent(
                type="playwright_test_generated",
                message=f"Playwright test generated: {os.path.basename(test_path or '')}",
                data={"path": test_path, "bug_id": bug.id},
            ))

        if hasattr(controller, "stop"):
            await controller.stop()

    except Exception as exc:
        log.error("[SERVER] Run %s failed: %s", run_id, exc, exc_info=True)
        run["status"] = "failed"
        queue.put_nowait({
            "type": "error",
            "message": f"Agent error: {exc}",
            "data": {},
        })
    finally:
        queue.put_nowait(None)  # sentinel


# ---------------------------------------------------------------------------
# SSE formatting
# ---------------------------------------------------------------------------

def _format_sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
