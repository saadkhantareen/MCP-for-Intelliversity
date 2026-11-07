"""Thin OpenAI-compatible client for the Agnes AI API.

Agnes exposes the standard Chat Completions shape at
``https://apihub.agnes-ai.com/v1`` so no vendor SDK is required - plain
``requests`` is enough and keeps the dependency surface small.

Configuration (all read from the environment / ``.env``):
    AGNES_API_KEY    required - Bearer token
    AGNES_BASE_URL   optional - defaults to https://apihub.agnes-ai.com/v1
    AGNES_MODEL      optional - defaults to agnes-2.5-flash
    AGNES_TIMEOUT    optional - per-request timeout in seconds (default 45)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_MODEL = "agnes-2.5-flash"

# Agnes free tier rate-limits aggressively (HTTP 429), so the client backs off
# and retries instead of dropping straight to the regex fallback.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
MAX_BACKOFF = 20.0

logger = logging.getLogger(__name__)


class AgnesError(RuntimeError):
    """Raised when the Agnes API cannot return a usable payload."""

    def __init__(self, message: str, *, retryable: bool = False, retry_after: float | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


def api_key() -> str | None:
    key = (os.getenv("AGNES_API_KEY") or "").strip()
    return key or None


def base_url() -> str:
    return (os.getenv("AGNES_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def model() -> str:
    return (os.getenv("AGNES_MODEL") or DEFAULT_MODEL).strip()


def _timeout() -> float:
    try:
        return float(os.getenv("AGNES_TIMEOUT") or 45)
    except ValueError:
        return 45.0


def _post(path: str, payload: dict) -> dict:
    key = api_key()
    if not key:
        raise AgnesError("AGNES_API_KEY is not set")

    url = f"{base_url()}{path}"
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=_timeout(),
        )
    except requests.RequestException as exc:
        raise AgnesError(f"Agnes request failed: {exc}", retryable=True) from exc

    if response.status_code != 200:
        retry_after = _retry_after(response)
        raise AgnesError(
            f"Agnes HTTP {response.status_code}: {response.text[:300]}",
            retryable=response.status_code in RETRYABLE_STATUSES,
            retry_after=retry_after,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise AgnesError(f"Agnes returned non-JSON body: {response.text[:300]}") from exc


def _retry_after(response) -> float | None:
    """Seconds the server asked us to wait, when it said so."""
    header = response.headers.get("Retry-After")
    if not header:
        return None
    try:
        return max(0.0, float(header))
    except ValueError:
        return None


def _strip_fences(text: str) -> str:
    """Agnes occasionally wraps output in ```json fences - strip them."""
    text = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1).strip()
    return text


def _content_from(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise AgnesError(f"Agnes returned no choices: {json.dumps(data)[:300]}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if not content:
        finish = choices[0].get("finish_reason")
        if finish == "length":
            raise AgnesError("Agnes hit the max_tokens budget before answering")
        raise AgnesError(f"Agnes returned empty content (finish_reason={finish})")
    return content


def chat(
    messages: list[dict],
    *,
    json_mode: bool = False,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> str:
    """Single chat completion; returns the assistant text."""
    payload: dict = {
        "model": model(),
        "messages": messages,
        "temperature": temperature,
        # agnes-2.5-flash is a reasoning model: thinking tokens are billed
        # from this budget, so leave generous headroom for short answers.
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    data = _post("/chat/completions", payload)
    return _content_from(data)


def chat_json(messages: list[dict], *, max_tokens: int = 1024) -> dict:
    """Chat completion that must return a JSON object.

    Agnes' free tier rate-limits (HTTP 429), so transient failures back off
    and retry rather than dropping the request onto the regex fallback.
    A reasoning-model budget blow-out is retried with a larger budget.
    """
    attempts = _max_attempts()
    budget = max_tokens
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            text = _strip_fences(chat(messages, json_mode=True, max_tokens=budget))
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise AgnesError(f"Expected a JSON object, got {type(parsed).__name__}")
            return parsed
        except ValueError as exc:  # model returned something that is not JSON
            last_error = exc
            delay = _backoff(attempt)
        except AgnesError as exc:
            last_error = exc
            if not exc.retryable and "max_tokens budget" not in str(exc):
                logger.warning("Agnes chat_json giving up on attempt %s: %s", attempt, exc)
                raise
            if "max_tokens budget" in str(exc):
                budget = min(budget * 2, 4096)
            delay = max(_backoff(attempt), exc.retry_after or 0.0)
        else:
            continue

        if attempt >= attempts:
            break
        delay = min(delay, _max_backoff())
        logger.warning("Agnes chat_json attempt %s failed (%s); retrying in %.1fs", attempt, last_error, delay)
        time.sleep(delay)

    raise AgnesError(str(last_error), retryable=True)


def _backoff(attempt: int) -> float:
    return {1: 3.0, 2: 8.0, 3: 20.0}.get(attempt, 20.0)


def _max_attempts() -> int:
    try:
        return max(1, int(os.getenv("AGNES_MAX_ATTEMPTS") or 4))
    except ValueError:
        return 4


def _max_backoff() -> float:
    try:
        return float(os.getenv("AGNES_MAX_BACKOFF") or MAX_BACKOFF)
    except ValueError:
        return MAX_BACKOFF


def vision(prompt: str, image_b64: str, *, max_tokens: int = 1024) -> str:
    """Image understanding via a base64 data URL (OpenAI-compatible shape)."""
    return chat(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
        json_mode=False,
        max_tokens=max_tokens,
    )
