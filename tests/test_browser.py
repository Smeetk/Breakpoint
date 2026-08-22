import asyncio


from backend.browser.controller import BrowserController
from backend.browser.manager import BrowserManager
from backend.browser.observer import PageObserver


async def main():
    manager = BrowserManager()

    try:
        page = await manager.start()

        browser = BrowserController(page)
        observer = PageObserver(page)

        await browser.navigate("https://example.com")

        observation = await observer.observe()

        print("\n--- PAGE OBSERVATION ---")
        print("URL:", observation["url"])
        print("Title:", observation["title"])
        print("Text:", observation["text"])
        print("Elements:", observation["interactive_elements"])

        await browser.screenshot("evidence/browser-test.png")

        print("\n✓ Browser test passed")

    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
