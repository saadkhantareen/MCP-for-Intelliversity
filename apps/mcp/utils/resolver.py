import difflib
import re
from datetime import date, datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.academics.models import Course, Term
from apps.enrollments.choices import AssignmentStatus
from apps.enrollments.models import CourseOffering


class AmbiguousCourseError(ValueError):
    """Raised when a course query is close to two or more real courses.

    Carries the candidate options so the caller can ask the user to pick
    one instead of guessing.
    """

    def __init__(self, query, options):
        self.query = query
        self.options = options  # list of {"code": ..., "name": ...}
        names = ", ".join(f"{o['name']} ({o['code']})" for o in options)
        super().__init__(f"Ambiguous course '{query}': did you mean {names}?")


FUZZY_THRESHOLD = 0.8
FUZZY_MARGIN = 0.1


def _normalize_course_text(value):
    """Casefold and strip spaces, hyphens and underscores: 'CS 102' -> 'cs102'."""
    return re.sub(r"[\s\-_]+", "", (value or "").casefold())


def _token_score(query_tokens, name_tokens):
    """Mean best-per-token similarity of the query against a course name."""
    if not query_tokens or not name_tokens:
        return 0.0
    total = 0.0
    for token in query_tokens:
        best = max(
            difflib.SequenceMatcher(None, token, name_token).ratio()
            for name_token in name_tokens
        )
        total += best
    return total / len(query_tokens)


def fuzzy_course_candidates(raw, courses):
    """Score one course spelling against every known course.

    ``courses`` is a list of (code, name) pairs. Returns ("ok", code)
    when exactly one candidate clears the threshold by a clear margin,
    ("ambiguous", [options]) when two or more are almost equally close,
    and ("none", None) when nothing is close enough.
    """
    query = (raw or "").strip()
    if not query or not courses:
        return ("none", None)

    query_norm = _normalize_course_text(query)
    query_tokens = re.findall(r"[a-z0-9]+", query.casefold())

    scored = []
    for code, name in courses:
        code_ratio = difflib.SequenceMatcher(
            None, query_norm, _normalize_course_text(code)
        ).ratio()
        name_ratio = difflib.SequenceMatcher(
            None, query_norm, _normalize_course_text(name)
        ).ratio()
        token_ratio = _token_score(
            query_tokens, re.findall(r"[a-z0-9]+", name.casefold())
        )
        scored.append((max(code_ratio, name_ratio, token_ratio), code, name))

    scored.sort(key=lambda item: -item[0])
    best_score, best_code, _best_name = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if best_score < FUZZY_THRESHOLD:
        return ("none", None)
    if best_score - second_score < FUZZY_MARGIN:
        close = [
            {"code": code, "name": name}
            for score, code, name in scored
            if score >= FUZZY_THRESHOLD and score >= best_score - FUZZY_MARGIN
        ]
        return ("ambiguous", close)
    return ("ok", best_code)


def _resolve_course(course_code):
    """Exact code lookup, then fuzzy; raises ValueError or AmbiguousCourseError."""
    course = Course.objects.filter(code__iexact=course_code.strip()).first()
    if course:
        return course
    courses = [(c.code, c.name) for c in Course.objects.all()[:300]]
    status, result = fuzzy_course_candidates(course_code, courses)
    if status == "ok":
        return Course.objects.filter(code__iexact=result).first()
    if status == "ambiguous":
        raise AmbiguousCourseError(course_code, result)
    raise ValueError(f"Course with code '{course_code}' not found")


def section_name_variants(value: str | None) -> list[str]:
    """Accept both bare and prefixed spellings of a section.

    The database stores "Section A" while users/LLM say "A", so both must
    match. Returns [] when nothing usable was provided.
    """
    raw = (value or "").strip()
    if not raw:
        return []
    bare = re.sub(r"^section[\s_-]*", "", raw, flags=re.I).strip() or raw
    variants: list[str] = []
    for candidate in (raw, bare, f"Section {bare}"):
        if candidate and candidate.casefold() not in {v.casefold() for v in variants}:
            variants.append(candidate)
    return variants


def section_q(field: str, value: str | None) -> Q:
    """OR-combined ``iexact`` lookups for every spelling of a section."""
    q = Q(pk__isnull=True)  # neutral element: matches nothing when empty
    for candidate in section_name_variants(value):
        q |= Q(**{f"{field}__iexact": candidate})
    return q

_HUMAN_DATE_FORMATS = (
    "%b %d, %Y",
    "%b %d %Y",
    "%B %d, %Y",
    "%B %d %Y",
)


def parse_date(value: str | None) -> date:
    if not value or value.strip().lower() in {"today", "today's"}:
        return timezone.now().date()
    if value.strip().lower() == "yesterday":
        return timezone.now().date() - timedelta(days=1)
    if value.strip().lower() == "tomorrow":
        return timezone.now().date() + timedelta(days=1)

    text = value.strip()
    candidates = [text]
    if text.split():
        candidates.append(text.split()[0])
    for iso_candidate in candidates:
        try:
            return date.fromisoformat(iso_candidate)
        except ValueError:
            continue

    # Accept human formats like "Mon, Oct 5, 2026" / "Oct 5, 2026", dropping a
    # weekday prefix and any trailing time part (" 9:00 AM - 10:00 AM").
    without_weekday = re.sub(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+", "", text, flags=re.I)
    match = re.search(r"[A-Za-z]+\.?\s+\d{1,2},?\s+\d{4}", without_weekday)
    if match:
        for fmt in _HUMAN_DATE_FORMATS:
            try:
                return datetime.strptime(match.group(0), fmt).date()
            except ValueError:
                continue

    raise ValueError(
        f"Could not understand date '{value}'. Use 'today' or e.g. 'Mon, Oct 5, 2026'."
    )


def resolve_offering(course_code: str, section_name: str, term=None):
    term = term or Term.objects.filter(is_active=True).first()
    if not term:
        raise ValueError("No active Term found. Admin must set Term.is_active=True")

    course = _resolve_course(course_code)

    if not section_name_variants(section_name):
        raise ValueError("Please specify a section, for example 'Section A'.")

    offering = (
        CourseOffering.objects.filter(course=course, term=term)
        .filter(section_q("section__name", section_name))
        .select_related("section", "section__batch", "course", "term")
        .first()
    )
    if not offering:
        raise ValueError(
            f"No CourseOffering for {course_code} Section {section_name} in active term {term.name}"
        )
    return offering, term


_SECTION_RE = re.compile(r"^[A-Za-z][0-9]?$")

_GENERIC_SECTIONS = {
    # NOTE: "a" is deliberately absent: section A is real, and the shape
    # check above (one letter + optional digit) already rules out articles.
    "my", "today", "tomorrow", "yesterday", "class", "course", "the",
    "an", "this", "that", "it", "for", "your", "our", "their", "section",
    "sec", "all", "please",
}


def normalize_section(value: str | None) -> str | None:
    """Canonical section letter, or None when the value cannot be a section.

    The LLM once returned "my" as a section ("mark MY today class"), so a
    section must be a single letter with an optional digit ("A", "B", "A1").
    "Section A" is accepted and reduced to "A".
    """
    raw = (value or "").strip()
    if not raw:
        return None
    bare = re.sub(r"^section[ _-]*", "", raw, flags=re.I).strip()
    if not _SECTION_RE.fullmatch(bare):
        return None
    if bare.casefold() in _GENERIC_SECTIONS:
        return None
    return bare.upper()


def _offering_label(offering):
    """'Section A' for display, whether the DB stores 'A' or 'Section A'."""
    label = offering.section.name
    return label if label.lower().startswith("section") else f"Section {label}"


def _approved_offerings_for_user(user, term):
    """The user's APPROVED faculty assignments in one term, all courses."""
    from apps.profiles.models import FacultyProfile

    faculty = FacultyProfile.objects.filter(base_profile__user=user).first()
    if faculty is None:
        return []
    return list(
        CourseOffering.objects.filter(
            term=term,
            faculty_assignments__faculty=faculty,
            faculty_assignments__status=AssignmentStatus.APPROVED,
        ).select_related("section", "course", "term")
    )


def _approved_offerings_for_course(user, course, term):
    """The user's APPROVED faculty assignments for one course in one term."""
    return [
        offering
        for offering in _approved_offerings_for_user(user, term)
        if offering.course_id == course.id
    ]


def resolve_offering_for_user(user, course_code: str | None = None, section_name: str | None = None, term=None):
    """Resolve an offering, inferring course and section when the teacher has one.

    - Course and section given (and plausible): same as resolve_offering.
    - No course mentioned and the teacher has exactly one approved offering
      this term: that is "my class", so use it.
    - No course and they teach several classes: ask which one, naming them.
    - Section missing and the teacher has exactly one approved offering for
      the course this term: use it, so "mark my today class ..." just works.
    - Section missing and they teach several sections: ask which one, naming
      them, instead of a bare "specify a section" error.
    - Admins and anyone without an approved assignment: ask for the details.
    """
    term = term or Term.objects.filter(is_active=True).first()
    if not term:
        raise ValueError("No active Term found. Admin must set Term.is_active=True")
    if not course_code:
        offerings = _approved_offerings_for_user(user, term)
        if len(offerings) == 1:
            return offerings[0], term
        if not offerings:
            raise ValueError(
                "Which course? Tell me the course and section, for example 'PF Section A'."
            )
        names = ", ".join(_offering_label(offering) for offering in offerings)
        raise ValueError(f"Which class? You teach {names}.")
    course = _resolve_course(course_code)
    section = normalize_section(section_name)
    if section_name and not section:
        raise ValueError(
            "I couldn't tell which section you meant. Please say the section, for example 'Section A'."
        )
    if section:
        return resolve_offering(course_code, section, term=term)
    offerings = _approved_offerings_for_course(user, course, term)
    if len(offerings) == 1:
        return offerings[0], term
    if not offerings:
        raise ValueError(
            f"You don't teach {course.code} this term. "
            "Please say the course and section, for example 'PF Section A'."
        )
    names = ", ".join(_offering_label(offering) for offering in offerings)
    raise ValueError(f"Which section of {course.code}? You teach {names}.")
