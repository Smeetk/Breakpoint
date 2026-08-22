import asyncio
import os

from backend.browser.controller import (
    BrowserController,
)
from backend.browser.manager import (
    BrowserManager,
)


async def main():
    manager = BrowserManager()

    try:
        page = await manager.start()

        browser = BrowserController(
            page,
            evidence_dir="evidence/test",
        )

        print(
            "\n--- AUTOMATIC EVIDENCE TEST ---"
        )

        await browser.navigate(
            "https://example.com"
        )

        evidence = (
            browser.get_evidence()
        )

        print(
            "\n--- EVIDENCE ---"
        )

        for item in evidence:
            print(item)

        assert len(evidence) == 1

        latest = evidence[-1]

        assert (
            latest["action"]
            == "navigate: https://example.com"
        )

        assert (
            latest["screenshot"] is not None
        )

        assert os.path.exists(
            latest["screenshot"]
        )

        print(
            "\n✓ Evidence automatically captured"
        )

        print(
            "✓ Screenshot exists"
        )

        print(
            "✓ Automatic evidence test passed"
        )

    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
