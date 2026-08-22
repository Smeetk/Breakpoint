from typing import Any

from backend.browser.controller import BrowserController
from backend.browser.schemas import BrowserAction
from backend.browser.validator import ActionValidator


class ActionExecutor:
    """
    Executes validated browser actions.

    Every action passes through ActionValidator
    before reaching the browser.
    """

    def __init__(
        self,
        browser: BrowserController,
        validator: ActionValidator | None = None,
    ):
        self.browser = browser
        self.validator = validator or ActionValidator()

    async def execute(
        self,
        action: BrowserAction,
    ) -> dict[str, Any]:

        # Safety / validity check
        self.validator.validate(action)

        if action.action == "navigate":
            await self.browser.navigate(
                action.url
            )

        elif action.action == "click":
            await self.browser.click(
                action.selector
            )

        elif action.action == "type":
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
            await self.browser.screenshot(
                action.path
            )

        return {
            "success": True,
            "action": action.action,
            "url": self.browser.page.url,
        }
