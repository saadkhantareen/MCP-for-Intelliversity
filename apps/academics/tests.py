from datetime import date, datetime, timezone

from apps.academics.views import build_enrollment_buckets

UTC = timezone.utc


def _dt(year, month, day=15):
    return datetime(year, month, day, 12, 0, tzinfo=UTC)


def test_buckets_6m_ends_at_today_with_real_zeros():
    buckets = build_enrollment_buckets(
        "6M", [_dt(2026, 11, 3)], today=date(2026, 11, 11)
    )
    assert [b["month"] for b in buckets] == [
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
    ]
    assert [b["value"] for b in buckets] == [0, 0, 0, 0, 0, 1]


def test_buckets_1y_labels_carry_the_year():
    buckets = build_enrollment_buckets(
        "1Y", [_dt(2025, 12, 20), _dt(2026, 1, 5)], today=date(2026, 11, 11)
    )
    assert len(buckets) == 12
    assert buckets[0]["month"] == "Dec 25"
    assert buckets[0]["value"] == 1
    assert buckets[1]["month"] == "Jan 26"
    assert buckets[1]["value"] == 1
    assert buckets[-1]["month"] == "Nov 26"
    assert buckets[-1]["value"] == 0


def test_buckets_all_spans_enrollment_years():
    buckets = build_enrollment_buckets(
        "All", [_dt(2024, 3), _dt(2026, 9)], today=date(2026, 11, 11)
    )
    assert buckets == [
        {"month": "2024", "value": 1},
        {"month": "2025", "value": 0},
        {"month": "2026", "value": 1},
    ]


def test_buckets_all_with_no_enrollments_returns_five_zero_years():
    buckets = build_enrollment_buckets("All", [], today=date(2026, 11, 11))
    assert buckets == [
        {"month": "2022", "value": 0},
        {"month": "2023", "value": 0},
        {"month": "2024", "value": 0},
        {"month": "2025", "value": 0},
        {"month": "2026", "value": 0},
    ]


def test_buckets_unknown_period_falls_back_to_6m():
    buckets = build_enrollment_buckets(
        "3Y", [_dt(2026, 11, 1)], today=date(2026, 11, 11)
    )
    assert len(buckets) == 6
    assert buckets[-1] == {"month": "Nov", "value": 1}
