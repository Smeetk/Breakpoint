"""
BREAKPOINT — Browser Tools Abstraction
The agent calls only these tools. Never Playwright directly.

Interface contract with Person 2:
  BrowserController must implement:
    async navigate(url: str) -> dict
    async click(selector: str) -> dict
    async type(selector: str, text: str) -> dict
    async back() -> dict
    async forward() -> dict
    async refresh() -> dict
    async observe() -> dict
    async screenshot() -> str (path)
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol

from backend.schemas.models import AgentAction, ActionType, Observation, PageElement

log = logging.getLogger("breakpoint.tools")


# ---------------------------------------------------------------------------
# Protocol — what Person 2 must implement
# ---------------------------------------------------------------------------


class BrowserControllerProtocol(Protocol):
    async def navigate(self, url: str) -> dict[str, Any]: ...
    async def click(self, selector: str) -> dict[str, Any]: ...
    async def type(self, selector: str, text: str) -> dict[str, Any]: ...
    async def back(self) -> dict[str, Any]: ...
    async def forward(self) -> dict[str, Any]: ...
    async def refresh(self) -> dict[str, Any]: ...
    async def observe(self) -> dict[str, Any]: ...
    async def screenshot(self) -> str: ...


# ---------------------------------------------------------------------------
# BrowserTools — translates AgentAction → controller calls → Observation
# ---------------------------------------------------------------------------


class BrowserTools:
    """
    Bridges the agent planner and the browser controller.
    Handles action dispatch, error recovery, and observation normalisation.
    """

    def __init__(self, controller: BrowserControllerProtocol) -> None:
        self._ctrl = controller

    async def execute(self, action: AgentAction) -> Observation:
        """Execute an action and return a normalised Observation."""
        errors = action.validate_fields()
        if errors:
            log.warning("[TOOLS] Invalid action %s: %s", action.action, errors)
            return self._error_observation(f"Invalid action: {'; '.join(errors)}")

        try:
            raw = await self._dispatch(action)
            obs = self._normalise(raw)
            log.info("[BROWSER] %s executed → %s", action.action, obs.url or "ok")
            return obs
        except Exception as exc:
            log.error("[TOOLS] Action %s failed: %s", action.action, exc)
            return self._error_observation(str(exc))

    async def observe(self) -> Observation:
        """Force a fresh observation without performing any action."""
        try:
            raw = await self._ctrl.observe()
            return self._normalise(raw)
        except Exception as exc:
            log.error("[TOOLS] Observe failed: %s", exc)
            return self._error_observation(str(exc))

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, action: AgentAction) -> dict[str, Any]:
        t = action.action

        if t == ActionType.NAVIGATE:
            result = await self._ctrl.navigate(action.url)  # type: ignore[arg-type]
            # After navigation always grab fresh observation
            obs_raw = await self._ctrl.observe()
            return obs_raw

        elif t == ActionType.CLICK:
            await self._ctrl.click(action.selector)  # type: ignore[arg-type]
            obs_raw = await self._ctrl.observe()
            return obs_raw

        elif t == ActionType.TYPE:
            await self._ctrl.type(action.selector, action.text)  # type: ignore[arg-type]
            obs_raw = await self._ctrl.observe()
            return obs_raw

        elif t == ActionType.BACK:
            await self._ctrl.back()
            obs_raw = await self._ctrl.observe()
            return obs_raw

        elif t == ActionType.FORWARD:
            await self._ctrl.forward()
            obs_raw = await self._ctrl.observe()
            return obs_raw

        elif t == ActionType.REFRESH:
            await self._ctrl.refresh()
            obs_raw = await self._ctrl.observe()
            return obs_raw

        elif t == ActionType.OBSERVE:
            return await self._ctrl.observe()

        elif t == ActionType.SCREENSHOT:
            path = await self._ctrl.screenshot()
            obs_raw = await self._ctrl.observe()
            obs_raw["screenshot_path"] = path
            return obs_raw

        elif t == ActionType.FINISH:
            # FINISH is handled by the agent loop, not here
            obs_raw = await self._ctrl.observe()
            return obs_raw

        else:
            return {}

    # ------------------------------------------------------------------
    # Normalisation — convert raw browser dict → Observation
    # ------------------------------------------------------------------

    def _normalise(self, raw: dict[str, Any]) -> Observation:
        """
        Convert whatever format Person 2's controller returns into our Observation.
        Handles both our format and possible alternate key names.
        """
        if not raw:
            return Observation(url="", title="", text="", elements=[])

        url = raw.get("url", raw.get("current_url", ""))
        title = raw.get("title", raw.get("page_title", ""))
        text = raw.get("text", raw.get("body_text", raw.get("content", "")))
        errors = raw.get("errors", raw.get("console_errors", []))
        screenshot_path = raw.get("screenshot_path")

        raw_elements = raw.get("elements", raw.get("interactive_elements", []))
        elements: list[PageElement] = []
        for el in raw_elements:
            if isinstance(el, dict):
                elements.append(
                    PageElement(
                        selector=el.get("selector", el.get("id", "")),
                        text=el.get("text", el.get("label", "")),
                        tag=el.get("tag", el.get("type", "")),
                        element_type=el.get("element_type", el.get("type", "")),
                        visible=el.get("visible", True),
                        attributes=el.get("attributes", {}),
                    )
                )
            elif isinstance(el, PageElement):
                elements.append(el)

        return Observation(
            url=url,
            title=title,
            text=text,
            elements=elements,
            errors=errors if isinstance(errors, list) else [str(errors)],
            screenshot_path=screenshot_path,
        )

    def _error_observation(self, msg: str) -> Observation:
        return Observation(url="", title="", text="", elements=[], errors=[msg])
