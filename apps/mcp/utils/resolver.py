import re
from datetime import date, datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.academics.models import Course, Term
from apps.enrollments.models import CourseOffering


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

    course = Course.objects.filter(code__iexact=course_code.strip()).first()
    if not course:
        raise ValueError(f"Course with code '{course_code}' not found")

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
