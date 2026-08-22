from typing import Any, Awaitable, Callable

from backend.browser.config import BrowserConfig
from backend.browser.controller import BrowserController
from backend.browser.schemas import BrowserAction
from backend.browser.validator import ActionValidator


class ActionExecutor:
    """
    Executes validated browser actions with
    bounded retries.
    """

    def __init__(
        self,
        browser: BrowserController,
        validator: ActionValidator | None = None,
        max_retries: int = (
            BrowserConfig.DEFAULT_MAX_RETRIES
        ),
    ):
        self.browser = browser

        self.validator = (
            validator or ActionValidator()
        )

        self.max_retries = max_retries

    async def execute(
        self,
        action: BrowserAction,
    ) -> dict[str, Any]:

        self.validator.validate(action)

        async def run_action():
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

        last_error = None

        for attempt in range(
            self.max_retries + 1
        ):
            try:
                await run_action()

                return {
                    "success": True,
                    "action": action.action,
                    "url": self.browser.page.url,
                    "attempts": attempt + 1,
                }

            except Exception as error:
                last_error = error

                if attempt >= self.max_retries:
                    raise

        raise last_error
