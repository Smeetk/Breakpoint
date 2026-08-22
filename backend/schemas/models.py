"""
BREAKPOINT — Core Pydantic Schemas
All data models for the agent system.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    BACK = "back"
    FORWARD = "forward"
    REFRESH = "refresh"
    OBSERVE = "observe"
    SCREENSHOT = "screenshot"
    FINISH = "finish"


class AgentStatus(str, Enum):
    IDLE = "idle"
    EXPLORING = "exploring"
    HYPOTHESIZING = "hypothesizing"
    EXPERIMENTING = "experimenting"
    REPRODUCING = "reproducing"
    CONFIRMED = "confirmed"
    EXHAUSTED = "exhausted"
    FAILED = "failed"


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HypothesisStatus(str, Enum):
    PENDING = "pending"
    TESTING = "testing"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class EventType(str, Enum):
    AGENT_START = "agent_start"
    AGENT_ACTION = "agent_action"
    OBSERVATION = "observation"
    ANOMALY = "anomaly"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT_START = "experiment_start"
    REPRODUCTION = "reproduction"
    BUG_CONFIRMED = "bug_confirmed"
    AGENT_FINISH = "agent_finish"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Browser Interaction
# ---------------------------------------------------------------------------


class AgentAction(BaseModel):
    """A single planned browser action with validation."""

    action: ActionType
    url: Optional[str] = None           # for navigate
    selector: Optional[str] = None     # for click / type
    text: Optional[str] = None         # for type
    reason: str = ""

    class Config:
        use_enum_values = True

    def validate_fields(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []
        if self.action == ActionType.NAVIGATE and not self.url:
            errors.append("navigate action requires 'url'")
        if self.action == ActionType.CLICK and not self.selector:
            errors.append("click action requires 'selector'")
        if self.action == ActionType.TYPE and (not self.selector or not self.text):
            errors.append("type action requires 'selector' and 'text'")
        return errors


class PageElement(BaseModel):
    """A single interactive element on the page."""

    selector: str
    text: str = ""
    tag: str = ""
    element_type: str = ""
    visible: bool = True
    attributes: dict[str, str] = Field(default_factory=dict)


class Observation(BaseModel):
    """What the browser sees at a given moment."""

    url: str
    title: str = ""
    text: str = ""
    elements: list[PageElement] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    screenshot_path: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def compact_summary(self, max_text: int = 500) -> str:
        """Token-efficient summary for LLM prompts."""
        elem_strs = [
            f"[{e.tag}] '{e.text[:60]}' ({e.selector})"
            for e in self.elements[:15]
        ]
        text_snippet = self.text[:max_text] if self.text else ""
        errors_str = f"\nErrors: {self.errors}" if self.errors else ""
        return (
            f"URL: {self.url}\n"
            f"Title: {self.title}\n"
            f"Text snippet: {text_snippet}{errors_str}\n"
            f"Elements ({len(self.elements)} total, showing first 15):\n"
            + "\n".join(elem_strs)
        )


# ---------------------------------------------------------------------------
# Hypothesis & Experiment
# ---------------------------------------------------------------------------


class Hypothesis(BaseModel):
    """A testable claim about a potential bug."""

    id: str = Field(default_factory=lambda: f"HYP-{uuid.uuid4().hex[:6].upper()}")
    statement: str
    supporting_evidence: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.LOW
    status: HypothesisStatus = HypothesisStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Experiment(BaseModel):
    """A reproducible test sequence for a hypothesis."""

    id: str = Field(default_factory=lambda: f"EXP-{uuid.uuid4().hex[:6].upper()}")
    hypothesis_id: str
    description: str
    actions: list[AgentAction] = Field(default_factory=list)
    expected_result: str
    actual_result: Optional[str] = None
    passed: Optional[bool] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReproductionAttempt(BaseModel):
    """Result of a single reproduction attempt."""

    attempt_number: int
    passed: bool
    observations: list[str] = Field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Bug Result
# ---------------------------------------------------------------------------


class ConfirmedBug(BaseModel):
    """A confirmed, reproducible bug with full evidence."""

    id: str = Field(default_factory=lambda: f"BUG-{uuid.uuid4().hex[:6].upper()}")
    title: str
    description: str
    severity: Severity = Severity.HIGH
    confidence: Confidence = Confidence.HIGH

    hypothesis: str
    expected_behavior: str
    actual_behavior: str

    reproduction_steps: list[str] = Field(default_factory=list)
    reproduction_attempts: int = 0
    reproduction_successes: int = 0

    evidence: list[str] = Field(default_factory=list)
    screenshot_paths: list[str] = Field(default_factory=list)
    status: str = "confirmed"

    confirmed_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def reproduction_rate(self) -> float:
        if self.reproduction_attempts == 0:
            return 0.0
        return self.reproduction_successes / self.reproduction_attempts

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "title": self.title,
            "confidence": self.confidence,
            "severity": self.severity,
            "hypothesis": self.hypothesis,
            "expected": self.expected_behavior,
            "actual": self.actual_behavior,
            "reproduction_attempts": self.reproduction_attempts,
            "reproduction_successes": self.reproduction_successes,
            "steps": self.reproduction_steps,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Agent State
# ---------------------------------------------------------------------------


class AgentState(BaseModel):
    """Live state of the investigation agent."""

    goal: str
    current_url: str = ""
    observations: list[Observation] = Field(default_factory=list)
    actions_taken: list[AgentAction] = Field(default_factory=list)
    visited_urls: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    confirmed_bugs: list[ConfirmedBug] = Field(default_factory=list)
    step_count: int = 0
    status: AgentStatus = AgentStatus.IDLE
    events: list["AgentEvent"] = Field(default_factory=list)
    start_time: datetime = Field(default_factory=datetime.utcnow)

    def last_observation(self) -> Optional[Observation]:
        return self.observations[-1] if self.observations else None

    def recent_action_types(self, n: int = 5) -> list[str]:
        return [a.action for a in self.actions_taken[-n:]]

    def has_visited(self, url: str) -> bool:
        return url in self.visited_urls

    def add_observation(self, obs: Observation) -> None:
        self.observations.append(obs)
        if obs.url not in self.visited_urls:
            self.visited_urls.append(obs.url)
        self.current_url = obs.url

    def add_action(self, action: AgentAction) -> None:
        self.actions_taken.append(action)
        self.step_count += 1

    def add_hypothesis(self, hyp: Hypothesis) -> None:
        self.hypotheses.append(hyp)

    def add_event(self, event: "AgentEvent") -> None:
        self.events.append(event)


# ---------------------------------------------------------------------------
# Events (for Person 4 frontend)
# ---------------------------------------------------------------------------


class AgentEvent(BaseModel):
    """Structured event emitted by the agent for the frontend dashboard."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True
