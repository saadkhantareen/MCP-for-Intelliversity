"""Tests for the MCP response fixes: section validation and session picking.

Run with: pytest apps/mcp/tests/test_mcp_response_fixes.py
"""

import os
import sys

if __package__ in (None, ""):
    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

from datetime import time
from types import SimpleNamespace

from apps.mcp.llm_parser import _normalize_course_section
from apps.mcp.tools.attendance_tools import _pick_session_for_date
from apps.mcp.utils.resolver import normalize_section


def test_normalize_section_accepts_real_sections():
    assert normalize_section("A") == "A"
    assert normalize_section("b") == "B"
    assert normalize_section("Section A") == "A"
    assert normalize_section("A1") == "A1"
    assert normalize_section(None) is None
    assert normalize_section("") is None


def test_normalize_section_rejects_words():
    # Regression: the LLM returned "my" as a section ("mark MY today class").
    assert normalize_section("my") is None
    assert normalize_section("today") is None
    assert normalize_section("class") is None
    assert normalize_section("AB") is None
    assert normalize_section("Section my") is None


def test_llm_section_my_is_dropped():
    """"mark my today class ... for PF class" must not become Section my."""
    result = _normalize_course_section(
        "mark my today class all present except bilal and ayesha for PF class",
        {"tool": "mark_bulk_attendance", "course_code": "PF", "section": "my"},
    )
    assert result["section"] is None
    assert result["course_code"] == "PF"


def test_llm_section_a_survives():
    result = _normalize_course_section(
        "mark my today class all present except bilal and ayesha for PF class section A",
        {"tool": "mark_bulk_attendance", "course_code": "PF", "section": "A"},
    )
    assert result["section"] == "A"


def _session(id_, marked=False, start=None, seq=None):
    return SimpleNamespace(
        id=id_, is_attendance_marked=marked, start_time=start, sequence_number=seq
    )


def test_pick_session_prefers_the_marked_one():
    pending = _session(1, marked=False, start=time(9, 0))
    held = _session(2, marked=True, start=time(11, 0))
    assert _pick_session_for_date([pending, held]) is held
    assert _pick_session_for_date([held, pending]) is held


def test_pick_session_earliest_when_none_marked():
    first = _session(1, start=time(9, 0))
    second = _session(2, start=time(11, 0))
    assert _pick_session_for_date([second, first]) is first


def test_pick_session_none_when_empty():
    assert _pick_session_for_date([]) is None
