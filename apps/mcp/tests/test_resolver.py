"""Regression tests for apps.mcp.utils.resolver.parse_date.

Guards the human-date fix: "Mon, Oct 5, 2026" (and time-suffixed variants)
must resolve instead of crashing date.fromisoformat.

Run with: pytest apps/mcp/tests/test_resolver.py
"""

import os
import sys
from datetime import date

if __package__ in (None, ""):
    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

from apps.mcp.utils.resolver import parse_date


def test_parse_date_human_formats():
    assert parse_date("Mon, Oct 5, 2026") == date(2026, 10, 5)
    assert parse_date("Monday, October 5, 2026") == date(2026, 10, 5)
    assert parse_date("Mon Oct 5, 2026") == date(2026, 10, 5)
    assert parse_date("Oct 5, 2026 9:00 AM - 10:00 AM") == date(2026, 10, 5)


def test_parse_date_iso_and_relative():
    assert parse_date("2026-10-05") == date(2026, 10, 5)
    assert parse_date("2026-10-05 extra text") == date(2026, 10, 5)
    from django.utils import timezone

    assert parse_date("today") == timezone.now().date()
    assert parse_date(None) == timezone.now().date()


def test_parse_date_invalid_raises_friendly_error():
    try:
        parse_date("not a real date")
    except ValueError as exc:
        assert "Could not understand date" in str(exc)
    else:
        raise AssertionError("expected ValueError for unparseable date")


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