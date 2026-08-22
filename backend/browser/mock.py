"""
BREAKPOINT — Mock Browser Controller
For testing the agent without Playwright.
Returns scripted observations that simulate the e-commerce bug scenario.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger("breakpoint.mock")


# ---------------------------------------------------------------------------
# Scripted observation sequences
# ---------------------------------------------------------------------------

_SHOP_HOME = {
    "url": "http://localhost:3000",
    "title": "ShopDemo — Home",
    "text": "Welcome to ShopDemo. Browse our products.",
    "elements": [
        {"selector": "a[href='/products']", "text": "Browse Products", "tag": "a"},
        {"selector": "a[href='/cart']", "text": "Cart (0)", "tag": "a"},
        {"selector": "a[href='/login']", "text": "Login", "tag": "a"},
    ],
    "errors": [],
}

_PRODUCTS_PAGE = {
    "url": "http://localhost:3000/products",
    "title": "ShopDemo — Products",
    "text": "Wireless Headphones ₹1500. Add to cart.",
    "elements": [
        {"selector": "button[data-product='headphones']", "text": "Add to Cart — ₹1500", "tag": "button"},
        {"selector": "a[href='/cart']", "text": "Cart (0)", "tag": "a"},
    ],
    "errors": [],
}

_CART_PAGE_1_ITEM = {
    "url": "http://localhost:3000/cart",
    "title": "ShopDemo — Cart",
    "text": "Cart: Wireless Headphones x1 = ₹1500. Total: ₹1500",
    "elements": [
        {"selector": "button[data-action='decrease-qty']", "text": "−", "tag": "button"},
        {"selector": "button[data-action='increase-qty']", "text": "+", "tag": "button"},
        {"selector": "span[data-testid='cart-total']", "text": "₹1500", "tag": "span"},
        {"selector": "a[href='/checkout']", "text": "Proceed to Checkout", "tag": "a"},
    ],
    "errors": [],
}

# After clicking decrease-qty, the cart total updates to ₹1000
_CART_PAGE_MODIFIED = {
    "url": "http://localhost:3000/cart",
    "title": "ShopDemo — Cart",
    "text": "Cart: Wireless Headphones x1 = ₹1000 (sale). Total: ₹1000",
    "elements": [
        {"selector": "button[data-action='decrease-qty']", "text": "−", "tag": "button"},
        {"selector": "button[data-action='increase-qty']", "text": "+", "tag": "button"},
        {"selector": "span[data-testid='cart-total']", "text": "₹1000", "tag": "span"},
        {"selector": "a[href='/checkout']", "text": "Proceed to Checkout", "tag": "a"},
    ],
    "errors": [],
}

# THE BUG: checkout still shows ₹1500 after cart was modified to ₹1000
_CHECKOUT_STALE = {
    "url": "http://localhost:3000/checkout",
    "title": "ShopDemo — Checkout",
    "text": "Order Summary: Wireless Headphones = ₹1500. Total to pay: ₹1500. Pay Now.",
    "elements": [
        {"selector": "span[data-testid='checkout-total']", "text": "₹1500", "tag": "span"},
        {"selector": "button[data-testid='pay-btn']", "text": "Pay ₹1500", "tag": "button"},
    ],
    "errors": [],
}

_CHECKOUT_FRESH = {
    "url": "http://localhost:3000/checkout",
    "title": "ShopDemo — Checkout",
    "text": "Order Summary: Wireless Headphones = ₹1500. Total to pay: ₹1500. Pay Now.",
    "elements": [
        {"selector": "span[data-testid='checkout-total']", "text": "₹1500", "tag": "span"},
        {"selector": "button[data-testid='pay-btn']", "text": "Pay ₹1500", "tag": "button"},
    ],
    "errors": [],
}


class MockBrowserController:
    """
    Scripted fake browser that simulates the checkout-staleness bug.

    Navigation trace that produces the bug:
      1. / → browse products → add to cart → go to cart
      2. cart: observe ₹1500 total
      3. cart: click decrease-qty → total updates to ₹1000
      4. checkout: observe ₹1500 (stale!)  ← the bug
    """

    def __init__(self) -> None:
        self._current_url = "http://localhost:3000"
        self._cart_modified = False
        self._history: list[str] = ["http://localhost:3000"]
        self._history_idx = 0

    # ------------------------------------------------------------------
    async def navigate(self, url: str) -> dict[str, Any]:
        log.debug("[MOCK] navigate → %s", url)
        await asyncio.sleep(0.05)
        self._current_url = url
        self._history = self._history[: self._history_idx + 1]
        self._history.append(url)
        self._history_idx = len(self._history) - 1
        return {}

    async def click(self, selector: str) -> dict[str, Any]:
        log.debug("[MOCK] click %s", selector)
        await asyncio.sleep(0.05)
        if "add-to-cart" in selector or "product='headphones'" in selector:
            # Adds item to cart
            pass
        elif "decrease-qty" in selector:
            self._cart_modified = True
        elif "increase-qty" in selector:
            self._cart_modified = False
        return {}

    async def type(self, selector: str, text: str) -> dict[str, Any]:
        log.debug("[MOCK] type '%s' into %s", text, selector)
        await asyncio.sleep(0.05)
        return {}

    async def back(self) -> dict[str, Any]:
        log.debug("[MOCK] back")
        await asyncio.sleep(0.05)
        if self._history_idx > 0:
            self._history_idx -= 1
            self._current_url = self._history[self._history_idx]
        return {}

    async def forward(self) -> dict[str, Any]:
        log.debug("[MOCK] forward")
        await asyncio.sleep(0.05)
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self._current_url = self._history[self._history_idx]
        return {}

    async def refresh(self) -> dict[str, Any]:
        log.debug("[MOCK] refresh")
        await asyncio.sleep(0.05)
        return {}

    async def screenshot(self) -> str:
        log.debug("[MOCK] screenshot")
        await asyncio.sleep(0.02)
        return f"/tmp/screenshot_{self._current_url.replace('/', '_')}.png"

    async def observe(self) -> dict[str, Any]:
        log.debug("[MOCK] observe → %s", self._current_url)
        await asyncio.sleep(0.02)
        return self._get_page(self._current_url)

    # ------------------------------------------------------------------
    def _get_page(self, url: str) -> dict[str, Any]:
        url = url.rstrip("/")
        base = "http://localhost:3000"

        if url in (base, base + "/"):
            return dict(_SHOP_HOME)
        elif url == base + "/products":
            return dict(_PRODUCTS_PAGE)
        elif url == base + "/cart":
            if self._cart_modified:
                return dict(_CART_PAGE_MODIFIED)
            return dict(_CART_PAGE_1_ITEM)
        elif url == base + "/checkout":
            # THE BUG: checkout always shows the original price ₹1500
            # regardless of cart modifications
            return dict(_CHECKOUT_STALE)
        else:
            return {
                "url": url,
                "title": "ShopDemo",
                "text": "Page content.",
                "elements": [{"selector": "a[href='/']", "text": "Home", "tag": "a"}],
                "errors": [],
            }
