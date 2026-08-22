from playwright.async_api import Page

from backend.browser.evidence import Evidence
from backend.browser.telemetry import BrowserTelemetry


class BrowserController:
    def __init__(self, page: Page):
        self.page = page

        self.evidence: list[Evidence] = []

        self.telemetry = BrowserTelemetry(page)

        self.current_action: str = "unknown"

    async def navigate(
        self,
        url: str,
    ) -> None:
        self.current_action = (
            f"navigate: {url}"
        )

        self.telemetry.clear()

        await self.page.goto(
            url,
            wait_until="domcontentloaded",
        )

    async def click(
        self,
        selector: str,
    ) -> None:
        self.current_action = (
            f"click: {selector}"
        )

        self.telemetry.clear()

        await self.page.locator(
            selector
        ).click()

    async def type(
        self,
        selector: str,
        text: str,
    ) -> None:
        self.current_action = (
            f"type: {selector}"
        )

        self.telemetry.clear()

        await self.page.locator(
            selector
        ).fill(text)

    async def back(self) -> None:
        self.current_action = "back"

        self.telemetry.clear()

        await self.page.go_back(
            wait_until="domcontentloaded"
        )

    async def forward(self) -> None:
        self.current_action = "forward"

        self.telemetry.clear()

        await self.page.go_forward(
            wait_until="domcontentloaded"
        )

    async def refresh(self) -> None:
        self.current_action = "refresh"

        self.telemetry.clear()

        await self.page.reload(
            wait_until="domcontentloaded"
        )

    async def screenshot(
        self,
        path: str,
    ) -> None:
        await self.page.screenshot(
            path=path,
            full_page=True,
        )

        telemetry = (
            self.telemetry.get_snapshot()
        )

        self.evidence.append(
            Evidence(
                action=self.current_action,
                url=self.page.url,
                screenshot=path,
                console_errors=(
                    telemetry[
                        "console_errors"
                    ]
                ),
                failed_requests=(
                    telemetry[
                        "failed_requests"
                    ]
                ),
            )
        )

        self.telemetry.clear()

    def get_evidence(
        self,
    ) -> list[dict]:
        return [
            item.to_dict()
            for item in self.evidence
        ]
