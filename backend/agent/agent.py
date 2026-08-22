"""
BREAKPOINT — Core Investigation Agent
Phases 5–12: Observe → Plan → Act → Anomaly → Hypothesis → Experiment → Reproduce → Confirm
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

from pydantic import ValidationError

from backend.agent.llm import llm_call_json
from backend.agent.prompts import (
    INVESTIGATOR_SYSTEM_PROMPT,
    build_anomaly_prompt,
    build_bug_confirmation_prompt,
    build_experiment_prompt,
    build_planning_prompt,
)
from backend.browser.tools import BrowserTools
from backend.schemas.models import (
    ActionType,
    AgentAction,
    AgentEvent,
    AgentState,
    AgentStatus,
    Confidence,
    ConfirmedBug,
    EventType,
    Experiment,
    Hypothesis,
    HypothesisStatus,
    Observation,
    ReproductionAttempt,
    Severity,
)

log = logging.getLogger("breakpoint.agent")


# ---------------------------------------------------------------------------
# Limits (configurable)
# ---------------------------------------------------------------------------

MAX_STEPS = 40
MAX_RETRIES = 2
MAX_RUNTIME_SECONDS = 300
MAX_SCENARIOS = 3
REPRODUCTION_ATTEMPTS = 3
MIN_REPRODUCTIONS_FOR_CONFIRM = 2


# ---------------------------------------------------------------------------
# Deterministic fallback scenarios
# ---------------------------------------------------------------------------

FALLBACK_SCENARIOS: list[list[dict[str, Any]]] = [
    # Scenario 1: add to cart → modify → checkout
    [
        {"action": "navigate", "url": "http://localhost:3000", "reason": "Start fresh"},
        {"action": "navigate", "url": "http://localhost:3000/products", "reason": "Browse products"},
        {"action": "click", "selector": "button[data-product='headphones']", "reason": "Add item to cart"},
        {"action": "navigate", "url": "http://localhost:3000/cart", "reason": "Go to cart"},
        {"action": "observe", "reason": "Record cart total"},
        {"action": "click", "selector": "button[data-action='decrease-qty']", "reason": "Modify cart quantity"},
        {"action": "observe", "reason": "Record modified cart total"},
        {"action": "navigate", "url": "http://localhost:3000/checkout", "reason": "Proceed to checkout"},
        {"action": "observe", "reason": "Record checkout total — compare to cart"},
    ],
    # Scenario 2: back/forward navigation
    [
        {"action": "navigate", "url": "http://localhost:3000/checkout", "reason": "Go to checkout"},
        {"action": "back", "reason": "Go back to previous page"},
        {"action": "navigate", "url": "http://localhost:3000/cart", "reason": "Modify cart"},
        {"action": "click", "selector": "button[data-action='decrease-qty']", "reason": "Change quantity"},
        {"action": "forward", "reason": "Return to checkout via forward"},
        {"action": "observe", "reason": "Check if checkout updated"},
    ],
]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class BreakpointAgent:
    """
    The autonomous browser investigation agent.
    
    LLM handles: planning, anomaly interpretation, hypothesis generation,
                 experiment design, bug report writing.
    
    Python handles: execution, validation, retries, limits, state, 
                    reproduction counting, confidence calculation.
    """

    def __init__(
        self,
        browser: BrowserTools,
        event_callback: Optional[Callable[[AgentEvent], None]] = None,
        max_steps: int = MAX_STEPS,
        max_runtime: int = MAX_RUNTIME_SECONDS,
    ) -> None:
        self.browser = browser
        self._emit = event_callback or (lambda e: None)
        self.max_steps = max_steps
        self.max_runtime = max_runtime
        self._start_time: float = 0.0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, goal: str, start_url: str = "http://localhost:3000") -> AgentState:
        """Run the full investigation. Returns final AgentState."""
        self._start_time = time.time()

        state = AgentState(goal=goal, status=AgentStatus.EXPLORING)
        log.info("[AGENT] Goal received: %s", goal)
        self._event(state, EventType.AGENT_START, "Investigation started", {"goal": goal})

        # ── PHASE A: Initial exploration ──────────────────────────────
        await self._navigate_to(state, start_url)
        initial_obs = await self._observe(state)

        # ── PHASE B: Main planning loop ───────────────────────────────
        hypothesis: Optional[Hypothesis] = None
        no_anomaly_streak = 0

        while not self._should_stop(state):
            state.step_count += 1
            log.info("[AGENT] Step %d | status=%s | url=%s",
                     state.step_count, state.status, state.current_url)

            prev_obs = state.last_observation()

            # Plan next action via LLM
            action = await self._plan_action(state, prev_obs or initial_obs)

            # Execute
            obs = await self.browser.execute(action)
            state.add_observation(obs)
            state.add_action(action)

            self._event(state, EventType.AGENT_ACTION,
                        f"{action.action}: {action.reason}",
                        {"action": action.action, "reason": action.reason,
                         "url": obs.url})

            # Finish requested by agent
            if action.action == ActionType.FINISH:
                log.info("[AGENT] Agent requested finish")
                break

            # ── Anomaly detection ─────────────────────────────────────
            if prev_obs and obs.url and len(state.actions_taken) >= 3:
                anomaly = await self._check_anomaly(state, obs, prev_obs)
                if anomaly.get("suspicious"):
                    no_anomaly_streak = 0
                    log.info("[AGENT] Suspicious behavior detected: %s",
                             anomaly.get("reason", ""))
                    self._event(state, EventType.ANOMALY,
                                anomaly.get("reason", "Suspicious state detected"),
                                anomaly)

                    # Create hypothesis
                    if not hypothesis or hypothesis.status != HypothesisStatus.PENDING:
                        hypothesis = self._create_hypothesis(
                            state,
                            anomaly.get("hypothesis", anomaly.get("reason", "Suspicious behavior")),
                            anomaly.get("confidence", "MEDIUM"),
                        )
                        state.add_hypothesis(hypothesis)

                    # Switch to experimenting mode
                    if state.status == AgentStatus.EXPLORING:
                        state.status = AgentStatus.HYPOTHESIZING
                else:
                    no_anomaly_streak += 1

            # ── Hypothesis testing ────────────────────────────────────
            if (
                hypothesis
                and hypothesis.status == HypothesisStatus.PENDING
                and state.step_count >= 6
            ):
                state.status = AgentStatus.EXPERIMENTING
                experiment = await self._design_experiment(state, hypothesis)
                state.experiments.append(experiment)

                # ── Reproduction ──────────────────────────────────────
                state.status = AgentStatus.REPRODUCING
                bug = await self._reproduce(state, hypothesis, experiment)

                if bug:
                    state.confirmed_bugs.append(bug)
                    state.status = AgentStatus.CONFIRMED
                    self._event(state, EventType.BUG_CONFIRMED,
                                f"BUG CONFIRMED: {bug.title}",
                                bug.to_summary())
                    log.info("[BUG] Confirmed: %s | confidence=%s", bug.title, bug.confidence)
                    break
                else:
                    hypothesis.status = HypothesisStatus.REJECTED
                    log.info("[AGENT] Hypothesis rejected: %s", hypothesis.statement)
                    state.status = AgentStatus.EXPLORING
                    hypothesis = None

        # ── Termination ───────────────────────────────────────────────
        if state.status not in (AgentStatus.CONFIRMED, AgentStatus.FAILED):
            state.status = AgentStatus.EXHAUSTED

        self._event(state, EventType.AGENT_FINISH,
                    f"Investigation complete. Status: {state.status}",
                    {"status": state.status,
                     "confirmed_bugs": len(state.confirmed_bugs),
                     "steps": state.step_count})
        log.info("[AGENT] Investigation complete. Status=%s | Steps=%d | Bugs=%d",
                 state.status, state.step_count, len(state.confirmed_bugs))
        return state

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _plan_action(self, state: AgentState, obs: Observation) -> AgentAction:
        """Ask LLM for next action, validate, retry, fallback."""
        prompt = build_planning_prompt(state, obs)

        raw = await llm_call_json(
            system_prompt=INVESTIGATOR_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=400,
        )
        if raw:
            action = self._parse_action(raw, state)
            if action:
                log.info("[AGENT] Planning → %s | %s", action.action, action.reason[:80])
                return action
        log.warning("[AGENT] LLM planning returned no valid action. Using fallback.")

        # Deterministic fallback
        return self._fallback_action(state)

    def _parse_action(self, raw: dict[str, Any], state: AgentState) -> Optional[AgentAction]:
        """Parse and validate LLM action output."""
        try:
            # Handle null values from LLM
            action_data = {
                "action": raw.get("action", "observe"),
                "url": raw.get("url") or None,
                "selector": raw.get("selector") or None,
                "text": raw.get("text") or None,
                "reason": raw.get("reason", ""),
            }
            action = AgentAction(**action_data)
            errors = action.validate_fields()
            if errors:
                log.warning("[AGENT] Action validation: %s", errors)
                # Try to recover: if navigate without URL, use observe instead
                if action.action == ActionType.NAVIGATE:
                    return AgentAction(action=ActionType.OBSERVE, reason="Fallback observe")
                return None
            # Avoid repeating the exact same action
            recent = state.recent_action_types(3)
            if recent.count(action.action) >= 3 and action.action not in (
                ActionType.OBSERVE, ActionType.FINISH
            ):
                log.warning("[AGENT] Avoiding repeated action: %s", action.action)
                return None
            return action
        except (ValidationError, Exception) as exc:
            log.warning("[AGENT] Action parse error: %s | raw: %s", exc, raw)
            return None

    def _fallback_action(self, state: AgentState) -> AgentAction:
        """
        Stateful deterministic fallback when LLM planning fails.
        Walks through the full bug-discovery scenario in order.
        """
        log.warning("[AGENT] Using deterministic fallback action")

        # Full scenario: explore → add to cart → modify → checkout (trigger bug)
        scenario = [
            AgentAction(action=ActionType.NAVIGATE, url="http://localhost:3000",
                        reason="Fallback: start at home"),
            AgentAction(action=ActionType.NAVIGATE, url="http://localhost:3000/products",
                        reason="Fallback: browse products"),
            AgentAction(action=ActionType.CLICK, selector="button[data-product='headphones']",
                        reason="Fallback: add headphones to cart"),
            AgentAction(action=ActionType.NAVIGATE, url="http://localhost:3000/cart",
                        reason="Fallback: view cart"),
            AgentAction(action=ActionType.OBSERVE,
                        reason="Fallback: record cart total before modification"),
            AgentAction(action=ActionType.CLICK, selector="button[data-action='decrease-qty']",
                        reason="Fallback: modify cart quantity to trigger bug"),
            AgentAction(action=ActionType.OBSERVE,
                        reason="Fallback: record modified cart total"),
            AgentAction(action=ActionType.NAVIGATE, url="http://localhost:3000/checkout",
                        reason="Fallback: proceed to checkout"),
            AgentAction(action=ActionType.OBSERVE,
                        reason="Fallback: check if checkout total matches modified cart"),
        ]

        # Return the next unexecuted step
        step = state.step_count - 1  # step_count increments after action
        idx = min(step, len(scenario) - 1)
        return scenario[idx]

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------

    async def _check_anomaly(
        self, state: AgentState, current: Observation, previous: Observation
    ) -> dict[str, Any]:
        """
        Two-layer anomaly detection:
        1. Deterministic: fast pattern checks
        2. LLM: semantic analysis if needed
        """
        # ── Layer 1: Deterministic checks ────────────────────────────
        deterministic = self._deterministic_anomaly(current, previous, state)
        if deterministic:
            return deterministic

        # ── Layer 2: LLM check (only for checkout pages or suspicious URLs) ──
        interesting_urls = ["checkout", "cart", "payment", "order", "confirm"]
        if any(kw in current.url for kw in interesting_urls) or len(state.observations) % 4 == 0:
            prompt = build_anomaly_prompt(state, current, previous)
            result = await llm_call_json(
                system_prompt="You are a web application bug detector. Respond only in JSON.",
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=300,
            )
            if result and result.get("suspicious"):
                return result

        return {"suspicious": False}

    def _deterministic_anomaly(
        self,
        current: Observation,
        previous: Observation,
        state: AgentState,
    ) -> Optional[dict[str, Any]]:
        """
        Fast Python checks for common patterns.
        No LLM needed for these.
        """
        # Price inconsistency: extract prices from text
        curr_prices = self._extract_prices(current.text)
        prev_prices = self._extract_prices(previous.text)

        # Checkout showing different total than cart page
        if "checkout" in current.url and "cart" in previous.url:
            if curr_prices and prev_prices and curr_prices != prev_prices:
                prev_max = max(prev_prices)
                curr_max = max(curr_prices)
                if curr_max > prev_max:
                    # Checkout showing MORE than cart — stale!
                    return {
                        "suspicious": True,
                        "reason": (
                            f"Checkout total ({curr_max}) appears higher than "
                            f"cart total ({prev_max}). Possible stale state."
                        ),
                        "hypothesis": (
                            "Checkout total may not update after cart is modified. "
                            "Cart shows updated price but checkout retains original."
                        ),
                        "confidence": "HIGH",
                    }

        # Console errors
        if current.errors and not previous.errors:
            return {
                "suspicious": True,
                "reason": f"New console errors appeared: {current.errors[:2]}",
                "hypothesis": "Application is throwing unexpected errors after this action.",
                "confidence": "MEDIUM",
            }

        # Page title disappeared
        if previous.title and not current.title and current.url == previous.url:
            return {
                "suspicious": True,
                "reason": "Page title vanished while staying on same URL.",
                "hypothesis": "Page may have partially re-rendered or failed to load.",
                "confidence": "LOW",
            }

        return None

    def _extract_prices(self, text: str) -> list[float]:
        """Extract numeric price values from page text."""
        import re
        # Match ₹1500, $1500, 1500.00, etc.
        matches = re.findall(r"[₹$€£]?\s*(\d+(?:[,]\d+)*(?:\.\d+)?)", text)
        prices = []
        for m in matches:
            try:
                prices.append(float(m.replace(",", "")))
            except ValueError:
                pass
        return prices

    # ------------------------------------------------------------------
    # Hypothesis
    # ------------------------------------------------------------------

    def _create_hypothesis(
        self, state: AgentState, statement: str, confidence_str: str
    ) -> Hypothesis:
        conf_map = {"LOW": Confidence.LOW, "MEDIUM": Confidence.MEDIUM, "HIGH": Confidence.HIGH}
        conf = conf_map.get(confidence_str.upper(), Confidence.MEDIUM)

        obs_evidence = []
        if state.observations:
            last = state.last_observation()
            if last:
                obs_evidence.append(f"Observed at {last.url}: {last.text[:150]}")

        hyp = Hypothesis(
            statement=statement,
            supporting_evidence=obs_evidence,
            confidence=conf,
        )
        log.info("[AGENT] Hypothesis created: [%s] %s", hyp.id, statement)
        self._event(
            state,
            EventType.HYPOTHESIS,
            f"Hypothesis: {statement}",
            {"hypothesis_id": hyp.id, "statement": statement, "confidence": conf},
        )
        return hyp

    # ------------------------------------------------------------------
    # Experiment design
    # ------------------------------------------------------------------

    async def _design_experiment(
        self, state: AgentState, hypothesis: Hypothesis
    ) -> Experiment:
        """Ask LLM to design a test sequence for the hypothesis."""
        log.info("[AGENT] Designing experiment for hypothesis: %s", hypothesis.id)
        self._event(state, EventType.EXPERIMENT_START,
                    f"Designing experiment for: {hypothesis.statement[:80]}",
                    {"hypothesis_id": hypothesis.id})

        prompt = build_experiment_prompt(hypothesis.statement, state.current_url)
        raw = await llm_call_json(
            system_prompt="You design browser test sequences. Respond only in JSON.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=600,
        )

        actions: list[AgentAction] = []
        if raw and "actions" in raw:
            for a in raw["actions"]:
                try:
                    act = AgentAction(**{k: v for k, v in a.items() if v is not None})
                    actions.append(act)
                except Exception:
                    pass

        # Fallback to hardcoded scenario if LLM fails
        if not actions:
            log.warning("[AGENT] LLM experiment design failed. Using fallback scenario.")
            scenario = FALLBACK_SCENARIOS[0]
            for a in scenario:
                try:
                    actions.append(AgentAction(**a))
                except Exception:
                    pass

        exp = Experiment(
            hypothesis_id=hypothesis.id,
            description=raw.get("description", "Test hypothesis via browser actions") if raw else "Fallback scenario",
            actions=actions,
            expected_result=raw.get("expected_result", "Application state is consistent") if raw else "Consistent state",
        )
        log.info("[AGENT] Experiment [%s] designed: %d actions", exp.id, len(actions))
        return exp

    # ------------------------------------------------------------------
    # Reproduction
    # ------------------------------------------------------------------

    async def _reproduce(
        self,
        state: AgentState,
        hypothesis: Hypothesis,
        experiment: Experiment,
    ) -> Optional[ConfirmedBug]:
        """
        Run the experiment up to REPRODUCTION_ATTEMPTS times.
        Requires MIN_REPRODUCTIONS_FOR_CONFIRM successes.
        """
        attempts: list[ReproductionAttempt] = []
        before_obs_text = ""
        after_obs_text = ""

        for i in range(1, REPRODUCTION_ATTEMPTS + 1):
            log.info("[REPRODUCER] Attempt %d/%d", i, REPRODUCTION_ATTEMPTS)
            self._event(state, EventType.REPRODUCTION,
                        f"Reproduction attempt {i}/{REPRODUCTION_ATTEMPTS}",
                        {"attempt": i, "total": REPRODUCTION_ATTEMPTS})

            result, before_text, after_text = await self._run_experiment(
                state, experiment, attempt_num=i
            )
            attempts.append(result)

            if before_text:
                before_obs_text = before_text
            if after_text:
                after_obs_text = after_text

            log.info("[REPRODUCER] Attempt %d: %s", i, "PASS" if result.passed else "FAIL")

        successes = sum(1 for a in attempts if a.passed)
        log.info("[REPRODUCER] Result: %d/%d reproductions succeeded", successes, len(attempts))

        if successes < MIN_REPRODUCTIONS_FOR_CONFIRM:
            return None

        # Confirmed! Generate bug report via LLM
        confidence = (
            Confidence.HIGH if successes == REPRODUCTION_ATTEMPTS
            else Confidence.MEDIUM
        )
        hypothesis.status = HypothesisStatus.CONFIRMED

        bug_raw = await llm_call_json(
            system_prompt="You write concise bug reports. Respond only in JSON.",
            user_prompt=build_bug_confirmation_prompt(
                hypothesis.statement,
                experiment.expected_result,
                before_obs_text,
                after_obs_text,
                successes,
                len(attempts),
            ),
            temperature=0.1,
            max_tokens=600,
        )

        # Build ConfirmedBug (with LLM data or fallback)
        steps = bug_raw.get("reproduction_steps", []) if bug_raw else []
        if not steps:
            steps = [a.reason for a in experiment.actions if a.reason]

        evidence = []
        for a in attempts:
            evidence.extend(a.observations[:2])

        bug = ConfirmedBug(
            title=bug_raw.get("title", "Checkout total becomes stale after cart modification") if bug_raw else hypothesis.statement[:60],
            description=bug_raw.get("description", hypothesis.statement) if bug_raw else hypothesis.statement,
            severity=Severity(bug_raw.get("severity", "high")) if bug_raw else Severity.HIGH,
            confidence=confidence,
            hypothesis=hypothesis.statement,
            expected_behavior=experiment.expected_result,
            actual_behavior=bug_raw.get("actual_behavior", after_obs_text[:200]) if bug_raw else after_obs_text[:200],
            reproduction_steps=steps,
            reproduction_attempts=len(attempts),
            reproduction_successes=successes,
            evidence=evidence,
        )
        return bug

    async def _run_experiment(
        self,
        state: AgentState,
        experiment: Experiment,
        attempt_num: int,
    ) -> tuple[ReproductionAttempt, str, str]:
        """Execute one reproduction attempt. Returns (result, before_text, after_text)."""
        observations_before: list[str] = []
        observations_after: list[str] = []
        before_text = ""
        after_text = ""
        bug_triggered = False
        error_msg = None

        # We split actions into "before state change" and "after" by watching for checkout
        seen_cart_after_modify = False

        try:
            for step_idx, action in enumerate(experiment.actions):
                obs = await self.browser.execute(action)

                if action.action == ActionType.OBSERVE:
                    text_snippet = f"[{obs.url}] {obs.text[:200]}"
                    if not seen_cart_after_modify:
                        observations_before.append(text_snippet)
                        if "cart" in obs.url:
                            before_text = obs.text
                    else:
                        observations_after.append(text_snippet)
                        if "checkout" in obs.url:
                            after_text = obs.text

                if action.action in (ActionType.CLICK,) and "decrease" in (action.selector or ""):
                    seen_cart_after_modify = True

                # Detect the bug: cart shows lower price than checkout
                if "checkout" in obs.url and seen_cart_after_modify:
                    cart_prices = self._extract_prices(before_text)
                    checkout_prices = self._extract_prices(obs.text)
                    if cart_prices and checkout_prices:
                        if max(checkout_prices) > max(cart_prices):
                            bug_triggered = True
                            after_text = obs.text
                            observations_after.append(f"[{obs.url}] STALE TOTAL DETECTED: {obs.text[:150]}")

        except Exception as exc:
            error_msg = str(exc)
            log.error("[REPRODUCER] Experiment step failed: %s", exc)

        result = ReproductionAttempt(
            attempt_number=attempt_num,
            passed=bug_triggered,
            observations=observations_before + observations_after,
            error=error_msg,
        )
        return result, before_text, after_text

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _navigate_to(self, state: AgentState, url: str) -> None:
        action = AgentAction(action=ActionType.NAVIGATE, url=url, reason="Initial navigation")
        obs = await self.browser.execute(action)
        state.add_observation(obs)
        state.add_action(action)

    async def _observe(self, state: AgentState) -> Observation:
        obs = await self.browser.observe()
        state.add_observation(obs)
        return obs

    def _should_stop(self, state: AgentState) -> bool:
        if state.step_count >= self.max_steps:
            log.warning("[AGENT] Max steps (%d) reached", self.max_steps)
            state.status = AgentStatus.EXHAUSTED
            return True
        elapsed = time.time() - self._start_time
        if elapsed > self.max_runtime:
            log.warning("[AGENT] Max runtime (%.0fs) exceeded", self.max_runtime)
            state.status = AgentStatus.EXHAUSTED
            return True
        if state.status in (AgentStatus.CONFIRMED, AgentStatus.FAILED):
            return True
        return False

    def _extract_prices(self, text: str) -> list[float]:
        import re
        matches = re.findall(r"[₹$€£]?\s*(\d+(?:[,]\d+)*(?:\.\d+)?)", text)
        prices = []
        for m in matches:
            try:
                prices.append(float(m.replace(",", "")))
            except ValueError:
                pass
        return prices

    def _event(
        self,
        state: AgentState,
        event_type: EventType,
        message: str,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        event = AgentEvent(type=event_type, message=message, data=data or {})
        state.add_event(event)
        self._emit(event)
