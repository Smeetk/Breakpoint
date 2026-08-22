"""
BREAKPOINT — Replay Engine
Replays recorded action sequences for reproduction verification.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.browser.tools import BrowserTools
from backend.schemas.models import AgentAction, Experiment, ReproductionAttempt

log = logging.getLogger("breakpoint.reproducer")


async def replay_experiment(
    browser: BrowserTools,
    experiment: Experiment,
    attempt_num: int,
) -> ReproductionAttempt:
    """
    Replay an experiment's action sequence and record the result.
    Delegates to agent's _run_experiment for consistency.
    """
    observations = []
    error = None

    try:
        for action in experiment.actions:
            obs = await browser.execute(action)
            observations.append(f"[{obs.url}] {obs.text[:100]}")
    except Exception as exc:
        error = str(exc)
        log.error("[REPRODUCER] Replay error: %s", exc)

    return ReproductionAttempt(
        attempt_number=attempt_num,
        passed=(error is None),
        observations=observations,
        error=error,
    )
