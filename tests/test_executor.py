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
            "\n--- ACTION 3: BLOCK UNSAFE URL ---"
        )

        unsafe_action = BrowserAction(
            action="navigate",
            url="javascript:alert(1)",
        )

        try:
            await executor.execute(
                unsafe_action
            )

            assert False, (
                "Unsafe action should "
                "have been rejected"
            )

        except ValueError as error:
            print(
                "Blocked as expected:",
                error,
            )

        assert (
            browser.page.url
            == "https://example.com/"
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
            "\n✓ Valid actions executed"
        )

        print(
            "✓ Unsafe action blocked"
        )

        print(
            "✓ Action executor test passed"
        )

    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
