from typing import Any

from backend.browser.controller import BrowserController
from backend.browser.schemas import BrowserAction


class ActionExecutor:
    """
    Executes validated browser actions.

    BrowserAction is the contract between the agent
    and the browser execution layer.
    """

    def __init__(self, browser: BrowserController):
        self.browser = browser

    async def execute(
        self,
        action: BrowserAction,
    ) -> dict[str, Any]:

        if action.action == "navigate":
            if not action.url:
                raise ValueError(
                    "Navigate action requires 'url'"
                )

            await self.browser.navigate(action.url)

        elif action.action == "click":
            if not action.selector:
                raise ValueError(
                    "Click action requires 'selector'"
                )

            await self.browser.click(action.selector)

        elif action.action == "type":
            if not action.selector:
                raise ValueError(
                    "Type action requires 'selector'"
                )

            if action.text is None:
                raise ValueError(
                    "Type action requires 'text'"
                )

            await self.browser.type(
                action.selector,
                action.text,
            )

        elif action.action == "back":
            await self.browser.back()

        elif action.action == "forward":
            await self.browser.forward()

        elif action.action == "refresh":
            await self.browser.refresh()

        elif action.action == "screenshot":
            if not action.path:
                raise ValueError(
                    "Screenshot action requires 'path'"
                )

            await self.browser.screenshot(
                action.path
            )

        return {
            "success": True,
            "action": action.action,
            "url": self.browser.page.url,
        }
