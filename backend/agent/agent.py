"""
BREAKPOINT — Core Investigation Agent (v2)
Full pipeline: OBSERVE → REASON → ACT → ANOMALY → HYPOTHESIS → EXPERIMENT → REPRODUCE → CONFIRM

Key upgrades over v1:
  - Continues after first bug (finds multiple bugs per run)
  - Adversarial scenario generation via LLM
  - Richer anomaly detection (6 bug categories)
  - Playwright test auto-generated on bug confirmation
  - Phase-aware exploration (MAPPING → WORKFLOW → ADVERSARIAL)
  - Better loop management (hypothesis queue, not just one at a time)
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
    build_scenario_prompt,
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
# Configurable limits
# ---------------------------------------------------------------------------

MAX_STEPS = 50
MAX_RUNTIME_SECONDS = 360
REPRODUCTION_ATTEMPTS = 3
MIN_REPRODUCTIONS_FOR_CONFIRM = 2
MAX_BUGS_PER_RUN = 3          # keep exploring after first bug
MIN_STEPS_BEFORE_HYPOTHESIS = 5  # explore a bit before jumping to hypotheses


# ---------------------------------------------------------------------------
# Deterministic fallback scenarios
# (used when LLM is unavailable — guarantees demo always works)
# ---------------------------------------------------------------------------

FALLBACK_SCENARIOS: list[list[dict[str, Any]]] = [
    # Scenario A: Add → modify → checkout (price staleness)
    [
        {"action": "navigate", "url": "http://localhost:3000", "reason": "Start fresh at home"},
        {"action": "navigate", "url": "http://localhost:3000/products", "reason": "Browse product catalog"},
        {"action": "click", "selector": "button[data-product='headphones']", "reason": "Add Wireless Headphones to cart"},
        {"action": "navigate", "url": "http://localhost:3000/cart", "reason": "View cart to confirm item added"},
        {"action": "observe", "reason": "Record cart total before modification"},
        {"action": "click", "selector": "button[data-action='decrease-qty']", "reason": "Decrease quantity — this should update the total"},
        {"action": "observe", "reason": "Record updated cart total after quantity change"},
        {"action": "navigate", "url": "http://localhost:3000/checkout", "reason": "Proceed to checkout — compare total"},
        {"action": "observe", "reason": "Check if checkout total matches the modified cart total"},
    ],
    # Scenario B: Back/forward navigation state
    [
        {"action": "navigate", "url": "http://localhost:3000/products", "reason": "Go to products"},
        {"action": "click", "selector": "button[data-product='headphones']", "reason": "Add to cart"},
        {"action": "navigate", "url": "http://localhost:3000/checkout", "reason": "Go directly to checkout"},
        {"action": "observe", "reason": "Record checkout state"},
        {"action": "back", "reason": "Go back — testing browser history state"},
        {"action": "navigate", "url": "http://localhost:3000/cart", "reason": "Modify cart"},
        {"action": "click", "selector": "button[data-action='decrease-qty']", "reason": "Change cart quantity"},
        {"action": "forward", "reason": "Return to checkout via forward navigation"},
        {"action": "observe", "reason": "Does checkout reflect the cart change?"},
    ],
]


# ---------------------------------------------------------------------------
# BreakpointAgent
# ---------------------------------------------------------------------------


class BreakpointAgent:
    """
    Autonomous browser investigation agent.

    LLM: planning, anomaly reasoning, hypothesis generation,
         experiment design, scenario generation, bug report writing.

    Python: execution, validation, state, limits, retries,
            reproduction, confidence, test generation.
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
        self._test_output_dir: str = "/tmp/breakpoint_tests"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, goal: str, start_url: str = "http://localhost:3000") -> AgentState:
        """Run the full investigation. Returns final AgentState."""
        self._start_time = time.time()
        state = AgentState(goal=goal, status=AgentStatus.EXPLORING)

        log.info("[AGENT] ═══════════════════════════════════════")
        log.info("[AGENT] BREAKPOINT Investigation Started")
        log.info("[AGENT] Goal: %s", goal)
        log.info("[AGENT] ═══════════════════════════════════════")

        self._event(state, EventType.AGENT_START, "Investigation started", {
            "goal": goal, "url": start_url,
        })

        # Initial navigation
        await self._navigate_to(state, start_url)
        initial_obs = await self._observe(state)

        # Main loop
        pending_hypothesis: Optional[Hypothesis] = None

        while not self._should_stop(state):
            state.step_count += 1
            log.info(
                "[AGENT] Step %d | Phase: %s | URL: %s | Bugs: %d",
                state.step_count, state.status.value, state.current_url,
                len(state.confirmed_bugs),
            )

            prev_obs = state.last_observation()
            current_obs = prev_obs or initial_obs

            # ── 1. Plan next action ────────────────────────────────────
            action = await self._plan_action(state, current_obs)

            # ── 2. Execute ────────────────────────────────────────────
            obs = await self.browser.execute(action)
            state.add_observation(obs)
            state.add_action(action)

            self._event(state, EventType.AGENT_ACTION,
                        f"{action.action}: {action.reason}",
                        {"action": action.action, "reason": action.reason, "url": obs.url})

            if action.action == ActionType.FINISH:
                log.info("[AGENT] Agent chose to finish.")
                break

            # ── 3. Anomaly detection ──────────────────────────────────
            if prev_obs and obs.url and state.step_count >= MIN_STEPS_BEFORE_HYPOTHESIS:
                anomaly = await self._check_anomaly(state, obs, prev_obs)

                if anomaly.get("suspicious") and not pending_hypothesis:
                    log.info("[AGENT] ⚠  Anomaly: %s", anomaly.get("reason", ""))
                    self._event(state, EventType.ANOMALY,
                                anomaly.get("reason", "Suspicious behavior detected"),
                                anomaly)

                    pending_hypothesis = self._create_hypothesis(state, anomaly)
                    state.add_hypothesis(pending_hypothesis)
                    state.status = AgentStatus.HYPOTHESIZING

            # ── 4. Test pending hypothesis ────────────────────────────
            if (
                pending_hypothesis
                and pending_hypothesis.status == HypothesisStatus.PENDING
                and state.step_count >= MIN_STEPS_BEFORE_HYPOTHESIS + 1
            ):
                bug = await self._test_hypothesis(state, pending_hypothesis)

                if bug:
                    state.confirmed_bugs.append(bug)
                    state.status = AgentStatus.CONFIRMED
                    self._event(state, EventType.BUG_CONFIRMED,
                                f"BUG CONFIRMED: {bug.title}",
                                bug.to_summary())
                    log.info("[BUG] ✓ Confirmed [%s]: %s | confidence=%s",
                             bug.id, bug.title, bug.confidence)

                    # Generate Playwright test
                    await self._generate_test(state, bug)

                    # Keep exploring if under bug limit AND LLM is available
                    from backend.agent.llm import _llm_disabled
                    if len(state.confirmed_bugs) < MAX_BUGS_PER_RUN and not _llm_disabled:
                        log.info("[AGENT] Bug limit not reached (%d/%d). Continuing.",
                                 len(state.confirmed_bugs), MAX_BUGS_PER_RUN)
                        state.status = AgentStatus.EXPLORING
                        pending_hypothesis = None
                        await self._navigate_to(state, start_url)
                    else:
                        # LLM disabled or bug limit reached — we're done
                        break
                else:
                    pending_hypothesis.status = HypothesisStatus.REJECTED
                    log.info("[AGENT] Hypothesis rejected: %s", pending_hypothesis.statement)
                    state.status = AgentStatus.EXPLORING
                    pending_hypothesis = None

        # Termination
        if state.status not in (AgentStatus.CONFIRMED, AgentStatus.FAILED):
            state.status = AgentStatus.EXHAUSTED

        self._event(state, EventType.AGENT_FINISH,
                    f"Investigation complete — {len(state.confirmed_bugs)} bug(s) confirmed",
                    {
                        "status": state.status,
                        "confirmed_bugs": len(state.confirmed_bugs),
                        "steps": state.step_count,
                        "elapsed_s": round(time.time() - self._start_time, 1),
                    })

        log.info("[AGENT] ═══════════════════════════════════════")
        log.info("[AGENT] Investigation complete")
        log.info("[AGENT] Status: %s | Steps: %d | Bugs: %d | Time: %.1fs",
                 state.status, state.step_count, len(state.confirmed_bugs),
                 time.time() - self._start_time)
        log.info("[AGENT] ═══════════════════════════════════════")
        return state

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _plan_action(self, state: AgentState, obs: Observation) -> AgentAction:
        """Ask LLM for next action → validate → fallback if needed."""
        prompt = build_planning_prompt(state, obs)
        raw = await llm_call_json(
            system_prompt=INVESTIGATOR_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=400,
        )

        if raw:
            action = self._parse_action(raw, state)
            if action:
                return action

        log.warning("[AGENT] LLM planning failed. Using deterministic fallback.")
        return self._fallback_action(state)

    def _parse_action(self, raw: dict[str, Any], state: AgentState) -> Optional[AgentAction]:
        try:
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
                if action.action == ActionType.NAVIGATE:
                    return AgentAction(action=ActionType.OBSERVE, reason="Recovered: missing URL")
                return None
            # Anti-loop: reject if repeating same non-useful action 3x
            recent = state.recent_action_types(4)
            if (
                recent.count(action.action) >= 3
                and action.action not in (ActionType.OBSERVE, ActionType.FINISH)
            ):
                return None
            return action
        except (ValidationError, Exception) as exc:
            log.debug("[AGENT] Action parse error: %s", exc)
            return None

    def _fallback_action(self, state: AgentState) -> AgentAction:
        """Stateful deterministic fallback — walks the bug-discovery scenario."""
        scenario = [AgentAction(**a) for a in FALLBACK_SCENARIOS[0]]
        idx = min(state.step_count - 1, len(scenario) - 1)
        log.warning("[AGENT] Fallback step %d: %s", idx, scenario[idx].reason)
        return scenario[idx]

    # ------------------------------------------------------------------
    # Anomaly detection — two layers
    # ------------------------------------------------------------------

    async def _check_anomaly(
        self, state: AgentState, current: Observation, previous: Observation
    ) -> dict[str, Any]:
        # Layer 1: fast deterministic checks
        det = self._deterministic_anomaly(current, previous, state)
        if det:
            return det

        # Layer 2: LLM semantic check (only on interesting pages)
        if self._is_interesting_page(current.url):
            result = await llm_call_json(
                system_prompt="You are a web security and QA analyst. Return only JSON.",
                user_prompt=build_anomaly_prompt(state, current, previous),
                temperature=0.1,
                max_tokens=400,
            )
            if result and result.get("suspicious"):
                return result

        return {"suspicious": False}

    def _is_interesting_page(self, url: str) -> bool:
        keywords = ["checkout", "cart", "payment", "order", "confirm",
                    "account", "profile", "admin", "dashboard", "receipt"]
        return any(kw in url.lower() for kw in keywords)

    def _deterministic_anomaly(
        self, current: Observation, previous: Observation, state: AgentState
    ) -> Optional[dict[str, Any]]:
        """
        Fast, zero-LLM anomaly patterns.
        Catches the most common bug categories without any API call.
        """
        curr_prices = self._extract_prices(current.text)
        prev_prices = self._extract_prices(previous.text)

        # ── Price inconsistency (checkout vs cart) ────────────────────
        if "checkout" in current.url and ("cart" in previous.url or prev_prices):
            if curr_prices and prev_prices:
                curr_max = max(curr_prices)
                prev_max = max(prev_prices)
                if curr_max != prev_max and curr_max > 0 and prev_max > 0:
                    direction = "higher" if curr_max > prev_max else "lower"
                    return {
                        "suspicious": True,
                        "bug_category": "price_inconsistency",
                        "reason": (
                            f"Checkout total ({_fmt_price(curr_max)}) is {direction} than "
                            f"the previous cart total ({_fmt_price(prev_max)}). "
                            f"Likely stale checkout state."
                        ),
                        "hypothesis": (
                            f"Checkout total is not recalculated after cart is modified. "
                            f"Cart shows {_fmt_price(prev_max)} but checkout shows {_fmt_price(curr_max)}."
                        ),
                        "confidence": "HIGH",
                        "severity": "high",
                        "suggested_experiment": "Modify cart quantity then navigate to checkout and compare totals.",
                    }

        # ── Same page, same URL, but price changed unexpectedly ───────
        if current.url == previous.url and curr_prices and prev_prices:
            curr_max = max(curr_prices)
            prev_max = max(prev_prices)
            if curr_max != prev_max and "refresh" in [a.action for a in state.actions_taken[-2:]]:
                return {
                    "suspicious": True,
                    "bug_category": "stale_state",
                    "reason": f"Price changed on refresh ({_fmt_price(prev_max)} → {_fmt_price(curr_max)}) without user action.",
                    "hypothesis": "Page is showing inconsistent price data across refreshes.",
                    "confidence": "MEDIUM",
                    "severity": "medium",
                    "suggested_experiment": "Refresh the page multiple times and compare prices.",
                }

        # ── Console errors appeared ───────────────────────────────────
        new_errors = [e for e in current.errors if e not in previous.errors]
        if new_errors:
            return {
                "suspicious": True,
                "bug_category": "console_error",
                "reason": f"New console errors after action: {new_errors[:2]}",
                "hypothesis": "The last action caused unexpected application errors.",
                "confidence": "MEDIUM",
                "severity": "medium",
                "suggested_experiment": "Repeat the last action and observe if errors recur.",
            }

        # ── Title disappeared (broken render) ────────────────────────
        if previous.title and not current.title and current.url == previous.url:
            return {
                "suspicious": True,
                "bug_category": "stale_state",
                "reason": "Page title disappeared while staying on the same URL — possible partial render failure.",
                "hypothesis": "The page is failing to fully re-render after a state change.",
                "confidence": "LOW",
                "severity": "low",
                "suggested_experiment": "Refresh and observe if the title returns.",
            }

        return None

    # ------------------------------------------------------------------
    # Hypothesis creation
    # ------------------------------------------------------------------

    def _create_hypothesis(self, state: AgentState, anomaly: dict[str, Any]) -> Hypothesis:
        conf_map = {"LOW": Confidence.LOW, "MEDIUM": Confidence.MEDIUM, "HIGH": Confidence.HIGH}
        conf = conf_map.get(str(anomaly.get("confidence", "MEDIUM")).upper(), Confidence.MEDIUM)

        evidence = []
        if state.observations:
            last = state.last_observation()
            if last:
                evidence.append(f"Observed at {last.url}: {last.text[:200]}")

        hyp = Hypothesis(
            statement=anomaly.get("hypothesis", anomaly.get("reason", "Suspicious behavior detected")),
            supporting_evidence=evidence,
            confidence=conf,
        )

        self._event(state, EventType.HYPOTHESIS,
                    f"Hypothesis: {hyp.statement}",
                    {
                        "hypothesis_id": hyp.id,
                        "statement": hyp.statement,
                        "confidence": conf.value if hasattr(conf, 'value') else str(conf),
                        "bug_category": anomaly.get("bug_category", "unknown"),
                        "severity": anomaly.get("severity", "medium"),
                    })
        return hyp

    # ------------------------------------------------------------------
    # Hypothesis testing (experiment + reproduction)
    # ------------------------------------------------------------------

    async def _test_hypothesis(
        self, state: AgentState, hypothesis: Hypothesis
    ) -> Optional[ConfirmedBug]:
        """Design experiment → reproduce → confirm or reject."""
        state.status = AgentStatus.EXPERIMENTING

        # Design the experiment
        elements = [f"{e.selector}" for e in (state.last_observation() or Observation(url="")).elements]
        exp = await self._design_experiment(state, hypothesis, elements)
        state.experiments.append(experiment := exp)

        self._event(state, EventType.EXPERIMENT_START,
                    f"Testing: {hypothesis.statement[:80]}",
                    {"hypothesis_id": hypothesis.id, "experiment_id": experiment.id,
                     "steps": len(experiment.actions)})

        # Reproduce
        state.status = AgentStatus.REPRODUCING
        return await self._reproduce(state, hypothesis, experiment)

    async def _design_experiment(
        self, state: AgentState, hypothesis: Hypothesis, elements: list[str]
    ) -> Experiment:
        prompt = build_experiment_prompt(hypothesis.statement, state.current_url, elements)
        raw = await llm_call_json(
            system_prompt="You design precise browser test sequences. Respond only in JSON.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=700,
        )

        actions: list[AgentAction] = []
        if raw and "actions" in raw:
            for a in raw["actions"]:
                try:
                    act = AgentAction(**{k: v for k, v in a.items() if v is not None})
                    if not act.validate_fields():
                        actions.append(act)
                except Exception:
                    pass

        if not actions:
            log.warning("[AGENT] LLM experiment failed. Using fallback scenario.")
            for a in FALLBACK_SCENARIOS[0]:
                try:
                    actions.append(AgentAction(**a))
                except Exception:
                    pass

        return Experiment(
            hypothesis_id=hypothesis.id,
            description=raw.get("description", "Test hypothesis") if raw else "Fallback scenario",
            actions=actions,
            expected_result=raw.get("expected_result", "Consistent application state") if raw else "Consistent state",
        )

    # ------------------------------------------------------------------
    # Reproduction
    # ------------------------------------------------------------------

    async def _reproduce(
        self, state: AgentState, hypothesis: Hypothesis, experiment: Experiment
    ) -> Optional[ConfirmedBug]:
        attempts: list[ReproductionAttempt] = []
        before_text = after_text = ""

        for i in range(1, REPRODUCTION_ATTEMPTS + 1):
            log.info("[REPRODUCER] Attempt %d/%d", i, REPRODUCTION_ATTEMPTS)
            self._event(state, EventType.REPRODUCTION,
                        f"Reproduction {i}/{REPRODUCTION_ATTEMPTS}",
                        {"attempt": i, "total": REPRODUCTION_ATTEMPTS})

            result, bt, at = await self._run_experiment(experiment, attempt_num=i)
            attempts.append(result)
            if bt:
                before_text = bt
            if at:
                after_text = at

            log.info("[REPRODUCER] Attempt %d: %s", i, "✓ PASS" if result.passed else "✗ FAIL")
            self._event(state, EventType.REPRODUCTION,
                        f"Reproduction {i}/{REPRODUCTION_ATTEMPTS}: {'PASS ✓' if result.passed else 'FAIL ✗'}",
                        {"attempt": i, "passed": result.passed})

        successes = sum(1 for a in attempts if a.passed)
        log.info("[REPRODUCER] Result: %d/%d", successes, len(attempts))

        if successes < MIN_REPRODUCTIONS_FOR_CONFIRM:
            return None

        confidence = Confidence.HIGH if successes == REPRODUCTION_ATTEMPTS else Confidence.MEDIUM
        hypothesis.status = HypothesisStatus.CONFIRMED

        # Generate professional bug report via LLM
        bug_raw = await llm_call_json(
            system_prompt="You write precise, professional bug reports. Respond only in JSON.",
            user_prompt=build_bug_confirmation_prompt(
                hypothesis=hypothesis.statement,
                expected=experiment.expected_result,
                buggy_behavior=after_text[:300],
                observations_before=before_text[:300],
                observations_after=after_text[:300],
                repro_successes=successes,
                repro_attempts=len(attempts),
                steps_taken=[a.reason for a in experiment.actions if a.reason],
            ),
            temperature=0.1,
            max_tokens=800,
        )

        steps = bug_raw.get("reproduction_steps", []) if bug_raw else []
        if not steps:
            steps = [a.reason for a in experiment.actions if a.reason]

        evidence = []
        for a in attempts:
            evidence.extend(a.observations[:2])

        return ConfirmedBug(
            title=bug_raw.get("title", f"Bug: {hypothesis.statement[:55]}") if bug_raw else hypothesis.statement[:60],
            description=bug_raw.get("description", hypothesis.statement) if bug_raw else hypothesis.statement,
            severity=Severity(bug_raw.get("severity", "high")) if bug_raw else Severity.HIGH,
            confidence=confidence,
            hypothesis=hypothesis.statement,
            expected_behavior=bug_raw.get("expected_behavior", experiment.expected_result) if bug_raw else experiment.expected_result,
            actual_behavior=bug_raw.get("actual_behavior", after_text[:200]) if bug_raw else after_text[:200],
            reproduction_steps=steps,
            reproduction_attempts=len(attempts),
            reproduction_successes=successes,
            evidence=evidence,
        )

    async def _run_experiment(
        self, experiment: Experiment, attempt_num: int
    ) -> tuple[ReproductionAttempt, str, str]:
        observations_log: list[str] = []
        before_text = after_text = ""
        bug_triggered = False
        error_msg = None
        seen_modification = False

        try:
            for action in experiment.actions:
                obs = await self.browser.execute(action)

                snippet = f"[{obs.url}] {obs.text[:200]}"

                if action.action == ActionType.OBSERVE:
                    if not seen_modification:
                        observations_log.append(f"BEFORE: {snippet}")
                        if "cart" in obs.url:
                            before_text = obs.text
                    else:
                        observations_log.append(f"AFTER: {snippet}")
                        if "checkout" in obs.url:
                            after_text = obs.text

                # Mark modification point
                if (action.action == ActionType.CLICK
                        and action.selector
                        and any(kw in action.selector.lower()
                                for kw in ["decrease", "remove", "delete", "qty", "quantity"])):
                    seen_modification = True

                # Detect bug: checkout price higher than post-modification cart price
                if "checkout" in obs.url and seen_modification:
                    cart_prices = self._extract_prices(before_text)
                    checkout_prices = self._extract_prices(obs.text)
                    if cart_prices and checkout_prices:
                        if max(checkout_prices) > max(cart_prices):
                            bug_triggered = True
                            after_text = obs.text
                            observations_log.append(
                                f"BUG DETECTED: checkout={_fmt_price(max(checkout_prices))} "
                                f"cart={_fmt_price(max(cart_prices))}"
                            )

        except Exception as exc:
            error_msg = str(exc)
            log.error("[REPRODUCER] Step error: %s", exc)

        return (
            ReproductionAttempt(
                attempt_number=attempt_num,
                passed=bug_triggered,
                observations=observations_log,
                error=error_msg,
            ),
            before_text,
            after_text,
        )

    # ------------------------------------------------------------------
    # Playwright test generation
    # ------------------------------------------------------------------

    async def _generate_test(self, state: AgentState, bug: ConfirmedBug) -> None:
        try:
            from backend.agent.testgen import generate_playwright_test
            path = await generate_playwright_test(
                bug=bug,
                recorded_actions=state.actions_taken,
                output_dir=self._test_output_dir,
            )
            if path:
                self._event(state, EventType.AGENT_ACTION,
                            f"Playwright test generated → {path}",
                            {"type": "playwright_test_generated", "path": path, "bug_id": bug.id})
                log.info("[TESTGEN] ✓ Test written to: %s", path)
        except Exception as exc:
            log.warning("[TESTGEN] Test generation failed: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _navigate_to(self, state: AgentState, url: str) -> None:
        action = AgentAction(action=ActionType.NAVIGATE, url=url, reason="Navigate to start URL")
        obs = await self.browser.execute(action)
        state.add_observation(obs)
        state.add_action(action)

    async def _observe(self, state: AgentState) -> Observation:
        obs = await self.browser.observe()
        state.add_observation(obs)
        return obs

    def _should_stop(self, state: AgentState) -> bool:
        if state.step_count >= self.max_steps:
            log.warning("[AGENT] Max steps reached (%d)", self.max_steps)
            state.status = AgentStatus.EXHAUSTED
            return True
        elapsed = time.time() - self._start_time
        if elapsed > self.max_runtime:
            log.warning("[AGENT] Max runtime exceeded (%.0fs)", elapsed)
            state.status = AgentStatus.EXHAUSTED
            return True
        if state.status == AgentStatus.FAILED:
            return True
        return False

    def _extract_prices(self, text: str) -> list[float]:
        import re
        matches = re.findall(r"[₹$€£]?\s*(\d+(?:[,]\d+)*(?:\.\d+)?)", text)
        prices = []
        for m in matches:
            try:
                v = float(m.replace(",", ""))
                if v >= 1:  # ignore tiny numbers (1px etc)
                    prices.append(v)
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


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _fmt_price(value: float) -> str:
    """Format a number as a price string."""
    return f"₹{value:,.0f}" if value == int(value) else f"₹{value:,.2f}"
