"""
BREAKPOINT — Anomaly Detector
Deterministic anomaly checks to complement LLM analysis.
Used by the agent, can also be called standalone.
"""

from __future__ import annotations

import re
from typing import Optional

from backend.schemas.models import Observation


def extract_prices(text: str) -> list[float]:
    """Extract all numeric price values from text."""
    matches = re.findall(r"[₹$€£]?\s*(\d+(?:[,]\d+)*(?:\.\d+)?)", text)
    prices = []
    for m in matches:
        try:
            val = float(m.replace(",", ""))
            if val > 0:
                prices.append(val)
        except ValueError:
            pass
    return prices


def check_price_consistency(obs_a: Observation, obs_b: Observation) -> Optional[dict]:
    """
    Check if prices between two pages are inconsistent.
    Returns anomaly dict or None.
    """
    prices_a = extract_prices(obs_a.text)
    prices_b = extract_prices(obs_b.text)

    if not prices_a or not prices_b:
        return None

    max_a = max(prices_a)
    max_b = max(prices_b)

    # Suspicious if checkout (b) shows significantly different total than cart (a)
    if abs(max_a - max_b) > 1 and max_b > max_a:
        return {
            "type": "price_inconsistency",
            "page_a": obs_a.url,
            "page_b": obs_b.url,
            "price_a": max_a,
            "price_b": max_b,
            "description": f"Price mismatch: {obs_a.url} shows {max_a}, {obs_b.url} shows {max_b}",
        }
    return None


def check_console_errors(obs: Observation) -> Optional[dict]:
    """Check for unexpected console errors."""
    if obs.errors:
        return {
            "type": "console_errors",
            "url": obs.url,
            "errors": obs.errors,
            "description": f"Console errors on {obs.url}: {obs.errors[:3]}",
        }
    return None
