from playwright.async_api import Page

from backend.browser.config import BrowserConfig
from backend.browser.evidence import Evidence
from backend.browser.telemetry import BrowserTelemetry


class BrowserController:
    def __init__(
        self,
        page: Page,
        timeout_ms: int = BrowserConfig.DEFAULT_TIMEOUT_MS,
    ):
        self.page = page

        self.timeout_ms = timeout_ms

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
            timeout=self.timeout_ms,
        )

    async def click(
        self,
        selector: str,
    ) -> None:
        self.current_action = (
            f"click: {selector}"
        )

        self.telemetry.clear()

        locator = self.page.locator(
            selector
        )

        await locator.wait_for(
            state="visible",
            timeout=self.timeout_ms,
        )

        await locator.click(
            timeout=self.timeout_ms
        )

    async def type(
        self,
        selector: str,
        text: str,
    ) -> None:
        self.current_action = (
            f"type: {selector}"
        )

        self.telemetry.clear()

        locator = self.page.locator(
            selector
        )

        await locator.wait_for(
            state="visible",
            timeout=self.timeout_ms,
        )

        await locator.fill(
            text,
            timeout=self.timeout_ms,
        )

    async def back(self) -> None:
        self.current_action = "back"

        self.telemetry.clear()

        await self.page.go_back(
            wait_until="domcontentloaded",
            timeout=self.timeout_ms,
        )

    async def forward(self) -> None:
        self.current_action = "forward"

        self.telemetry.clear()

        await self.page.go_forward(
            wait_until="domcontentloaded",
            timeout=self.timeout_ms,
        )

    async def refresh(self) -> None:
        self.current_action = "refresh"

        self.telemetry.clear()

        await self.page.reload(
            wait_until="domcontentloaded",
            timeout=self.timeout_ms,
        )

    async def screenshot(
        self,
        path: str,
    ) -> None:
        await self.page.screenshot(
            path=path,
            full_page=True,
            timeout=self.timeout_ms,
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
