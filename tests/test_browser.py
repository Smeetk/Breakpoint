import asyncio
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from backend.browser.controller import BrowserController
from backend.browser.manager import BrowserManager
from backend.browser.observer import PageObserver


PORT = 8765


class TestServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Telemetry Test</title>
            </head>
            <body>
                <h1>Telemetry Test Page</h1>
                <button id="trigger-error">Trigger Error</button>

                <script>
                    console.error("TEST_CONSOLE_ERROR");

                    fetch("/api/failure")
                        .catch(() => {});
                </script>
            </body>
            </html>
            """

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html",
            )
            self.end_headers()

            self.wfile.write(body.encode())

        elif self.path == "/api/failure":
            self.send_response(500)
            self.send_header(
                "Content-Type",
                "application/json",
            )
            self.end_headers()

            self.wfile.write(
                b'{"error": "TEST_NETWORK_FAILURE"}'
            )

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_test_server():
    server = HTTPServer(
        ("127.0.0.1", PORT),
        TestServerHandler,
    )

    thread = Thread(
        target=server.serve_forever,
        daemon=True,
    )

    thread.start()

    return server


async def main():
    server = start_test_server()
    manager = BrowserManager()

    try:
        page = await manager.start()

        browser = BrowserController(page)
        observer = PageObserver(page)

        os.makedirs(
            "evidence",
            exist_ok=True,
        )

        await browser.navigate(
            f"http://127.0.0.1:{PORT}"
        )

        await page.wait_for_timeout(500)

        observation = await observer.observe()

        print("\n--- PAGE OBSERVATION ---")
        print("URL:", observation["url"])
        print("Title:", observation["title"])
        print("Text:", observation["text"])
        print(
            "Elements:",
            observation["interactive_elements"],
        )

        await browser.screenshot(
            "evidence/telemetry-test.png"
        )

        evidence = browser.get_evidence()

        print("\n--- EVIDENCE ---")

        for item in evidence:
            print(item)

        latest = evidence[-1]

        assert "TEST_CONSOLE_ERROR" in (
            latest["console_errors"]
        )

        assert any(
            request["url"].endswith("/api/failure")
            and request["status"] == 500
            for request in latest["failed_requests"]
        )

        print("\n✓ Console error captured")
        print("✓ Failed request captured")
        print("✓ Telemetry test passed")

    finally:
        await manager.stop()
        server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

