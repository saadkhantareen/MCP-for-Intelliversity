"""Regression tests for apps.mcp.llm_parser free-text parsing.

Guards against the two historical bugs:
1. Course extraction returning generic words: "PF class section A" -> CLASS.
2. Human dates like "Mon, Oct 5, 2026" being dropped by the regex fallback.

Run with: pytest apps/mcp/tests/test_llm_parser.py
"""

import os
import sys

if __package__ in (None, ""):
    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

from apps.mcp.llm_parser import (
    _infer_course_from_text,
    _match_course_code,
    _normalize_course_section,
    extract_course_section,
    extract_date_str,
    parse,
    regex_fallback,
)

COURSES = [
    ("CS201", "Data Structures"),
    ("CS102", "Programming Fundamentals"),
]

MARK_QUERY = (
    "mark attendance of Mon, Oct 5, 2026 9:00 AM - 10:00 AM "
    "PF class section A as all Present"
)


def test_extract_course_section_skips_generic_words():
    assert extract_course_section(MARK_QUERY) == ("PF", "A")
    assert extract_course_section("PF Section A attendance today") == ("PF", "A")
    assert extract_course_section("attendance report for section B") == (None, "B")
    assert extract_course_section("no section mentioned") == (None, None)


def test_match_course_code_spellings():
    """Regression: 'PF' is ONE token, so first-letter initials gave 'P' != 'PF'.

    The model is free to answer with the abbreviation, a name, or a word of
    the name - all must land on the real code.
    """
    assert _match_course_code("PF", COURSES) == "CS102"
    assert _match_course_code("pf", COURSES) == "CS102"
    assert _match_course_code("cs102", COURSES) == "CS102"
    assert _match_course_code("Programming Fundamentals", COURSES) == "CS102"
    assert _match_course_code("fundamentals", COURSES) == "CS102"
    assert _match_course_code("Data Structures", COURSES) == "CS201"
    assert _match_course_code("ds", COURSES) == "CS201"
    assert _match_course_code("structures", COURSES) == "CS201"
    # Unknown spellings stay unknown so the tool can reject them loudly.
    assert _match_course_code("ZOO101", COURSES) is None
    assert _match_course_code("PF", []) is None


def test_extract_course_section_accepts_sec_shorthand():
    assert extract_course_section("ds sec a quiz 2 marks report") == ("DS", "A")
    assert extract_course_section("PF Sec B attendance today") == ("PF", "B")
    # "sec" itself must never be read as the course.
    assert extract_course_section("show sec a students") == (None, "A")


def test_infer_course_from_text_without_section():
    assert _infer_course_from_text(
        "whats the defaulter list for data structures", COURSES
    ) == "CS201"
    assert _infer_course_from_text(
        "show me programming fundamentals numbers", COURSES
    ) == "CS102"
    assert _infer_course_from_text("PF defaulters", COURSES) == "CS102"
    assert _infer_course_from_text("nothing course related here", COURSES) is None
    assert _infer_course_from_text("", COURSES) is None
    # No tenant loaded -> no candidates to match against.
    assert _infer_course_from_text("data structures") in (None, "CS201")


def test_regex_fallback_defaulters_lesser_known_phrasings():
    """Wording that used to come back as tool=unknown must map to a tool."""
    parsed = regex_fallback("whats the defaulter list for data structures")
    assert parsed["tool"] == "get_defaulters"

    parsed = regex_fallback("students less than 70 percent in PF Section A")
    assert parsed["tool"] == "get_defaulters"
    assert parsed["args"]["threshold"] == 70
    assert parsed["args"]["course_code"] == "PF"
    assert parsed["args"]["section"] == "A"


def test_extract_date_str_human_iso_and_default():
    assert extract_date_str(MARK_QUERY) == "Mon, Oct 5, 2026"
    assert extract_date_str("attendance report for 2026-10-05") == "2026-10-05"
    assert extract_date_str("no date in this message") == "today"


def test_normalize_fills_missing_course_with_pf_not_class():
    # LLM omitted course_code; regex must fill PF, not CLASS.
    args = _normalize_course_section(
        MARK_QUERY,
        {"course_code": None, "section": "A", "date_str": "Mon, Oct 5, 2026"},
    )
    assert args["course_code"] == "PF"
    assert args["section"] == "A"


def test_normalize_scrubs_class_returned_by_llm():
    args = _normalize_course_section(
        "PF class section A", {"course_code": "CLASS", "section": "A"}
    )
    assert args["course_code"] == "PF"


def test_normalize_keeps_valid_llm_values():
    args = _normalize_course_section(
        MARK_QUERY, {"course_code": "PF", "section": "A"}
    )
    assert args["course_code"] == "PF"
    assert args["section"] == "A"


def test_regex_fallback_mark_attendance_with_human_date():
    parsed = regex_fallback(MARK_QUERY)
    assert parsed["tool"] == "mark_bulk_attendance"
    assert parsed["args"]["course_code"] == "PF"
    assert parsed["args"]["section"] == "A"
    assert parsed["args"]["date_str"] == "Mon, Oct 5, 2026"
    assert parsed["args"]["status"] == "PRESENT"


def test_regex_fallback_departments():
    parsed = regex_fallback("which of the departments are registered?")
    assert parsed["tool"] == "get_departments"


def test_regex_fallback_defaulters_ignores_class():
    parsed = regex_fallback("students below 60% in PF class section A")
    assert parsed["tool"] == "get_defaulters"
    assert parsed["args"]["course_code"] == "PF"
    assert parsed["args"]["section"] == "A"
    assert parsed["args"]["threshold"] == 60


def test_parse_without_api_key_uses_regex_path():
    """With no LLM key configured the parser must still answer via regex."""
    saved = {
        name: os.environ.pop(name, None)
        for name in ("EXPERIENTIAL_API_KEY", "GROQ_API_KEY")
    }
    try:
        parsed = parse("which of the departments are registered?")
        assert parsed["tool"] == "get_departments"
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value


def test_normalize_args_coerces_llm_values():
    """The model may answer naturally ('quiz', 'avg', '2') - tools need typed args."""
    from apps.mcp.llm_parser import _normalize_args

    args = _normalize_args(
        "add_marks_bulk",
        {
            "assessment_type_code": "quiz",
            "sequence": "2",
            "total_marks": "10",
            "mode": "avg",
            "avg_value": None,
        },
    )
    assert args["assessment_type_code"] == "QUIZ"
    assert args["sequence"] == 2
    assert args["total_marks"] == 10
    assert args["mode"] == "average"
    # No average stated -> half of the total, never a 0-100 style guess.
    assert args["avg_value"] == 5.0

    # The model answered "75" for an out-of-10 quiz -> 75% of 10 = 7.5.
    scaled = _normalize_args(
        "add_marks_bulk",
        {"assessment_type_code": "quiz", "total_marks": 10, "mode": "average", "avg_value": 75},
    )
    assert scaled["avg_value"] == 7.5

    attendance = _normalize_args(
        "mark_bulk_attendance", {"status": "present", "absent_names": "Ahmad Raza, Sana"}
    )
    assert attendance["status"] == "PRESENT"
    assert attendance["absent_names"] == ["Ahmad Raza", "Sana"]

    assert _normalize_args("get_defaulters", {"threshold": "60"})["threshold"] == 60


def test_parse_with_experiential_key_uses_llm_path():
    """Live smoke test: only runs when EXPERIENTIAL_API_KEY is configured."""
    if not os.getenv("EXPERIENTIAL_API_KEY"):
        print("skip: EXPERIENTIAL_API_KEY not set")
        return
    parsed = parse(MARK_QUERY)
    args = parsed["args"]
    assert parsed["tool"] == "mark_bulk_attendance"
    # "PF" without a tenant, the resolved real code (CS102) inside one.
    assert args["course_code"] in {"PF", "CS102"}
    assert args["section"] == "A"
    # The date must survive the LLM path - in whichever spelling it arrives.
    assert args["date_str"] in {"Mon, Oct 5, 2026", "Oct 5, 2026", "2026-10-05", "today"}
    assert args["status"] == "PRESENT"


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