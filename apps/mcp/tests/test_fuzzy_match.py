"""Regression tests for the difflib fuzzy course matcher.

Covers exact codes, initials, one-typo names/codes, ambiguous codes that
must ask instead of guessing, and distant nonsense that must not match.

Run with: pytest apps/mcp/tests/test_fuzzy_match.py"""

import os
import sys

if __package__ in (None, ""):
    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

import pytest

from apps.mcp import llm_parser
from apps.mcp.llm_parser import _match_course_code, _resolve_course_code, parse
from apps.mcp.utils.resolver import AmbiguousCourseError, fuzzy_course_candidates

COURSES = [
    ("CSC101", "Introduction to ICT"),
    ("CSC102", "Discrete Structures"),
    ("CSC103", "Programming Fundamentals"),
    ("CSC211", "Data Structures and Algorithms"),
    ("CSC241", "Object Oriented Programming"),
    ("MTH104", "Calculus and Analytic Geometry"),
]


@pytest.fixture(autouse=True)
def _fixed_courses(monkeypatch):
    # No LLM and no tenant DB: the parser resolves against this fixed list.
    monkeypatch.setattr(llm_parser, "_load_courses", lambda: COURSES)
    monkeypatch.setattr(llm_parser.experiential_client, "api_key", lambda: "")


def test_match_exact_code():
    assert _match_course_code("CSC103", COURSES) == "CSC103"
    assert _match_course_code("csc103", COURSES) == "CSC103"


def test_match_initials():
    assert _match_course_code("PF", COURSES) == "CSC103"


def test_match_exact_name():
    assert _match_course_code("Data Structures and Algorithms", COURSES) == "CSC211"
    # Exact name must beat the initials collision: both CSC102 "Discrete
    # Structures" and CSC211 shorten to DS, so "Data Structures" is CSC211.
    assert _match_course_code("Data Structures", COURSES) == "CSC211"


def test_match_misspelled_names():
    assert _match_course_code("Programing Fundmentals", COURSES) == "CSC103"
    assert _match_course_code("Data Structres", COURSES) == "CSC211"


def test_match_fuzzy_only_path():
    # Single misspelled words: no exact/initials/token rule fires, only fuzzy.
    assert _match_course_code("Fundmentals", COURSES) == "CSC103"
    # Bare "Structres" is genuinely ambiguous: two courses contain
    # "Structures" (CSC102 Discrete Structures, CSC211 Data Structures).
    status, options = fuzzy_course_candidates("Structres", COURSES)
    assert status == "ambiguous"
    assert {option["code"] for option in options} == {"CSC102", "CSC211"}


def test_match_spaced_and_short_codes():
    assert _match_course_code("CS 102", COURSES) == "CSC102"
    assert _match_course_code("CS103", COURSES) == "CSC103"


def test_fuzzy_ambiguous_code():
    status, options = fuzzy_course_candidates("CSC10Z", COURSES)
    assert status == "ambiguous"
    assert {option["code"] for option in options} == {"CSC101", "CSC102", "CSC103"}


def test_fuzzy_nonsense_matches_nothing():
    assert fuzzy_course_candidates("XYZQQ", COURSES) == ("none", None)
    assert _match_course_code("XYZQQ", COURSES) is None


def test_resolve_ambiguous_raises():
    with pytest.raises(AmbiguousCourseError) as excinfo:
        _resolve_course_code("CSC10Z")
    assert {option["code"] for option in excinfo.value.options} == {"CSC101", "CSC102", "CSC103"}


def test_resolve_nonsense_passes_through_upper_cased():
    # Unknown spellings are left for the tool to reject loudly.
    assert _resolve_course_code("XYZQQ") == "XYZQQ"


def test_parse_misspelled_name_resolves():
    parsed = parse("Programing Fundmentals Section A attendance report today")
    assert parsed["tool"] == "get_attendance_report"
    assert parsed["args"]["course_code"] == "CSC103"
    assert parsed["args"]["section"] == "A"


def test_parse_ambiguous_code_clarifies():
    parsed = parse("CSC10Z Section A attendance report today")
    assert parsed["tool"] == "clarify"
    assert {option["code"] for option in parsed["args"]["options"]} == {"CSC101", "CSC102", "CSC103"}
    assert parsed["args"]["matched_text"] == "CSC10Z"


def test_parse_nonsense_course_passes_through():
    parsed = parse("XYZQQ Section A attendance report today")
    assert parsed["tool"] == "get_attendance_report"
    assert parsed["args"]["course_code"] == "XYZQQ"


def test_parse_my_cgpa_forecast():
    assert parse("What is my CGPA forecast?")["tool"] == "get_my_cgpa_forecast"


def test_parse_my_attendance():
    parsed = parse("My attendance in CSC103 Section A")
    assert parsed["tool"] == "get_attendance_report"
    assert parsed["args"]["course_code"] == "CSC103"
    assert parsed["args"]["section"] == "A"


def test_parse_quiz_marks_for_is_a_read():
    parsed = parse("Quiz marks for CSC103 Section A")
    assert parsed["tool"] == "get_marks_report"
    assert parsed["args"]["course_code"] == "CSC103"


def test_parse_my_offerings():
    assert parse("My course offerings")["tool"] == "get_offerings"
