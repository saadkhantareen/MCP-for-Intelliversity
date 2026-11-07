"""HTTP surface for the bundled CGPA models.

Authorisation is default-deny: a student may forecast themselves, admin and
faculty may forecast any student **in their own tenant**, and every other
authenticated account is refused. There is no "staff by elimination" path.

Every endpoint maps a bad *request* to 400/403/404 and a broken *deployment*
(missing, corrupt or mismatched artifacts) to 503. Nothing in this module
returns 500 with internals in the body.
"""

from __future__ import annotations

import json
import logging
import math

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.predictions import services
from apps.predictions.serializers import CGPAForecastRequestSerializer
from apps.profiles.models import StudentProfile
from apps.profiles.permissions import IsAdminOrFaculty
from apps.tenants.context import get_current_tenant
from apps.tenants.router import TenantNotResolved

logger = logging.getLogger(__name__)

MAX_SEARCH_LENGTH = 100

#: Deployment faults, not request faults. Every one of these becomes a 503 with
#: a generic body; the detail goes to the log, not to the caller.
FAULT_EXCEPTIONS = (
    ImproperlyConfigured,
    FileNotFoundError,
    KeyError,
    json.JSONDecodeError,
    OSError,
    ImportError,
)


def _fault_response(exc: Exception, endpoint: str) -> Response:
    logger.error(
        "cgpa_prediction_unavailable endpoint=%s error=%s detail=%s",
        endpoint,
        type(exc).__name__,
        exc,
    )
    return Response(
        {
            "detail": (
                "Prediction service unavailable. The shipped model bundle could "
                "not be loaded or verified."
            ),
            "code": "artifact_unavailable",
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _tenant_fault_response(exc: Exception, endpoint: str) -> Response:
    logger.error("cgpa_tenant_unresolved endpoint=%s detail=%s", endpoint, exc)
    return Response(
        {
            "detail": "Tenant could not be resolved for this request.",
            "code": "tenant_unresolved",
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _require_tenant():
    """A tenant-scoped endpoint must not run without a resolved tenant."""
    tenant = get_current_tenant()
    if tenant is None:
        raise TenantNotResolved(
            "No tenant is in context for this request; refusing to touch "
            "tenant-scoped data."
        )
    return tenant


def _caller_is_student(user) -> bool:
    return bool(getattr(user, "is_student", False))


def _caller_is_staff(user) -> bool:
    return bool(getattr(user, "is_admin", False) or getattr(user, "is_faculty", False))


def _resolve_student(request, student_id) -> StudentProfile:
    """Default-deny student resolution.

    * student -> themselves only;
    * admin/faculty -> any student in this tenant (tenant-wide in the demo);
    * anyone else -> 403.
    """
    user = request.user

    if _caller_is_student(user):
        own = get_object_or_404(
            StudentProfile.objects.select_related("base_profile", "batch"),
            base_profile__user=user,
        )
        if student_id and str(student_id) != str(own.id):
            raise PermissionDenied("Students can only request their own forecast.")
        return own

    if _caller_is_staff(user):
        if not student_id:
            raise ValidationError(
                {"student_id": "Required for staff accounts; students may omit it."}
            )
        return get_object_or_404(
            StudentProfile.objects.select_related("base_profile", "batch"),
            id=student_id,
        )

    raise PermissionDenied(
        "This account has no role that may request a CGPA forecast."
    )


class CGPAForecastView(APIView):
    """Forecast for one student.

    The model is the vendor-shipped one for the student's current semester; a
    university cannot substitute its own data or model.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "predictions"

    @extend_schema(request=CGPAForecastRequestSerializer, responses={200: dict})
    def post(self, request):
        payload = CGPAForecastRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._forecast(request, payload.validated_data)

    def get(self, request):
        # Pass only the parameters that were actually supplied. Sending None
        # for an optional UUID/integer field is a validation error in DRF, so
        # a student calling this endpoint with no query string would get 400.
        data = {
            key: request.query_params.get(key)
            for key in ("student_id", "semester")
            if request.query_params.get(key) not in (None, "")
        }
        payload = CGPAForecastRequestSerializer(data=data)
        payload.is_valid(raise_exception=True)
        return self._forecast(request, payload.validated_data)

    def _forecast(self, request, data):
        try:
            _require_tenant()
        except TenantNotResolved as exc:
            return _tenant_fault_response(exc, "forecast")

        student = _resolve_student(request, data.get("student_id"))

        try:
            result = services.predict_student(student, data.get("semester"))
        except services.InvalidSemester as exc:
            raise ValidationError({"semester": str(exc)}) from exc
        except FAULT_EXCEPTIONS as exc:
            return _fault_response(exc, "forecast")

        try:
            services.record_prediction(student, result)
        except FAULT_EXCEPTIONS as exc:
            # The forecast itself is still valid; failing the request would hide
            # a working prediction because the audit write failed.
            logger.error("cgpa_prediction_audit_failed error=%s", exc)

        return Response(result)


class ModelInfoView(APIView):
    """Provenance and health for the shipped model bundle.

    Returns 200 only when all eight artifacts are present, hash-verified and
    loadable. A provenance-only payload with missing models must never be
    reported as healthy.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            payload = services.model_info()
        except FAULT_EXCEPTIONS as exc:
            return _fault_response(exc, "models")

        health = payload.get("health", {})
        if not health.get("ok"):
            return Response(
                {
                    "detail": (
                        "Prediction service unavailable. At least one shipped model "
                        "failed its health check."
                    ),
                    "code": "artifact_unavailable",
                    "health": health,
                    "semesters": payload.get("semesters"),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(payload)


class CohortForecastView(APIView):
    """Forecast a whole cohort, worst first — the early-warning list.

    Ordering, filtering and pagination are server-side and applied in that
    order (filter -> sort -> paginate), so ``total_count`` is the number of
    students that actually matched, not the page size.

    Reads do not write audit rows: only a single-student forecast is audited.
    Opening the drawer in the UI calls the single-student endpoint, which does
    write one.
    """

    permission_classes = [IsAuthenticated, IsAdminOrFaculty]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "predictions_cohort"

    def get(self, request):
        try:
            _require_tenant()
        except TenantNotResolved as exc:
            return _tenant_fault_response(exc, "cohort")

        params = request.query_params

        def _int(name, default, low, high):
            raw = params.get(name)
            if raw in (None, ""):
                return default
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise ValidationError({name: "Must be an integer."})
            return max(low, min(value, high))

        page = _int("page", 1, 1, 100000)
        page_size = _int("page_size", 50, 1, 1000)

        raw_threshold = params.get("threshold", "")
        if raw_threshold in (None, ""):
            threshold = 0.5
        else:
            try:
                threshold = float(raw_threshold)
            except (TypeError, ValueError):
                raise ValidationError({"threshold": "Must be a number between 0 and 1."})
            if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
                raise ValidationError(
                    {"threshold": "Must be a finite number between 0 and 1."}
                )

        at_risk_only = str(params.get("at_risk", "")).lower() in {"1", "true", "yes"}

        search = (params.get("search") or "").strip()
        if len(search) > MAX_SEARCH_LENGTH:
            raise ValidationError(
                {"search": f"Must be at most {MAX_SEARCH_LENGTH} characters."}
            )

        students = (
            StudentProfile.objects.select_related(
                "base_profile__user", "batch__program", "section", "admission"
            )
            .prefetch_related("term_records__term")
            .order_by("registration_id")
        )
        if search:
            students = students.filter(
                Q(registration_id__icontains=search)
                | Q(base_profile__user__first_name__icontains=search)
                | Q(base_profile__user__last_name__icontains=search)
                | Q(base_profile__user__email__icontains=search)
            )

        cap = int(getattr(settings, "CGPA_COHORT_MAX_STUDENTS", 5000))
        student_list = list(students[:cap])

        rows, skipped = [], []
        try:
            for student in student_list:
                # One prefetch for every student; predict_student reuses it
                # instead of issuing a query per student.
                records = list(student.term_records.all())
                try:
                    result = services.predict_student(student, records=records)
                except services.InvalidSemester as exc:
                    skipped.append(
                        {"student_id": str(student.id), "reason": str(exc)}
                    )
                    continue

                if not result["meaningful"]:
                    skipped.append(
                        {
                            "student_id": str(student.id),
                            "reason": "insufficient_inputs: no admission marks and no completed semesters",
                        }
                    )
                    continue

                user = student.base_profile.user
                rows.append(
                    {
                        "student_id": str(student.id),
                        "registration_id": student.registration_id,
                        "name": f"{user.first_name} {user.last_name}".strip()
                        or user.email,
                        "program": getattr(student.batch.program, "name", None)
                        if student.batch_id
                        else None,
                        "semester": result["semester"],
                        "completed_semesters": result["completed_semesters"],
                        "current_cgpa": result["current_cgpa"],
                        "predicted_cgpa": result["predicted_cgpa"],
                        "raw_prediction": result["raw_prediction"],
                        "prediction_interval_90": result["prediction_interval_90"],
                        "at_risk_probability": result["at_risk_probability"],
                        "guardrail_applied": result["guardrail_applied"],
                        "has_admission_marks": not any(
                            w.startswith("admission_marks_missing")
                            for w in result["warnings"]
                        ),
                        "meaningful": result["meaningful"],
                    }
                )
        except FAULT_EXCEPTIONS as exc:
            return _fault_response(exc, "cohort")

        # Filter before paginating, and sort before slicing, so the page is the
        # worst N of the matching set rather than the worst N of the first 300.
        if at_risk_only:
            rows = [
                row
                for row in rows
                if (row["at_risk_probability"] or 0.0) >= threshold
            ]

        rows.sort(
            key=lambda row: (-(row["at_risk_probability"] or -1.0), row["predicted_cgpa"] or 99.0)
        )

        total_count = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        page_rows = rows[start:end]
        total_pages = max(1, math.ceil(total_count / page_size)) if total_count else 0

        return Response(
            {
                "count": len(page_rows),
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": end < total_count,
                "has_previous": page > 1 and total_count > 0,
                "at_risk_threshold": threshold,
                "results": page_rows,
                "skipped": skipped[:50],
                "skipped_count": len(skipped),
                "truncated": len(student_list) >= cap,
                "disclaimer": (
                    "Statistical estimates from a pre-trained model; not official "
                    "results. Cohort order is advisor triage only and must not be "
                    "used as the sole basis for probation, scholarship or "
                    "progression decisions."
                ),
            }
        )
