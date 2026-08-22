from playwright.async_api import Browser, Page, Playwright, async_playwright


class BrowserManager:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.page: Page | None = None

    async def start(self) -> Page:
        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=self.headless
        )

        self.page = await self.browser.new_page()

        return self.page

    async def stop(self) -> None:
        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        self.page = None
        self.browser = None
        self.playwright = None
