"""Prediction policy: the post-processing rules applied to a raw model output.

Deliberately pure Python with no Django, numpy or pandas imports, so the same
functions are used by

* ``ml/train.py`` when it measures guardrail fire rate, MAE before/after the
  guardrail and band coverage, and
* ``apps/predictions/services.py`` when it serves a request.

If the two implementations ever diverged, the evaluation recorded in the
manifest would stop describing what the API actually does. Sharing this module
is the only thing that keeps them in step.

**These are demo constants, not a validated policy.** ``GUARDRAIL_MIN_AVG`` in
particular is an arbitrary demo choice: a student whose past average is 2.99
receives no guardrail, while one at 3.00 does. See docs/09 §5.
"""

from __future__ import annotations

import math

#: Demo-only constants. Changing any of these changes what the shipped
#: evaluation means, so change the manifest/evaluation record with them.
GUARDRAIL_MIN_AVG = 3.0
GUARDRAIL_MAX_DROP = 0.2
CGPA_MIN = 0.0
CGPA_MAX = 4.0
AT_RISK_THRESHOLD = 2.0

#: Recorded verbatim in ``manifest.json`` so a served prediction can be traced
#: to the policy that produced it.
DEFAULT_POLICY = {
    "guardrail_min_avg": GUARDRAIL_MIN_AVG,
    "guardrail_max_drop": GUARDRAIL_MAX_DROP,
    "cgpa_min": CGPA_MIN,
    "cgpa_max": CGPA_MAX,
    "at_risk_threshold": AT_RISK_THRESHOLD,
    "guardrail_rule": "max(raw, past_avg - max_drop) when past_avg >= min_avg; "
    "0-4 clamp always applied",
}


def guardrail(
    raw: float,
    history: list[float] | None,
    *,
    min_avg: float = GUARDRAIL_MIN_AVG,
    max_drop: float = GUARDRAIL_MAX_DROP,
    lo: float = CGPA_MIN,
    hi: float = CGPA_MAX,
) -> dict:
    """Apply the monotonic drop-cap and the hard range clamp.

    The rule is ``value = max(raw, past_avg - max_drop)`` when a history exists
    and ``past_avg >= min_avg``. It is monotonic in ``raw``: a larger raw
    prediction can never produce a smaller guarded value, which the previous
    ``past_avg - max_drop / 2`` floor did not satisfy (a raw prediction just
    below the floor was raised while a much lower one was raised further).

    Returns ``{"value", "applied", "reasons", "past_avg"}``. ``value`` is
    ``None`` when the model produced a non-finite number (for example a student
    with no admission marks *and* no semester history, where every informative
    input is missing).
    """
    if raw is None or not math.isfinite(float(raw)):
        return {"value": None, "applied": False, "reasons": [], "past_avg": None}

    value = float(raw)
    applied = False
    reasons: list[str] = []
    past_avg = None

    if history:
        past_avg = sum(float(g) for g in history) / len(history)
        if past_avg >= min_avg and value < past_avg - max_drop:
            value = past_avg - max_drop
            applied = True
            reasons.append("history_drop_cap")

    clamped = min(max(value, lo), hi)
    if clamped != value:
        applied = True
        reasons.append("range_clamp")
    value = clamped

    return {
        "value": round(value, 2),
        "applied": applied,
        "reasons": reasons,
        "past_avg": round(past_avg, 2) if past_avg is not None else None,
    }


def interval_and_risk(
    raw: float,
    half_width: float | None,
    sigma: float | None,
    *,
    threshold: float = AT_RISK_THRESHOLD,
    lo: float = CGPA_MIN,
    hi: float = CGPA_MAX,
) -> tuple[list[float] | None, float | None]:
    """Nominal 90% band and the model-implied P(final CGPA < threshold).

    The band is ``raw +/- half_width`` where ``half_width`` is the out-of-fold
    90th percentile of absolute residuals stored in the manifest. It is a
    *nominal* band: empirical coverage is measured in ``ml/evaluation``, not
    assumed. The risk figure is a Gaussian-residual probability conditional on
    graduation (it excludes dropout) and is computed from the **raw** model
    output, never from the guardrailed value — otherwise the guardrail would
    silently mask risk at the top of the cohort.
    """
    if raw is None or not math.isfinite(float(raw)):
        return None, None

    raw = float(raw)
    interval = None
    if half_width is not None and half_width > 0:
        # Clamp the centre first, then the band: clamping each edge
        # independently can invert the interval when the raw value is outside
        # the plausible range.
        centre = min(max(raw, lo), hi)
        low = max(lo, centre - half_width)
        high = min(hi, centre + half_width)
        if high < low:
            low, high = high, low
        interval = [round(low, 2), round(high, 2)]

    at_risk = None
    if sigma and sigma > 0:
        z = (threshold - raw) / sigma
        at_risk = round(0.5 * (1.0 + math.erf(z / math.sqrt(2.0))), 4)

    return interval, at_risk
