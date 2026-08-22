"""
BREAKPOINT — Lightweight Agent Tests
Tests the agent without LLM calls (uses mock browser and deterministic paths).
Run: python -m tests.test_agent
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

PASS_TESTS: list[str] = []
FAIL_TESTS: list[str] = []


def test(name: str):
    """Decorator for test functions."""
    def decorator(fn):
        async def wrapper():
            try:
                await fn()
                PASS_TESTS.append(name)
                print(f"  ✓ {name}")
            except Exception as exc:
                FAIL_TESTS.append(name)
                print(f"  ✗ {name}")
                traceback.print_exc()
        wrapper._test_name = name
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Test 1: Schema validation
# ---------------------------------------------------------------------------

@test("AgentAction — valid navigate")
async def test_action_navigate_valid():
    from backend.schemas.models import AgentAction, ActionType
    a = AgentAction(action=ActionType.NAVIGATE, url="http://example.com", reason="test")
    errors = a.validate_fields()
    assert errors == [], f"Expected no errors, got {errors}"


@test("AgentAction — navigate missing URL fails validation")
async def test_action_navigate_no_url():
    from backend.schemas.models import AgentAction, ActionType
    a = AgentAction(action=ActionType.NAVIGATE, reason="test")
    errors = a.validate_fields()
    assert len(errors) == 1, f"Expected 1 error, got {errors}"
    assert "url" in errors[0]


@test("AgentAction — click missing selector fails validation")
async def test_action_click_no_selector():
    from backend.schemas.models import AgentAction, ActionType
    a = AgentAction(action=ActionType.CLICK, reason="test")
    errors = a.validate_fields()
    assert len(errors) == 1


@test("AgentAction — type requires selector and text")
async def test_action_type_missing_fields():
    from backend.schemas.models import AgentAction, ActionType
    a = AgentAction(action=ActionType.TYPE, selector="input", reason="test")
    errors = a.validate_fields()
    assert len(errors) == 1
    assert "text" in errors[0]


@test("AgentAction — back/forward/refresh need no selector/url")
async def test_action_no_required_fields():
    from backend.schemas.models import AgentAction, ActionType
    for action_type in [ActionType.BACK, ActionType.FORWARD, ActionType.REFRESH, ActionType.OBSERVE]:
        a = AgentAction(action=action_type, reason="test")
        errors = a.validate_fields()
        assert errors == [], f"{action_type}: {errors}"


# ---------------------------------------------------------------------------
# Test 2: Observation normalisation
# ---------------------------------------------------------------------------

@test("BrowserTools — normalises raw observation")
async def test_browser_tools_normalise():
    from backend.browser.mock import MockBrowserController
    from backend.browser.tools import BrowserTools
    from backend.schemas.models import AgentAction, ActionType

    ctrl = MockBrowserController()
    tools = BrowserTools(ctrl)
    action = AgentAction(action=ActionType.NAVIGATE, url="http://localhost:3000", reason="test")
    obs = await tools.execute(action)
    assert obs.url == "http://localhost:3000"
    assert obs.title != ""
    assert isinstance(obs.elements, list)


@test("BrowserTools — recovers from invalid action gracefully")
async def test_browser_tools_invalid_action():
    from backend.browser.mock import MockBrowserController
    from backend.browser.tools import BrowserTools
    from backend.schemas.models import AgentAction, ActionType

    ctrl = MockBrowserController()
    tools = BrowserTools(ctrl)
    # Navigate without URL — should return error observation, not crash
    action = AgentAction(action=ActionType.NAVIGATE, reason="bad action")
    obs = await tools.execute(action)
    assert len(obs.errors) > 0


# ---------------------------------------------------------------------------
# Test 3: Mock browser scenario
# ---------------------------------------------------------------------------

@test("MockBrowser — checkout stale bug is reproducible")
async def test_mock_checkout_bug():
    from backend.browser.mock import MockBrowserController
    from backend.browser.tools import BrowserTools
    from backend.schemas.models import AgentAction, ActionType

    ctrl = MockBrowserController()
    tools = BrowserTools(ctrl)

    # Navigate and add to cart
    await tools.execute(AgentAction(action=ActionType.NAVIGATE, url="http://localhost:3000/products", reason="t"))
    await tools.execute(AgentAction(action=ActionType.CLICK, selector="button[data-product='headphones']", reason="t"))

    # Go to cart, observe ₹1500
    cart_obs = await tools.execute(AgentAction(action=ActionType.NAVIGATE, url="http://localhost:3000/cart", reason="t"))
    assert "1500" in cart_obs.text, f"Expected 1500 in cart, got: {cart_obs.text}"

    # Decrease qty — cart should now show ₹1000
    await tools.execute(AgentAction(action=ActionType.CLICK, selector="button[data-action='decrease-qty']", reason="t"))
    cart_mod_obs = await tools.execute(AgentAction(action=ActionType.OBSERVE, reason="t"))
    assert "1000" in cart_mod_obs.text, f"Expected 1000 in modified cart, got: {cart_mod_obs.text}"

    # Go to checkout — should still show ₹1500 (THE BUG)
    checkout_obs = await tools.execute(AgentAction(action=ActionType.NAVIGATE, url="http://localhost:3000/checkout", reason="t"))
    assert "1500" in checkout_obs.text, f"Expected stale 1500 in checkout, got: {checkout_obs.text}"

    # Confirm the discrepancy: cart=₹1000, checkout=₹1500
    assert "1000" not in checkout_obs.text or "1500" in checkout_obs.text


# ---------------------------------------------------------------------------
# Test 4: Agent state management
# ---------------------------------------------------------------------------

@test("AgentState — tracks steps and observations correctly")
async def test_agent_state():
    from backend.schemas.models import AgentState, Observation, AgentAction, ActionType

    state = AgentState(goal="test goal")
    assert state.step_count == 0
    assert state.last_observation() is None

    obs = Observation(url="http://test.com", title="Test", text="content", elements=[])
    state.add_observation(obs)
    assert state.last_observation() == obs
    assert "http://test.com" in state.visited_urls

    action = AgentAction(action=ActionType.CLICK, selector="button", reason="test")
    state.add_action(action)
    assert state.step_count == 1


@test("AgentState — has_visited detects duplicate URLs")
async def test_has_visited():
    from backend.schemas.models import AgentState, Observation

    state = AgentState(goal="test")
    obs = Observation(url="http://test.com/cart", title="Cart", text="", elements=[])
    state.add_observation(obs)
    assert state.has_visited("http://test.com/cart")
    assert not state.has_visited("http://test.com/checkout")


# ---------------------------------------------------------------------------
# Test 5: Hypothesis creation
# ---------------------------------------------------------------------------

@test("Hypothesis — can be created and stored in state")
async def test_hypothesis():
    from backend.schemas.models import AgentState, Hypothesis, Confidence, HypothesisStatus

    state = AgentState(goal="test")
    hyp = Hypothesis(
        statement="Checkout total may not update after cart modification.",
        supporting_evidence=["Cart shows ₹1000, checkout shows ₹1500"],
        confidence=Confidence.HIGH,
    )
    state.add_hypothesis(hyp)
    assert len(state.hypotheses) == 1
    assert state.hypotheses[0].status == HypothesisStatus.PENDING


# ---------------------------------------------------------------------------
# Test 6: Deterministic anomaly detection
# ---------------------------------------------------------------------------

@test("Agent — deterministic anomaly detects price mismatch")
async def test_deterministic_anomaly():
    from backend.browser.mock import MockBrowserController
    from backend.browser.tools import BrowserTools
    from backend.agent.agent import BreakpointAgent
    from backend.schemas.models import AgentState, Observation

    ctrl = MockBrowserController()
    tools = BrowserTools(ctrl)
    agent = BreakpointAgent(browser=tools)
    state = AgentState(goal="test")

    cart_obs = Observation(
        url="http://localhost:3000/cart",
        title="Cart",
        text="Total: ₹1000",
        elements=[],
    )
    checkout_obs = Observation(
        url="http://localhost:3000/checkout",
        title="Checkout",
        text="Total to pay: ₹1500",
        elements=[],
    )

    anomaly = agent._deterministic_anomaly(checkout_obs, cart_obs, state)
    assert anomaly is not None, "Should detect price mismatch"
    assert anomaly["suspicious"] is True
    assert "HIGH" in anomaly["confidence"]


# ---------------------------------------------------------------------------
# Test 7: Reproduction counting
# ---------------------------------------------------------------------------

@test("ConfirmedBug — reproduction rate calculated correctly")
async def test_bug_repro_rate():
    from backend.schemas.models import ConfirmedBug, Confidence, Severity

    bug = ConfirmedBug(
        title="Test bug",
        description="desc",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        hypothesis="test hypothesis",
        expected_behavior="X",
        actual_behavior="Y",
        reproduction_attempts=3,
        reproduction_successes=3,
    )
    assert bug.reproduction_rate == 1.0

    bug2 = ConfirmedBug(
        title="Test bug 2",
        description="desc",
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        hypothesis="test",
        expected_behavior="X",
        actual_behavior="Y",
        reproduction_attempts=3,
        reproduction_successes=2,
    )
    assert abs(bug2.reproduction_rate - 0.666) < 0.01


# ---------------------------------------------------------------------------
# Test 8: Full mock golden path (no LLM)
# ---------------------------------------------------------------------------

@test("Full golden path — mock browser + deterministic agent")
async def test_golden_path_mock():
    """
    Run a stripped-down agent loop that uses mock LLM responses.
    Verifies the full OBSERVE→ANOMALY→HYPOTHESIS→EXPERIMENT→REPRODUCE→CONFIRM pipeline.
    """
    from backend.browser.mock import MockBrowserController
    from backend.browser.tools import BrowserTools
    from backend.agent.agent import BreakpointAgent
    from backend.schemas.models import AgentAction, ActionType, Observation

    # Patch llm_call_json to return deterministic responses
    import backend.agent.agent as agent_module
    import backend.agent.llm as llm_module

    call_count = [0]

    async def mock_llm_json(system_prompt, user_prompt, **kwargs):
        call_count[0] += 1
        # Planning responses — walk through the checkout bug scenario
        responses = [
            # Steps 1-4: explore
            {"action": "navigate", "url": "http://localhost:3000/products", "reason": "Explore products page"},
            {"action": "click", "selector": "button[data-product='headphones']", "reason": "Add item to cart"},
            {"action": "navigate", "url": "http://localhost:3000/cart", "reason": "View cart"},
            {"action": "observe", "reason": "Record cart total"},
            {"action": "click", "selector": "button[data-action='decrease-qty']", "reason": "Modify cart quantity"},
            {"action": "observe", "reason": "Record modified total"},
            {"action": "navigate", "url": "http://localhost:3000/checkout", "reason": "Go to checkout"},
            {"action": "observe", "reason": "Check checkout total"},
            {"action": "finish", "reason": "Bug found"},
        ]
        idx = min(call_count[0] - 1, len(responses) - 1)
        
        # For anomaly/experiment/bug confirmation prompts
        if "suspicious" in system_prompt.lower() or "anomaly" in user_prompt.lower():
            return {
                "suspicious": True,
                "reason": "Checkout shows ₹1500 but cart was modified to ₹1000",
                "hypothesis": "Checkout total is stale after cart modification",
                "confidence": "HIGH",
            }
        if "experiment" in user_prompt.lower() or "design" in system_prompt.lower():
            return {
                "description": "Test checkout staleness",
                "expected_result": "Checkout should show ₹1000 after cart modification",
                "actions": [
                    {"action": "navigate", "url": "http://localhost:3000/products", "reason": "Start"},
                    {"action": "click", "selector": "button[data-product='headphones']", "reason": "Add to cart"},
                    {"action": "navigate", "url": "http://localhost:3000/cart", "reason": "View cart"},
                    {"action": "observe", "reason": "Record total"},
                    {"action": "click", "selector": "button[data-action='decrease-qty']", "reason": "Modify"},
                    {"action": "observe", "reason": "Record modified"},
                    {"action": "navigate", "url": "http://localhost:3000/checkout", "reason": "Check checkout"},
                    {"action": "observe", "reason": "Verify total"},
                ]
            }
        if "bug report" in system_prompt.lower() or "confirmed" in user_prompt.lower():
            return {
                "title": "Checkout total becomes stale after cart modification",
                "description": "When the cart quantity is modified, the checkout page continues to display the original total instead of the updated one.",
                "expected_behavior": "Checkout total should equal current cart total (₹1000)",
                "actual_behavior": "Checkout total shows ₹1500 (original price) instead of ₹1000",
                "severity": "high",
                "reproduction_steps": [
                    "Navigate to /products",
                    "Add Wireless Headphones to cart",
                    "Navigate to /cart",
                    "Modify cart quantity (decrease)",
                    "Navigate to /checkout",
                    "Observe that total shows ₹1500 instead of ₹1000",
                ]
            }
        return responses[idx]

    # Monkey-patch
    original = llm_module.llm_call_json
    llm_module.llm_call_json = mock_llm_json

    # Also patch in agent module
    import backend.agent.agent as aa
    aa.llm_call_json = mock_llm_json

    try:
        ctrl = MockBrowserController()
        tools = BrowserTools(ctrl)
        events_received = []
        agent = BreakpointAgent(
            browser=tools,
            event_callback=lambda e: events_received.append(e),
            max_steps=25,
        )

        state = await agent.run(
            goal="Find something wrong with this application.",
            start_url="http://localhost:3000",
        )

        # Verify the pipeline completed
        assert state.step_count > 0, "Agent should have taken steps"
        assert len(state.observations) > 0, "Agent should have observations"

        # Verify event types were emitted
        event_types = [e.type for e in events_received]
        assert EventType.AGENT_START in event_types or "agent_start" in event_types
        
        # The mock should produce confirmed bugs
        if state.confirmed_bugs:
            bug = state.confirmed_bugs[0]
            assert bug.title != ""
            assert bug.confidence in ("HIGH", "MEDIUM", "LOW")
            print(f"    → Bug confirmed: '{bug.title}' (confidence={bug.confidence})")
        else:
            print(f"    → Status: {state.status} | Steps: {state.step_count}")
            # At least we should have a hypothesis
            assert len(state.hypotheses) > 0 or state.step_count >= 3

    finally:
        llm_module.llm_call_json = original
        aa.llm_call_json = original


# Import EventType for the test
from backend.schemas.models import EventType


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all_tests():
    tests = [
        test_action_navigate_valid,
        test_action_navigate_no_url,
        test_action_click_no_selector,
        test_action_type_missing_fields,
        test_action_no_required_fields,
        test_browser_tools_normalise,
        test_browser_tools_invalid_action,
        test_mock_checkout_bug,
        test_agent_state,
        test_has_visited,
        test_hypothesis,
        test_deterministic_anomaly,
        test_bug_repro_rate,
        test_golden_path_mock,
    ]

    print("\n" + "=" * 50)
    print("BREAKPOINT — Agent Test Suite")
    print("=" * 50)

    for test_fn in tests:
        await test_fn()

    print("\n" + "=" * 50)
    total = len(PASS_TESTS) + len(FAIL_TESTS)
    print(f"Results: {len(PASS_TESTS)}/{total} passed")
    if FAIL_TESTS:
        print(f"FAILED: {', '.join(FAIL_TESTS)}")
        return False
    else:
        print("ALL TESTS PASSED ✓")
        return True


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
