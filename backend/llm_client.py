"""Small Anthropic-compatible Messages API client for backend LLM calls."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import requests


DEFAULT_MODEL = "claude-fable-5"
DEFAULT_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"


class LLMConfigError(RuntimeError):
    """Raised when required LLM environment variables are missing."""


class LLMRequestError(RuntimeError):
    """Raised when the Anthropic-compatible API call fails."""


def configured_model(default: str = DEFAULT_MODEL) -> str:
    return os.getenv("ANTHROPIC_MODEL") or default


def configured_news_model(default: str = DEFAULT_MODEL) -> str:
    return os.getenv("ANTHROPIC_NEWS_MODEL") or configured_model(default)


def is_llm_configured() -> bool:
    return bool(_auth_token())


async def send_message(
    *,
    system_message: str,
    user_message: str,
    model: str | None = None,
    max_tokens: int = 1200,
    temperature: float = 0.2,
    timeout_seconds: int = 90,
) -> str:
    """Send one Messages API request and return the text response."""
    return await asyncio.to_thread(
        _send_message_sync,
        system_message=system_message,
        user_message=user_message,
        model=model or configured_model(),
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )


def _auth_token() -> str | None:
    return os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")


def _endpoint() -> str:
    base = (os.getenv("ANTHROPIC_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/v1/messages"


def _headers(*, x_api_key_fallback: bool = False) -> dict[str, str]:
    token = _auth_token()
    if not token:
        raise LLMConfigError("ANTHROPIC_AUTH_TOKEN puuttuu.")

    headers = {
        "Content-Type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
    }
    if os.getenv("ANTHROPIC_AUTH_TOKEN") and not x_api_key_fallback:
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers["x-api-key"] = token
    return headers


def _send_message_sync(
    *,
    system_message: str,
    user_message: str,
    model: str,
    max_tokens: int,
    temperature: float,
    timeout_seconds: int,
) -> str:
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_message,
        "messages": [{"role": "user", "content": user_message}],
    }

    url = _endpoint()
    response = requests.post(
        url,
        headers=_headers(),
        json=payload,
        timeout=(10, timeout_seconds),
    )

    if response.status_code in (401, 403) and os.getenv("ANTHROPIC_AUTH_TOKEN"):
        response = requests.post(
            url,
            headers=_headers(x_api_key_fallback=True),
            json=payload,
            timeout=(10, timeout_seconds),
        )

    if response.status_code >= 400:
        # SECURITY: Redact secrets from error messages
        detail = response.text.replace("\n", " ")[:500]
        # Import here to avoid circular dependency
        import re
        # Redact common secret patterns
        detail = re.sub(
            r'(api[_-]?key|token|secret|authorization|password|bearer)[\"\s:=]+[^\s\"]+',
            r'\1=REDACTED',
            detail,
            flags=re.IGNORECASE
        )
        raise LLMRequestError(f"HTTP {response.status_code}: {detail}")

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMRequestError(f"Invalid JSON response: {exc}") from exc

    return _extract_text(data)


def _extract_text(data: dict[str, Any]) -> str:
    content = data.get("content")
    if isinstance(content, list):
        chunks: list[str] = []
        for block in content:
            if isinstance(block, str):
                chunks.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        if chunks:
            return "\n".join(chunks)

    # Tolerate proxies that expose OpenAI- or completion-like response shapes.
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        msg = (choices[0] or {}).get("message") or {}
        if isinstance(msg.get("content"), str):
            return msg["content"]

    for key in ("text", "completion"):
        if isinstance(data.get(key), str):
            return data[key]

    raise LLMRequestError("Response did not contain text content.")
