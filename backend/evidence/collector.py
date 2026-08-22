"""
BREAKPOINT — Evidence Collector
Collects screenshots and text evidence during investigations.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.schemas.models import ConfirmedBug, Observation

log = logging.getLogger("breakpoint.evidence")


class EvidenceCollector:
    """Collects and organizes evidence for bug reports."""

    def __init__(self, output_dir: str = "/tmp/breakpoint_evidence") -> None:
        self.output_dir = output_dir
        self._screenshots: list[str] = []
        self._observations: list[Observation] = []

    def add_screenshot(self, path: str) -> None:
        self._screenshots.append(path)
        log.debug("[EVIDENCE] Screenshot added: %s", path)

    def add_observation(self, obs: Observation) -> None:
        self._observations.append(obs)

    def get_text_evidence(self) -> list[str]:
        return [
            f"[{obs.url}] {obs.text[:200]}"
            for obs in self._observations[-10:]
        ]

    def attach_to_bug(self, bug: ConfirmedBug) -> ConfirmedBug:
        bug.screenshot_paths = self._screenshots[-5:]
        return bug
