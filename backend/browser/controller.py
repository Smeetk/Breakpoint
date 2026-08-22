"""
BREAKPOINT — Browser Controller Interface
Person 2 implements this using Playwright.

This file defines the expected interface.
If Person 2's Playwright controller is in a different file, 
import it here and wrap it to match BrowserControllerProtocol.

REQUIRED: Implement all methods below.
Each method should return a dict matching the Observation schema or 
a raw dict that BrowserTools._normalise() can convert.

Expected observe() return format:
{
    "url": "http://...",
    "title": "Page Title",
    "text": "Visible page text",
    "elements": [
        {"selector": "button#submit", "text": "Submit", "tag": "button"},
        ...
    ],
    "errors": []  // console errors
}
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("breakpoint.controller")


class BrowserController:
    """
    Playwright-backed browser controller.
    Person 2: implement each method below.
    
    Usage:
        ctrl = BrowserController()
        await ctrl.start()  # launch browser
        obs = await ctrl.observe()
        ...
        await ctrl.stop()
    """

    def __init__(self) -> None:
        self._page = None  # Playwright page object
        self._browser = None

    async def start(self) -> None:
        """Launch Playwright browser. Call before any actions."""
        # Person 2: initialize playwright here
        # from playwright.async_api import async_playwright
        # self._pw = await async_playwright().start()
        # self._browser = await self._pw.chromium.launch(headless=False)
        # self._page = await self._browser.new_page()
        log.info("[CONTROLLER] Browser started (stub)")

    async def stop(self) -> None:
        """Close browser."""
        log.info("[CONTROLLER] Browser stopped (stub)")

    async def navigate(self, url: str) -> dict[str, Any]:
        log.info("[CONTROLLER] navigate → %s", url)
        # await self._page.goto(url)
        return {}

    async def click(self, selector: str) -> dict[str, Any]:
        log.info("[CONTROLLER] click %s", selector)
        # await self._page.click(selector)
        return {}

    async def type(self, selector: str, text: str) -> dict[str, Any]:
        log.info("[CONTROLLER] type '%s' into %s", text, selector)
        # await self._page.fill(selector, text)
        return {}

    async def back(self) -> dict[str, Any]:
        log.info("[CONTROLLER] back")
        # await self._page.go_back()
        return {}

    async def forward(self) -> dict[str, Any]:
        log.info("[CONTROLLER] forward")
        # await self._page.go_forward()
        return {}

    async def refresh(self) -> dict[str, Any]:
        log.info("[CONTROLLER] refresh")
        # await self._page.reload()
        return {}

    async def screenshot(self) -> str:
        log.info("[CONTROLLER] screenshot")
        path = "/tmp/screenshot.png"
        # await self._page.screenshot(path=path)
        return path

    async def observe(self) -> dict[str, Any]:
        """
        Return current page state.
        Person 2: use Playwright to extract URL, title, text, elements, errors.
        """
        log.info("[CONTROLLER] observe (stub)")
        # url = self._page.url
        # title = await self._page.title()
        # text = await self._page.inner_text("body")
        # elements = await self._extract_elements()
        # errors = []  # collect console errors via page.on("console", ...)
        # return {"url": url, "title": title, "text": text, "elements": elements, "errors": errors}
        return {
            "url": "",
            "title": "",
            "text": "",
            "elements": [],
            "errors": [],
        }
