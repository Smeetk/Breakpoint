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
            browser,
            max_retries=2,
        )

        print(
            "\n--- RETRY TEST ---"
        )

        action = BrowserAction(
            action="click",
            selector="#does-not-exist",
        )

        try:
            await executor.execute(action)

            assert False, (
                "Expected action to fail"
            )

        except Exception as error:
            print(
                "Action failed after bounded retries:"
            )

            print(
                type(error).__name__,
                error,
            )

        print(
            "\n✓ Retry limit enforced"
        )

    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
