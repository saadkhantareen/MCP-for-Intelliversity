from __future__ import annotations

import logging
import re

from . import experiential_client

SYSTEM = """You are Intelliversity MCP parser. Return ONLY JSON {"tool": "...", "args": {...}}
Tools:
WRITES: mark_bulk_attendance(course_code,section,date_str,status,absent_names), add_marks_bulk(course_code,section,assessment_type_code,sequence,total_marks,mode,avg_value), create_departments_bulk(departments), bulk_create_students(csv_text,batch_name,section_name)
READS: get_attendance_report(course_code,section,date_str), get_defaulters(course_code,section,threshold), get_my_classes_count(), get_marks_report(course_code,section,assessment_type_code,sequence), get_departments(), get_faculty_by_department(department_code), get_curriculum(program_code,batch_name,curriculum_name), get_section_students(section,batch_name), get_offerings(course_code)
IMPORTANT:
- The value of "tool" must be the exact function name from the list above, never a category like READS or WRITES.
- Return ONLY one JSON object, no markdown, no explanation.
- CRITICAL: course_code is NEVER "CLASS" or "COURSE" or "SECTION" or "QUIZ".
- course_code must be an EXACT code from the KNOWN COURSES list in this message. If the user writes a course name ("Data Structures"), an abbreviation ("PF"), or a phrase like "PF class", return the matching code.
- Lines such as "Quiz 2" or "out of 10" are NOT course names: assessment type comes from words quiz/mid/final/assignment, sequence is the number after them.
- Extract date_str verbatim like "Mon, Oct 5, 2026" (weekday, month, day, year). Use "today" only when no date is mentioned.
- assessment_type_code must be UPPERCASE: QUIZ, MID, FINAL or ASSIGNMENT.
- mode must be exactly "average" (user said avg/average) or "random" (default/otherwise). avg_value is a number, only used when mode is "average".
- sequence and total_marks are integers. status is "PRESENT" or "ABSENT".
For "only X and Y are absent rest present" -> mark_bulk_attendance status=PRESENT absent_names=[X,Y]
For "below 60%" -> get_defaulters threshold=60
For "today" -> date_str=today
"""

ALLOWED_TOOLS = {
    "mark_bulk_attendance",
    "add_marks_bulk",
    "create_departments_bulk",
    "bulk_create_students",
    "get_attendance_report",
    "get_defaulters",
    "get_my_classes_count",
    "get_marks_report",
    "get_departments",
    "get_faculty_by_department",
    "get_curriculum",
    "get_section_students",
    "get_offerings",
}

logger = logging.getLogger(__name__)

# Words a regex can mistake for a course code but that never actually are.
GENERIC_COURSE_WORDS = {
    "class", "course", "section", "sec", "attendance", "mark", "marks", "report",
    "all", "only", "rest", "present", "absent", "today", "yesterday", "tomorrow",
    "the", "for", "of", "in", "on", "at", "to", "and", "or", "a", "an",
    "which", "what", "when", "where", "how", "who", "please", "bring", "show",
    "give", "list", "students", "faculty", "teacher", "teachers", "department",
    "departments", "batch", "quiz", "mid", "final", "date", "day",
}

_DATE_PATTERNS = (
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
)


def extract_course_section(text: str) -> tuple[str | None, str | None]:
    """Best-effort (course_code, section) extraction from free text.

    Handles filler between the code and the word "section" so that
    "PF class section A" -> ("PF", "A") and never returns generic words
    like CLASS/COURSE as a course code. "sec" is accepted as shorthand.
    """
    section_match = re.search(r"\b(?:sections?|sec)(?![a-z0-9])[\s-]*([a-z0-9]{1,4})\b", text, re.I)
    if not section_match:
        return None, None
    section = section_match.group(1).upper()
    words = re.findall(r"[A-Za-z0-9]+", text[: section_match.start()])
    for word in reversed(words[-4:]):
        if word.isdigit() or word.lower() in GENERIC_COURSE_WORDS:
            continue
        return word.upper(), section
    return None, section


def extract_date_str(text: str) -> str:
    """Pull a date out of free text, keeping the human format verbatim.

    "mark ... Mon, Oct 5, 2026 ..." -> "Mon, Oct 5, 2026" (resolver.parse_date
    understands it); ISO dates pass through; falls back to "today".
    """
    for pattern in _DATE_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0).strip()
    return "today"


def _load_courses() -> list[tuple[str, str]]:
    """(code, name) for every course of the current tenant.

    Returns [] outside a request (tests, management commands without a
    tenant) or when the tenant DB is unavailable - callers must tolerate that.
    """
    try:
        from apps.academics.models import Course

        return [(c.code, c.name) for c in Course.objects.all()[:300]]
    except Exception:  # noqa: BLE001 - course lookup is advisory only
        return []


def _course_hint() -> str:
    courses = _load_courses()
    if not courses:
        return ""
    listing = ", ".join(f"{code} = {name}" for code, name in courses)
    return f"KNOWN COURSES (course_code must be one of these codes):\n- {listing}\n"


def _match_course_code(raw: str, courses: list[tuple[str, str]]) -> str | None:
    """Map one spelling of a course onto a real (code, name) pair.

    Pure so it can be unit-tested without a database.

    "PF" / "pf"      -> CS102  (initials of "Programming Fundamentals")
    "Fundamentals"   -> CS102  (a word of the course name)
    "Data Structures"-> CS201  (exact name)
    "CS102"          -> CS102  (exact code)
    """
    if not raw or not courses:
        return None

    upper = raw.upper()
    by_code = {code.upper(): code for code, _ in courses}
    if upper in by_code:
        return by_code[upper]

    raw_tokens = set(re.findall(r"[a-z0-9]+", raw.casefold()))
    # "PF" is one token, so take both the whole spelling and the first letter
    # of every word - "PF" must still match initials "PF".
    word_initials = "".join(part[0] for part in re.findall(r"[A-Za-z0-9]+", raw)).upper()

    for code, name in courses:
        name_tokens = re.findall(r"[A-Za-z0-9]+", name)
        name_folded = {token.casefold() for token in name_tokens}
        name_initials = "".join(token[0] for token in name_tokens).upper()

        if upper == name.upper():
            return code
        if name_initials and upper == name_initials:
            return code
        if word_initials and word_initials == name_initials:
            return code
        if raw_tokens and raw_tokens <= name_folded:
            return code
        if len(raw_tokens) == 1 and raw_tokens & name_folded:
            return code
    return None


def _resolve_course_code(value: object) -> str | None:
    """Resolve whatever the user/model said against the tenant's courses.

    Unknown values are upper-cased and left for the tool to reject loudly.
    """
    raw = str(value or "").strip()
    if not raw:
        return None

    courses = _load_courses()
    if not courses:
        return raw.upper()
    return _match_course_code(raw, courses) or raw.upper()


def _infer_course_from_text(text: str, courses: list[tuple[str, str]] | None = None) -> str | None:
    """Find a course by name/initials anywhere in the free text.

    Catches phrasings the section regex cannot reach, e.g.
    "whats the defaulter list for data structures" -> CS201.
    ``courses`` is injectable so the matcher is testable without a tenant DB.
    """
    if courses is None:
        courses = _load_courses()
    if not courses or not text:
        return None

    low = text.casefold()
    # Longest name first so "Data Structures" wins over any shorter overlap.
    for code, name in sorted(courses, key=lambda pair: -len(pair[1])):
        if name.casefold() in low:
            return code
    for code, name in courses:
        initials = "".join(token[0] for token in re.findall(r"[A-Za-z0-9]+", name)).upper()
        if initials and re.search(rf"\b{re.escape(initials)}\b", text, re.I):
            return code
    return None


def _normalize_course_section(message: str, args: dict[str, object], context: str = "") -> dict[str, object]:
    normalized = _normalize_course_section_base(message, args, context)
    if normalized.get("course_code") not in (None, "", "null"):
        normalized["course_code"] = _resolve_course_code(normalized["course_code"])
    return normalized


def _normalize_course_section_base(message: str, args: dict[str, object], context: str = "") -> dict[str, object]:
    normalized = dict(args)

    def apply_context(text: str):
        if not text:
            return
        course_match = re.search(r"course_code\s*=\s*([A-Za-z0-9]{2,10})", text, re.I)
        section_match = re.search(r"section\s*=\s*([A-Za-z0-9]+)", text, re.I)
        if course_match and not normalized.get("course_code"):
            normalized["course_code"] = course_match.group(1).upper()
        if section_match and not normalized.get("section"):
            normalized["section"] = section_match.group(1).upper()

    apply_context(context)

    # Never let generic words (CLASS/COURSE/SECTION) survive as course codes,
    # even when they came straight from the LLM.
    if str(normalized.get("course_code") or "").strip().lower() in GENERIC_COURSE_WORDS:
        normalized["course_code"] = None

    # Fill any missing values from the message itself: "PF class section A" -> PF, A.
    if normalized.get("course_code") in (None, "", "null") or normalized.get("section") in (None, "", "null"):
        course, section = extract_course_section(message)
        if course and normalized.get("course_code") in (None, "", "null"):
            normalized["course_code"] = course
        if section and normalized.get("section") in (None, "", "null"):
            normalized["section"] = section

    # If the page context / LLM / message already provided the values, stop here.
    if normalized.get("course_code") and normalized.get("section"):
        return normalized

    code_in_parens = re.search(r"\(([A-Z0-9]{2,10})\)", message)
    if code_in_parens and normalized.get("course_code") in (None, "", "null"):
        normalized["course_code"] = code_in_parens.group(1).upper()

    # Last resort: no "section"-anchored code anywhere, so match the course
    # name (or its initials) that appears in the message itself.
    if normalized.get("course_code") in (None, "", "null"):
        inferred = _infer_course_from_text(message)
        if inferred:
            normalized["course_code"] = inferred

    return normalized


COURSE_SECTION_TOOLS = {
    "mark_bulk_attendance",
    "add_marks_bulk",
    "get_attendance_report",
    "get_defaulters",
    "get_marks_report",
    "get_offerings",
}


def regex_fallback(m: str):
    low = m.lower()

    if any(x in low for x in [
        "report", "list", "show", "give", "bring", "how many", "below",
        "percentage", "percent", "less than", "under", "defaulter",
        "struggling", "curriculum", "department",
    ]):
        if "attendance" in low and "report" in low:
            course, section = extract_course_section(m)
            if course:
                return {
                    "tool": "get_attendance_report",
                    "args": {
                        "course_code": course,
                        "section": section,
                        "date_str": extract_date_str(m),
                    },
                }
        if re.search(r"\b(below|less than|under|defaulter|struggling)\b", low):
            threshold = re.search(r"(?:below|less than|under)\s*(\d+)", low)
            course, section = extract_course_section(m)
            return {
                "tool": "get_defaulters",
                "args": {
                    "course_code": course,
                    "section": section,
                    "threshold": int(threshold.group(1)) if threshold else 60,
                },
            }
        if "how many classes" in low or "my courses" in low or "total have" in low:
            return {"tool": "get_my_classes_count", "args": {}}
        if "marks" in low and "report" in low:
            course, section = extract_course_section(m)
            seq = re.search(r"quiz\s*(\d+)", low)
            if course:
                return {
                    "tool": "get_marks_report",
                    "args": {
                        "course_code": course,
                        "section": section,
                        "assessment_type_code": "QUIZ",
                        "sequence": int(seq.group(1)) if seq else 1,
                    },
                }
        if "department" in low and "add" not in low:
            if "teacher" in low or "faculty" in low:
                dept = re.search(r"(cs|business|maths|english|[a-z]{2,})\s+department", low)
                return {
                    "tool": "get_faculty_by_department",
                    "args": {"department_code": dept.group(1).upper() if dept else "CS"},
                }
            return {"tool": "get_departments", "args": {}}
        if "curriculum" in low:
            batch = re.search(r"batch\s*(\d{4})", low)
            prog = re.search(r"\b(cs|bscs|bba)\b", low)
            return {
                "tool": "get_curriculum",
                "args": {
                    "program_code": prog.group(1).upper() if prog else None,
                    "batch_name": batch.group(1) if batch else None,
                },
            }
        if "student" in low and "section" in low:
            sec = re.search(r"\bsection[\s-]*([a-z0-9]{1,4})\b", low)
            return {
                "tool": "get_section_students",
                "args": {"section": sec.group(1).upper() if sec else None},
            }

    if "attendance" in low or "absent" in low or "present" in low:
        course, section = extract_course_section(m)
        if course:
            m1 = re.search(r"only\s+(.+?)\s+(?:are\s+)?absent", low)
            absent = []
            if m1:
                raw = m1.group(1)
                absent = [n.strip() for n in re.split(r",| and ", raw) if n.strip() and len(n.strip()) > 2]
            status = "ABSENT" if "all absent" in low else "PRESENT"
            return {
                "tool": "mark_bulk_attendance",
                "args": {
                    "course_code": course,
                    "section": section,
                    "date_str": extract_date_str(m),
                    "status": status,
                    "absent_names": absent,
                },
            }

    if any(x in low for x in ["marks", "quiz", "mid", "final"]):
        course, section = extract_course_section(m)
        total = re.search(r"out of (\d+)", low)
        seq = re.search(r"quiz\s*(\d+)|mid\s*(\d+)|final", low)
        seq_no = 1
        if seq:
            for group in seq.groups():
                if group:
                    seq_no = int(group)
                    break
        type_code = "QUIZ" if "quiz" in low else "MID" if "mid" in low else "FINAL" if "final" in low else "QUIZ"
        mode = "random" if "random" in low else "average" if "avg" in low or "average" in low else "random"
        if course:
            return {
                "tool": "add_marks_bulk",
                "args": {
                    "course_code": course,
                    "section": section,
                    "assessment_type_code": type_code,
                    "sequence": seq_no,
                    "total_marks": int(total.group(1)) if total else 10,
                    "mode": mode,
                    "avg_value": 7.5,
                },
            }

    if "department" in low and "add" in low:
        codes = re.findall(r"\b(CS|Management Sciences|Maths|English|[A-Z]{2,})\b", m, re.I)
        if codes:
            return {
                "tool": "create_departments_bulk",
                "args": {"departments": [{"name": c, "code": c[:10].upper().replace(" ", "_")} for c in codes]},
            }

    return {"tool": "unknown", "args": {"message": m}}


def _coerce_int(value, default=None):
    try:
        if value in (None, "", "null"):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _coerce_float(value, default=None):
    try:
        if value in (None, "", "null"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_str_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = re.split(r",| and ", value)
    return [str(name).strip() for name in value if str(name).strip()]


def _normalize_args(tool: str, args: dict[str, object]) -> dict[str, object]:
    """Coerce LLM output into exactly what the tool functions expect.

    Keeps the model free to answer naturally ("quiz", "avg", "2") while the
    tools still receive QUIZ/average/2.
    """
    normalized = dict(args)

    if tool in {"add_marks_bulk", "get_marks_report"}:
        kind = str(normalized.get("assessment_type_code") or "").strip().lower()
        if kind:
            normalized["assessment_type_code"] = {
                "quiz": "QUIZ",
                "mid": "MID",
                "midterm": "MID",
                "final": "FINAL",
                "assignment": "ASSIGNMENT",
            }.get(kind, kind.upper())
        if tool == "add_marks_bulk":
            mode = str(normalized.get("mode") or "").strip().lower()
            normalized["mode"] = "average" if mode in {"avg", "average", "mean"} else "random"
            total_marks = _coerce_int(normalized.get("total_marks"), 10)
            normalized["total_marks"] = total_marks
            avg_value = _coerce_float(normalized.get("avg_value"))
            if avg_value is None or avg_value < 0:
                avg_value = total_marks / 2
            elif avg_value > total_marks:
                # The model often answers on a 0-100 scale ("75" meaning 75%).
                # Convert into the real mark range; otherwise fall back to half.
                avg_value = (
                    total_marks * (avg_value / 100) if avg_value <= 100 else total_marks / 2
                )
            normalized["avg_value"] = round(float(avg_value), 2)
        normalized["sequence"] = _coerce_int(normalized.get("sequence"), 1)

    if tool == "get_defaulters":
        normalized["threshold"] = _coerce_int(normalized.get("threshold"), 60)

    if tool == "mark_bulk_attendance":
        normalized["status"] = str(normalized.get("status") or "PRESENT").strip().upper()
        if normalized["status"] not in {"PRESENT", "ABSENT"}:
            normalized["status"] = "PRESENT"
        normalized["absent_names"] = _coerce_str_list(normalized.get("absent_names"))
        normalized.setdefault("date_str", "today")

    return normalized


def _finalize(message: str, parsed: dict, context: str = "") -> dict:
    """Run course/section resolution + argument coercion on any parse result."""
    tool = parsed.get("tool")
    args = parsed.get("args") or {}
    if not isinstance(args, dict):
        args = {}
    if tool in COURSE_SECTION_TOOLS:
        args = _normalize_course_section(message, args, context)
    return {"tool": tool, "args": _normalize_args(tool, args)}


def parse(message: str, context: str = ""):
    """Turn free text into {"tool": ..., "args": ...} via the Experiential Labs LLM.

    The regex fallback only runs when the LLM is unreachable or returns
    something unusable - it is a safety net, not the primary path.
    """
    if not experiential_client.api_key():
        logger.warning("MCP parse: EXPERIENTIAL_API_KEY missing -> regex_fallback msg=%r", message[:60])
        return _finalize(message, regex_fallback(message), context)

    try:
        parsed = experiential_client.chat_json(
            [
                {"role": "system", "content": SYSTEM + _course_hint()},
                {"role": "user", "content": message},
            ],
            max_tokens=1024,
        )
        if parsed.get("tool") not in ALLOWED_TOOLS:
            raise ValueError(f"Unsupported tool returned by {experiential_client.model()}: {parsed}")

        result = _finalize(message, parsed, context)
        logger.info("MCP parse: Experiential OK tool=%s args=%s", result["tool"], result["args"])
        return result
    except Exception as exc:
        logger.warning("MCP parse: Experiential failed (%s) -> regex_fallback msg=%r", exc, message[:60])
        return _finalize(message, regex_fallback(message), context)
