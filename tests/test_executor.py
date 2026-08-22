import asyncio

from backend.browser.controller import (
    BrowserController,
)
from backend.browser.executor import (
    ActionExecutor,
)
from backend.browser.manager import (
    BrowserManager,
)
from backend.browser.schemas import (
    BrowserAction,
)


async def main():
    manager = BrowserManager()

    try:
        page = await manager.start()

        browser = BrowserController(page)

        executor = ActionExecutor(
            browser
        )

        print(
            "\n--- ACTION 1: NAVIGATE ---"
        )

        navigate_action = BrowserAction(
            action="navigate",
            url="https://example.com",
        )

        result = await executor.execute(
            navigate_action
        )

        print(result)

        assert result["success"] is True

        assert (
            result["action"]
            == "navigate"
        )

        print(
            "\n--- ACTION 2: SCREENSHOT ---"
        )

        screenshot_action = BrowserAction(
            action="screenshot",
            path="evidence/executor-test.png",
        )

        result = await executor.execute(
            screenshot_action
        )

        print(result)

        assert result["success"] is True

        assert (
            result["action"]
            == "screenshot"
        )

        print(
            "\n--- EVIDENCE ---"
        )

        for evidence in (
            browser.get_evidence()
        ):
            print(evidence)

        assert (
            len(
                browser.get_evidence()
            )
            == 1
        )

        print(
            "\n✓ Action executor test passed"
        )

    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())

