from playwright.async_api import Page


class BrowserController:
    def __init__(self, page: Page):
        self.page = page

    async def navigate(self, url: str) -> None:
        await self.page.goto(
            url,
            wait_until="domcontentloaded",
        )

    async def click(self, selector: str) -> None:
        await self.page.locator(selector).click()

    async def type(self, selector: str, text: str) -> None:
        await self.page.locator(selector).fill(text)

    async def back(self) -> None:
        await self.page.go_back(
            wait_until="domcontentloaded",
        )

    async def forward(self) -> None:
        await self.page.go_forward(
            wait_until="domcontentloaded",
        )

    async def refresh(self) -> None:
        await self.page.reload(
            wait_until="domcontentloaded",
        )

    async def screenshot(self, path: str) -> None:
        await self.page.screenshot(
            path=path,
            full_page=True,
        )
