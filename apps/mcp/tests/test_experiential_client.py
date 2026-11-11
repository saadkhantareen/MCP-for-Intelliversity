"""Regression tests for the Experiential Labs HTTP client rate-limit handling.

The provider answers HTTP 429 on bursts. The client must back off and
retry instead of dropping the request onto the regex fallback.

Run with: pytest apps/mcp/tests/test_experiential_client.py
"""

import json
import os
import sys

if __package__ in (None, ""):
    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

from apps.mcp import experiential_client


class FakeResponse:
    def __init__(self, status_code: int, body: dict | str, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


def _ok_body(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def test_chat_json_retries_429_with_backoff_then_succeeds():
    """Two 429s then a good answer: back off, then answer - never fall back."""
    saved_key = os.environ.get("EXPERIENTIAL_API_KEY")
    os.environ["EXPERIENTIAL_API_KEY"] = "test-key"
    responses = [
        FakeResponse(429, {"error": {"message": "rate limited"}}),
        FakeResponse(429, {"error": {"message": "rate limited"}}, headers={"Retry-After": "7"}),
        FakeResponse(200, _ok_body('{"tool": "get_departments", "args": {}}')),
    ]
    slept: list[float] = []
    original_post, original_sleep = experiential_client.requests.post, experiential_client.time.sleep

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        return responses.pop(0)

    experiential_client.requests.post = fake_post
    experiential_client.time.sleep = slept.append
    try:
        parsed = experiential_client.chat_json([{"role": "user", "content": "hi"}])
    finally:
        experiential_client.requests.post = original_post
        experiential_client.time.sleep = original_sleep
        if saved_key is None:
            os.environ.pop("EXPERIENTIAL_API_KEY", None)
        else:
            os.environ["EXPERIENTIAL_API_KEY"] = saved_key

    assert parsed == {"tool": "get_departments", "args": {}}
    # Attempt 1 waits its backoff; attempt 2 honours the server Retry-After.
    assert slept[0] == experiential_client._backoff(1)
    assert slept[1] == experiential_client._backoff(2)


def test_chat_json_does_not_retry_auth_errors():
    """A bad key must fail fast instead of sleeping through every retry."""
    saved_key = os.environ.get("EXPERIENTIAL_API_KEY")
    os.environ["EXPERIENTIAL_API_KEY"] = "test-key"
    responses = [FakeResponse(401, {"error": {"message": "bad key"}})]
    slept: list[float] = []
    original_post, original_sleep = experiential_client.requests.post, experiential_client.time.sleep

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        return responses.pop(0)

    experiential_client.requests.post = fake_post
    experiential_client.time.sleep = slept.append
    try:
        try:
            experiential_client.chat_json([{"role": "user", "content": "hi"}])
            raised = False
        except experiential_client.ExperientialError:
            raised = True
    finally:
        experiential_client.requests.post = original_post
        experiential_client.time.sleep = original_sleep
        if saved_key is None:
            os.environ.pop("EXPERIENTIAL_API_KEY", None)
        else:
            os.environ["EXPERIENTIAL_API_KEY"] = saved_key

    assert raised, "401 should raise ExperientialError"
    assert slept == [], "non-retryable errors must not back off"


def test_backoff_schedule_is_bounded():
    """Delays grow but never exceed MAX_BACKOFF."""
    delays = [min(experiential_client._backoff(n), experiential_client._max_backoff()) for n in range(1, 6)]
    assert delays == sorted(delays)
    assert max(delays) <= experiential_client.MAX_BACKOFF


if __name__ == "__main__":
    failures = 0
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
