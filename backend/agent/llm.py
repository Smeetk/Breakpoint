"""
BREAKPOINT — LLM Abstraction
Provider-agnostic interface. Uses OpenAI by default.
Configure via OPENAI_API_KEY / OPENAI_BASE_URL environment variables.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from openai import AsyncOpenAI

log = logging.getLogger("breakpoint.llm")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = os.getenv("BREAKPOINT_MODEL", "gpt-4o-mini")
_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL")
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _client


# ---------------------------------------------------------------------------
# Core LLM call
# ---------------------------------------------------------------------------


async def llm_call(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 800,
) -> str:
    """
    Single LLM call. Returns raw text response.
    Raises on hard API errors; callers should handle retries.
    """
    model = model or _DEFAULT_MODEL
    client = get_client()

    log.debug("[LLM] Calling %s (temp=%.1f, max_tok=%d)", model, temperature, max_tokens)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content or ""
    log.debug("[LLM] Response length: %d chars", len(text))
    return text


# ---------------------------------------------------------------------------
# JSON extraction with retry
# ---------------------------------------------------------------------------


async def llm_call_json(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 800,
    max_retries: int = 2,
) -> dict[str, Any]:
    """
    Call LLM and parse JSON. Retries on parse failure.
    Returns {} on final failure (never raises).
    """
    attempt = 0
    last_raw = ""
    current_user_prompt = user_prompt

    while attempt <= max_retries:
        try:
            raw = await llm_call(
                system_prompt=system_prompt,
                user_prompt=current_user_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            last_raw = raw
            parsed = _extract_json(raw)
            if parsed is not None:
                return parsed
            # JSON not found — retry with correction
            current_user_prompt = (
                f"{user_prompt}\n\n"
                f"IMPORTANT: Your previous response was not valid JSON:\n{raw}\n"
                f"Return ONLY a raw JSON object. No markdown, no explanation."
            )
            attempt += 1
        except Exception as exc:
            log.error("[LLM] API error attempt %d: %s", attempt, exc)
            attempt += 1

    log.warning("[LLM] All %d attempts failed. Last raw: %s", max_retries + 1, last_raw[:200])
    return {}


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """Extract JSON from LLM output (handles markdown fences, stray text)."""
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try stripping markdown fences
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
