from datetime import date

from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.academics.filters import RoleBasedBatchFilter
from apps.academics.models import (
    AcademicPolicy,
    AcademicYear,
    Batch,
    Course,
    Curriculum,
    Department,
    FacultyCourse,
    Program,
    Section,
    Term,
)
from apps.academics.serializers import (
    AcademicPolicySerializer,
    AcademicYearActivateSerializer,
    AcademicYearSerializer,
    BatchAutoSectionSerializer,
    BatchSerializer,
    CourseSerializer,
    CurriculumDetailSerializer,
    CurriculumListSerializer,
    DepartmentSerializer,
    FacultyCourseSerializer,
    ProgramSerializer,
    SectionSerializer,
    TermActivateSerializer,
    TermSerializer,
)
from apps.enrollments.models import CourseOffering, Enrollment
from apps.profiles.models import FacultyProfile, StudentProfile
from apps.profiles.permissions import IsAdmin


class AcademicPolicyView(generics.RetrieveUpdateAPIView):
    serializer_class = AcademicPolicySerializer
    permission_classes = [DjangoModelPermissions, IsAdmin]
    queryset = AcademicPolicy.objects.all()

    def get_object(self):
        try:
            return AcademicPolicy.load()
        except AcademicPolicy.DoesNotExist:
            return Response(
                {"detail": "Academic Policy has not been initialized."},
                status=status.HTTP_404_NOT_FOUND,
            )


class DepartmentViewSet(ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [DjangoModelPermissions]

    @action(detail=False, methods=["get"], url_path="codes")
    def codes(self, request):
        codes = list(self.get_queryset().values_list("code", flat=True))
        return Response(codes)


class ProgramViewSet(ModelViewSet):
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer
    permission_classes = [DjangoModelPermissions]

    @action(detail=False, methods=["get"], url_path="codes")
    def codes(self, request):
        codes = list(self.get_queryset().values_list("code", flat=True))
        return Response(codes)


class CourseViewSet(ModelViewSet):
    queryset = Course.objects.select_related("department").prefetch_related(
        "prerequisites"
    )
    serializer_class = CourseSerializer
    permission_classes = [DjangoModelPermissions]

    @action(detail=True, methods=["get"], url_path="prerequisites")
    def list_prerequisites(self, request, pk=None):
        course = self.get_object()
        codes = list(course.prerequisites.values_list("code", flat=True))
        return Response(codes)


class FacultyCourseViewSet(ModelViewSet):
    queryset = FacultyCourse.objects.select_related("faculty", "course")
    serializer_class = FacultyCourseSerializer
    permission_classes = [DjangoModelPermissions]


class CurriculumViewSet(ModelViewSet):
    queryset = Curriculum.objects.select_related("program").prefetch_related("courses")
    permission_classes = [DjangoModelPermissions]

    def get_serializer_class(self):
        # Returns only curriculum instances for 'GET all'
        if self.action == "list":
            return CurriculumListSerializer
        # Handles full nested data for create, retrieve, and update
        return CurriculumDetailSerializer


class AcademicYearViewSet(ModelViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [DjangoModelPermissions]

    # detail=True means this action applies to a single instance (requires an ID in the URL)
    @extend_schema(request=None, responses={200: AcademicYearSerializer})
    @action(
        detail=True, methods=["post"], serializer_class=AcademicYearActivateSerializer
    )
    def activate(self, request, pk=None):
        # Fetch the specific academic year using the ID from the URL
        academic_year = self.get_object()
        # Initialize the action serializer with the instance and empty data
        # data={} is required to trigger the validation cycle
        serializer = self.get_serializer(academic_year, data={})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        response_serializer = AcademicYearSerializer(academic_year)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class TermViewSet(ModelViewSet):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    permission_classes = [DjangoModelPermissions]

    def get_queryset(self):
        queryset = super().get_queryset()
        academic_year_id = self.request.query_params.get("academic_year")
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)

        return queryset

    @action(detail=True, methods=["post"], serializer_class=TermActivateSerializer)
    def activate(self, request, pk=None):
        term = self.get_object()

        serializer = self.get_serializer(term, data={})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(TermSerializer(term).data, status=status.HTTP_200_OK)


class BatchViewSet(ModelViewSet):
    serializer_class = BatchSerializer
    permission_classes = [DjangoModelPermissions]
    filter_backends = [RoleBasedBatchFilter]

    def get_queryset(self):
        return Batch.objects.select_related("program", "curriculum").prefetch_related(
            "sections"
        )

    @action(
        detail=True,
        methods=["post"],
        serializer_class=BatchAutoSectionSerializer,
        url_path="auto-generate-sections",
    )
    def auto_generate_sections(self, request, pk=None):
        batch = self.get_object()

        serializer = BatchAutoSectionSerializer(
            data=request.data, context={"batch": batch}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SectionViewSet(ModelViewSet):
    queryset = Section.objects.select_related("batch")
    serializer_class = SectionSerializer
    permission_classes = [DjangoModelPermissions]

    def get_queryset(self):
        queryset = super().get_queryset()
        batch_id = self.request.query_params.get("batch")
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)

        return queryset


def build_enrollment_buckets(period, created_dates, today=None):
    """Group enrollment datetimes into chart buckets for one period.

    ``created_dates`` is an iterable of datetimes (only year/month are
    used). Returns ``[{"month": label, "value": count}, ...]`` in time
    order. Buckets with no enrollments are real zeros, not missing data.
    An unknown period falls back to the last 6 months.
    """
    today = today or timezone.now().date()
    period = period if period in ("6M", "1Y", "All") else "6M"

    if period == "All":
        years = [d.year for d in created_dates]
        start_year = min(years) if years else today.year - 4
        counts = {}
        for d in created_dates:
            counts[d.year] = counts.get(d.year, 0) + 1
        return [
            {"month": str(year), "value": counts.get(year, 0)}
            for year in range(start_year, today.year + 1)
        ]

    months = 6 if period == "6M" else 12
    label_fmt = "%b" if period == "6M" else "%b %y"
    # Walk back to the first month of the window.
    year, month = today.year, today.month
    for _ in range(months - 1):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    counts = {}
    for d in created_dates:
        counts[(d.year, d.month)] = counts.get((d.year, d.month), 0) + 1
    buckets = []
    for _ in range(months):
        buckets.append(
            {
                "month": date(year, month, 1).strftime(label_fmt),
                "value": counts.get((year, month), 0),
            }
        )
        month += 1
        if month == 13:
            month, year = 1, year + 1
    return buckets


class DashboardStatsView(APIView):
    """Live counts for the admin dashboard, scoped to the current tenant.

    Read-only, admin only. The dashboard previously showed hardcoded demo
    numbers; every figure here is counted from this tenant's database, so
    a tenant with no offerings yet honestly reports 0.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        period = request.query_params.get("period", "6M")
        departments = Department.objects.all()
        dept_counts = {
            row["batch__program__department__name"]: row["n"]
            for row in StudentProfile.objects.values(
                "batch__program__department__name"
            ).annotate(n=Count("id"))
        }
        breakdown = [
            {"name": dept.name, "students": dept_counts.get(dept.name, 0)}
            for dept in departments.order_by("name")
        ]
        # Students whose batch has no department (including no batch at all)
        # are not inside any department bar; list them instead of dropping
        # them from the breakdown total.
        unassigned = StudentProfile.objects.filter(
            batch__program__department__isnull=True
        ).count()
        if unassigned:
            breakdown.append({"name": "Unassigned", "students": unassigned})
        enrolled_dates = list(
            Enrollment.objects.values_list("created_at", flat=True)
        )
        return Response(
            {
                "students": StudentProfile.objects.count(),
                "faculty": FacultyProfile.objects.count(),
                "departments": departments.count(),
                "programs": Program.objects.count(),
                "courses": Course.objects.count(),
                "offerings": CourseOffering.objects.count(),
                "enrollments": Enrollment.objects.count(),
                "departments_breakdown": breakdown,
                "enrollments_by_month": build_enrollment_buckets(
                    period, enrolled_dates
                ),
            }
        )
