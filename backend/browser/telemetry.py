from typing import Any

from playwright.async_api import (
    ConsoleMessage,
    Page,
    Request,
    Response,
)


class BrowserTelemetry:
    def __init__(self, page: Page):
        self.page = page

        self.console_errors: list[str] = []

        self.failed_requests: list[
            dict[str, Any]
        ] = []

        self._attach_listeners()

    def _attach_listeners(self) -> None:
        self.page.on(
            "console",
            self._handle_console,
        )

        self.page.on(
            "requestfailed",
            self._handle_failed_request,
        )

        self.page.on(
            "response",
            self._handle_response,
        )

    def _handle_console(
        self,
        message: ConsoleMessage,
    ) -> None:
        if message.type == "error":
            self.console_errors.append(
                message.text
            )

    def _handle_failed_request(
        self,
        request: Request,
    ) -> None:
        self.failed_requests.append(
            {
                "url": request.url,
                "method": request.method,
                "failure": request.failure,
                "status": None,
            }
        )

    def _handle_response(
        self,
        response: Response,
    ) -> None:
        if response.status >= 400:
            self.failed_requests.append(
                {
                    "url": response.url,
                    "method": response.request.method,
                    "failure": None,
                    "status": response.status,
                }
            )

    def get_snapshot(self) -> dict[str, Any]:
        return {
            "console_errors": list(
                self.console_errors
            ),
            "failed_requests": list(
                self.failed_requests
            ),
        }

    def clear(self) -> None:
        self.console_errors.clear()
        self.failed_requests.clear()

