"""Regression tests for the Agnes HTTP client's rate-limit handling.

The Agnes free tier answers HTTP 429 on bursts. The old client retried twice
with no wait and then dropped the request onto the regex fallback, which is
exactly what the Agnes migration was meant to remove.

Run with: pytest apps/mcp/tests/test_agnes_client.py
"""

import json
import os
import sys

if __package__ in (None, ""):
    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

from apps.mcp import agnes_client


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
    saved_key = os.environ.get("AGNES_API_KEY")
    os.environ["AGNES_API_KEY"] = "test-key"
    responses = [
        FakeResponse(429, {"error": {"message": "rate limited"}}),
        FakeResponse(429, {"error": {"message": "rate limited"}}, headers={"Retry-After": "7"}),
        FakeResponse(200, _ok_body('{"tool": "get_departments", "args": {}}')),
    ]
    slept: list[float] = []
    original_post, original_sleep = agnes_client.requests.post, agnes_client.time.sleep

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        return responses.pop(0)

    agnes_client.requests.post = fake_post
    agnes_client.time.sleep = slept.append
    try:
        parsed = agnes_client.chat_json([{"role": "user", "content": "hi"}])
    finally:
        agnes_client.requests.post = original_post
        agnes_client.time.sleep = original_sleep
        if saved_key is None:
            os.environ.pop("AGNES_API_KEY", None)
        else:
            os.environ["AGNES_API_KEY"] = saved_key

    assert parsed == {"tool": "get_departments", "args": {}}
    # Attempt 1 waits its backoff; attempt 2 honours the server's Retry-After.
    assert slept[0] == agnes_client._backoff(1)
    assert slept[1] == agnes_client._backoff(2)


def test_chat_json_does_not_retry_auth_errors():
    """A bad key must fail fast instead of sleeping through every retry."""
    saved_key = os.environ.get("AGNES_API_KEY")
    os.environ["AGNES_API_KEY"] = "test-key"
    responses = [FakeResponse(401, {"error": {"message": "bad key"}})]
    slept: list[float] = []
    original_post, original_sleep = agnes_client.requests.post, agnes_client.time.sleep

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        return responses.pop(0)

    agnes_client.requests.post = fake_post
    agnes_client.time.sleep = slept.append
    try:
        try:
            agnes_client.chat_json([{"role": "user", "content": "hi"}])
            raised = False
        except agnes_client.AgnesError:
            raised = True
    finally:
        agnes_client.requests.post = original_post
        agnes_client.time.sleep = original_sleep
        if saved_key is None:
            os.environ.pop("AGNES_API_KEY", None)
        else:
            os.environ["AGNES_API_KEY"] = saved_key

    assert raised, "401 should raise AgnesError"
    assert slept == [], "non-retryable errors must not back off"


def test_backoff_schedule_is_bounded():
    """Delays grow but never exceed MAX_BACKOFF."""
    delays = [min(agnes_client._backoff(n), agnes_client._max_backoff()) for n in range(1, 6)]
    assert delays == sorted(delays)
    assert max(delays) <= agnes_client.MAX_BACKOFF


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
