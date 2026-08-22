"""
BREAKPOINT — Prompts
All LLM prompts in one place. Easy to tune.
"""

from __future__ import annotations

from backend.schemas.models import AgentState, Observation


# ---------------------------------------------------------------------------
# System Prompt — The Investigator Persona
# ---------------------------------------------------------------------------

INVESTIGATOR_SYSTEM_PROMPT = """You are BREAKPOINT — an elite autonomous security and quality investigation agent.

Your mission: discover real, reproducible bugs in web applications by acting like an expert penetration tester combined with a senior QA engineer.

You are NOT a browser assistant. You are a methodical AI investigator.

═══════════════════════════════════════
INVESTIGATION MINDSET
═══════════════════════════════════════

Think like a skeptical engineer who assumes the application is broken until proven otherwise.

Ask yourself constantly:
  - "What happens if I do this OUT OF ORDER?"
  - "What happens if I MODIFY state mid-workflow?"
  - "What happens if I go BACK and FORWARD unexpectedly?"
  - "What happens if I SUBMIT twice?"
  - "Does the UI reflect the ACTUAL backend state or a CACHED one?"
  - "What happens if I skip a step the app expects?"

═══════════════════════════════════════
EXPLORATION STRATEGY
═══════════════════════════════════════

Phase 1 — MAPPING: Visit every page, understand the structure.
Phase 2 — WORKFLOW: Execute the happy path completely.
Phase 3 — ADVERSARIAL: Deviate from the happy path in interesting ways:
  • Modify cart → return to checkout (stale state?)
  • Submit form → submit again (duplicate?)
  • Navigate back → forward (cache inconsistency?)
  • Refresh mid-checkout (session loss?)
  • Skip required steps (broken validation?)
  • Enter edge-case values (0 quantity, negative, very large)

Phase 4 — CONFIRM: Once suspicious, form hypothesis and test it 3 times.

═══════════════════════════════════════
WHAT COUNTS AS SUSPICIOUS
═══════════════════════════════════════

PRICE/VALUE BUGS:
  - Checkout total doesn't match cart total after modification
  - Discount applied twice or not at all
  - Price changes between pages without explanation

STATE CONSISTENCY BUGS:
  - Page shows stale data after a clear state change
  - Going back/forward reveals cached (wrong) state
  - Refreshing loses cart items but checkout still shows them

WORKFLOW BUGS:
  - Can reach checkout without items in cart
  - Can submit the same order twice
  - Can bypass required steps

VALIDATION BUGS:
  - Can enter quantity 0 or negative
  - Form accepts obviously invalid data
  - Error messages are missing or wrong

═══════════════════════════════════════
RESPONSE FORMAT — STRICT
═══════════════════════════════════════

ALWAYS respond with exactly one JSON object. No preamble, no explanation.

{
    "action": "<navigate|click|type|back|forward|refresh|observe|screenshot|finish>",
    "url": "<full URL or null>",
    "selector": "<exact CSS selector from elements list or null>",
    "text": "<text to type or null>",
    "reason": "<one crisp sentence — what you expect to learn from this>"
}

RULES:
- reason is REQUIRED. Make it investigative: explain what you're testing, not just what you're doing.
- selector MUST be copied exactly from the elements list you were shown.
- Never invent selectors. Never repeat an action 3 times in a row.
- finish when: a bug is confirmed (≥2/3 reproductions), OR you've exhausted all interesting scenarios."""


# ---------------------------------------------------------------------------
# Planning prompt
# ---------------------------------------------------------------------------

def build_planning_prompt(state: AgentState, observation: Observation) -> str:
    obs_summary = observation.compact_summary()

    visited = "\n".join(f"  - {u}" for u in state.visited_urls[-12:]) or "  (none yet)"

    recent_actions = " → ".join(
        f"{a.action}({(a.selector or a.url or '')[:40]})"
        for a in state.actions_taken[-8:]
    ) or "(none)"

    hyp_section = ""
    if state.hypotheses:
        active = [h for h in state.hypotheses if h.status == "pending"]
        if active:
            hyp_section = "\n\nACTIVE HYPOTHESES UNDER INVESTIGATION:\n" + "\n".join(
                f"  ▶ [{h.id}] {h.statement}  [confidence={h.confidence}]"
                for h in active[:3]
            )

    bugs_section = ""
    if state.confirmed_bugs:
        bugs_section = f"\n\nCONFIRMED BUGS THIS SESSION: {len(state.confirmed_bugs)}"
        for b in state.confirmed_bugs:
            bugs_section += f"\n  ✓ [{b.id}] {b.title}"
        bugs_section += "\n  → Continue exploring for more bugs."

    phase = _infer_phase(state)

    return f"""INVESTIGATION GOAL: {state.goal}

STEP {state.step_count} | PHASE: {phase}

━━━ CURRENT PAGE ━━━
{obs_summary}

━━━ VISITED URLS ━━━
{visited}

━━━ RECENT ACTIONS ━━━
{recent_actions}
{hyp_section}
{bugs_section}

━━━ YOUR TASK ━━━
Choose the single best next action to advance the investigation.
Think about what you haven't tried yet. Think adversarially.
Return ONLY the JSON action object."""


def _infer_phase(state: AgentState) -> str:
    if state.confirmed_bugs:
        return "CONTINUING (bug found, exploring for more)"
    if any(h.status == "pending" for h in state.hypotheses):
        return "HYPOTHESIZING"
    if len(state.visited_urls) < 3:
        return "MAPPING"
    if state.step_count < 8:
        return "WORKFLOW (happy path)"
    return "ADVERSARIAL (probing edge cases)"


# ---------------------------------------------------------------------------
# Anomaly analysis prompt
# ---------------------------------------------------------------------------

def build_anomaly_prompt(
    state: AgentState,
    current_obs: Observation,
    previous_obs: Observation,
    recent_context: str = "",
) -> str:
    return f"""You are an expert web application bug analyst.

INVESTIGATION GOAL: {state.goal}

PREVIOUS STATE:
  URL: {previous_obs.url}
  Title: {previous_obs.title}
  Content: {previous_obs.text[:500]}

CURRENT STATE:
  URL: {current_obs.url}
  Title: {current_obs.title}
  Content: {current_obs.text[:500]}
  Console Errors: {current_obs.errors}

RECENT ACTION SEQUENCE:
  {" → ".join(f"{a.action}({a.selector or a.url or ''})" for a in state.actions_taken[-6:])}

PATTERNS TO CHECK:
1. Are any prices/totals inconsistent between pages?
2. Is any information unexpectedly stale or cached?
3. Did an action produce no visible effect when it should have?
4. Are there duplicate entries or missing entries?
5. Did navigation (back/forward/refresh) cause inconsistent state?
6. Are there console errors that indicate something broke?

Respond ONLY with this JSON:
{{
    "suspicious": true/false,
    "bug_category": "price_inconsistency|stale_state|duplicate_submission|validation_bypass|navigation_bug|console_error|none",
    "reason": "<specific observation explaining WHY it's suspicious>",
    "hypothesis": "<precise, testable statement e.g. 'Checkout total is not recalculated after cart quantity is modified'>",
    "confidence": "LOW|MEDIUM|HIGH",
    "suggested_experiment": "<brief description of how to verify this>",
    "severity": "low|medium|high|critical"
}}"""


# ---------------------------------------------------------------------------
# Adversarial scenario generation
# ---------------------------------------------------------------------------

def build_scenario_prompt(state: AgentState, current_obs: Observation) -> str:
    already_tried = "\n".join(
        f"  - {a.action}({a.selector or a.url or ''})"
        for a in state.actions_taken[-15:]
    )

    return f"""You are designing the next adversarial investigation scenario.

APPLICATION EXPLORED SO FAR:
  Visited: {', '.join(state.visited_urls)}
  Steps taken: {state.step_count}
  Bugs found: {len(state.confirmed_bugs)}

CURRENT PAGE:
  URL: {current_obs.url}
  Elements: {', '.join(f"{e.tag}:{e.selector}" for e in current_obs.elements[:10])}

RECENTLY TRIED:
{already_tried}

Choose ONE untried adversarial scenario. Good options:
  A) Modify cart → proceed to checkout (stale price?)
  B) Submit order → press back → submit again (duplicate?)
  C) Add item → refresh page → continue to checkout (session state?)
  D) Navigate directly to checkout without cart items
  E) Change quantity to edge values (0, negative, very large)
  F) Log in → modify data → check if other user sees changes

Respond with JSON:
{{
    "scenario_name": "<short name>",
    "goal": "<what bug this might expose>",
    "actions": [
        {{"action": "<type>", "url": "<or null>", "selector": "<or null>", "text": "<or null>", "reason": "<why>"}}
    ]
}}

Use ONLY selectors from the elements list above. Keep it 4-8 steps."""


# ---------------------------------------------------------------------------
# Experiment design prompt
# ---------------------------------------------------------------------------

def build_experiment_prompt(hypothesis_statement: str, current_url: str, elements: list[str] = None) -> str:
    elements_hint = ""
    if elements:
        elements_hint = f"\nAVAILABLE SELECTORS (use only these):\n" + "\n".join(f"  {e}" for e in elements[:15])

    return f"""You are designing a precise browser experiment to test this hypothesis:

HYPOTHESIS: {hypothesis_statement}

CURRENT URL: {current_url}
{elements_hint}

Design a minimal, reproducible sequence of browser actions that:
1. Sets up the exact conditions that trigger the bug
2. Captures BOTH the "before" state (expected value) and "after" state (actual/buggy value)
3. Can be run identically 3 times in a row (no side effects between runs)

Respond with JSON:
{{
    "description": "<what this experiment specifically tests>",
    "expected_result": "<what the correct, bug-free behavior should be>",
    "buggy_behavior": "<what the bug causes to happen instead>",
    "actions": [
        {{"action": "<type>", "url": "<or null>", "selector": "<or null>", "text": "<or null>", "reason": "<what this step establishes>"}},
        ...
    ]
}}

Rules:
- 5-10 steps maximum
- Include observe steps to capture state before and after the bug trigger
- Start from a clean state (navigate to home or products first)
- Only use: navigate, click, type, back, forward, refresh, observe"""


# ---------------------------------------------------------------------------
# Bug confirmation / report prompt
# ---------------------------------------------------------------------------

def build_bug_confirmation_prompt(
    hypothesis: str,
    expected: str,
    buggy_behavior: str,
    observations_before: str,
    observations_after: str,
    repro_successes: int,
    repro_attempts: int,
    steps_taken: list[str] = None,
) -> str:
    steps_str = ""
    if steps_taken:
        steps_str = "\nACTUAL RECORDED STEPS:\n" + "\n".join(
            f"  {i+1}. {s}" for i, s in enumerate(steps_taken)
        )

    return f"""You are writing a professional bug report for a confirmed, reproducible bug.

HYPOTHESIS CONFIRMED: {hypothesis}

REPRODUCTION RATE: {repro_successes}/{repro_attempts} attempts reproduced the bug

OBSERVATIONS BEFORE BUG TRIGGER:
{observations_before}

OBSERVATIONS SHOWING THE BUG:
{observations_after}

EXPECTED BEHAVIOR: {expected}
BUGGY BEHAVIOR: {buggy_behavior}
{steps_str}

Write a clear, professional bug report. Be specific — include actual values observed (e.g. "₹1000" not "the updated price").

Respond ONLY with this JSON:
{{
    "title": "<concise bug title, max 60 chars, specific e.g. 'Checkout total not updated after cart quantity change'>",
    "description": "<3-4 sentences. What the bug is, when it occurs, what impact it has on users.>",
    "root_cause_hypothesis": "<one sentence technical guess at the root cause>",
    "expected_behavior": "<specific: what should happen with actual values>",
    "actual_behavior": "<specific: what actually happens with actual values>",
    "severity": "low|medium|high|critical",
    "impact": "<business/user impact in one sentence>",
    "reproduction_steps": [
        "<step 1 — be specific>",
        "<step 2>",
        "..."
    ]
}}"""


# ---------------------------------------------------------------------------
# Playwright test generation prompt
# ---------------------------------------------------------------------------

def build_playwright_test_prompt(
    bug: dict,
    recorded_actions: list[dict],
    base_url: str,
) -> str:
    actions_str = "\n".join(
        f"  {i+1}. {a.get('action')} "
        f"{'→ ' + a.get('url','') if a.get('url') else ''}"
        f"{'→ ' + a.get('selector','') if a.get('selector') else ''}"
        f"{'→ type: ' + a.get('text','') if a.get('text') else ''}"
        f" // {a.get('reason','')}"
        for i, a in enumerate(recorded_actions)
    )

    return f"""Generate a Playwright test that reproduces this confirmed bug.

BUG: {bug.get('title')}
DESCRIPTION: {bug.get('description')}
EXPECTED: {bug.get('expected_behavior')}
ACTUAL (BUG): {bug.get('actual_behavior')}

BASE URL: {base_url}

RECORDED ACTIONS (in order):
{actions_str}

Generate a complete Playwright test file. The test should:
1. Execute the exact steps that reproduce the bug
2. Assert the EXPECTED (correct) behavior
3. The assertion SHOULD FAIL because the bug exists — proving the bug
4. Include a clear comment explaining what's broken

Return ONLY this JSON (the test code as a string):
{{
    "filename": "bug_{bug.get('id', 'BUG-001').lower().replace('-','_')}.spec.js",
    "test_code": "<complete playwright test as a single string with \\n for newlines>"
}}"""
