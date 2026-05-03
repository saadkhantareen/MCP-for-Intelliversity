from rest_framework.decorators import action
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.academics.models import (
    AcademicYear,
    Batch,
    Course,
    Curriculum,
    Department,
    FacultyCourse,
    Program,
)
from apps.academics.serializers import (
    AcademicYearSerializer,
    BatchSerializer,
    CourseSerializer,
    CurriculumDetailSerializer,
    CurriculumListSerializer,
    DepartmentSerializer,
    FacultyCourseSerializer,
    ProgramSerializer,
)
from apps.profiles.permissions import IsOwnerOrAdmin


class DepartmentViewSet(ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    @action(detail=False, methods=["get"], url_path="codes")
    def codes(self, request):
        codes = list(self.get_queryset().values_list("code", flat=True))
        return Response(codes)


class ProgramViewSet(ModelViewSet):
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    @action(detail=False, methods=["get"], url_path="codes")
    def codes(self, request):
        codes = list(self.get_queryset().values_list("code", flat=True))
        return Response(codes)


class CourseViewSet(ModelViewSet):
    queryset = Course.objects.select_related("department").prefetch_related(
        "prerequisites"
    )
    serializer_class = CourseSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    @action(detail=True, methods=["get"], url_path="prerequisites")
    def list_prerequisites(self, request, pk=None):
        course = self.get_object()
        codes = list(course.prerequisites.values_list("code", flat=True))
        return Response(codes)


class FacultyCourseViewSet(ModelViewSet):
    queryset = FacultyCourse.objects.select_related("faculty", "course")
    serializer_class = FacultyCourseSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]


class CurriculumViewSet(ModelViewSet):
    queryset = Curriculum.objects.all()
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    def get_serializer_class(self):
        # Returns only curriculum instances for 'GET all'
        if self.action == "list":
            return CurriculumListSerializer
        # Handles full nested data for create, retrieve, and update
        return CurriculumDetailSerializer


class AcademicYearViewSet(ModelViewSet):
    queryset = AcademicYear.objects.prefetch_related("term_set")
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]


class BatchViewSet(ModelViewSet):
    serializer_class = BatchSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    def get_queryset(self):
        user = self.request.user

        base_qs = Batch.objects.select_related(
            "program", "curriculum"
        ).prefetch_related("sections")

        # Admin Logic: See all batches
        if user.groups.filter(name="admin").exists():
            return base_qs

        # Student Logic: See only the batch for their assigned section
        if user.groups.filter(name="student").exists():
            try:
                # Based on related_name="student_profile" in your OneToOneField
                student_profile = user.base_profile.student_profile
                return base_qs.filter(sections__students=student_profile).distinct()

            except AttributeError:
                return base_qs.none()

        # Faculty Logic: See batches containing sections they teach
        if user.groups.filter(name="faculty").exists():
            try:
                # Assuming the related_name on BaseProfile is "faculty_profile"
                faculty_profile = user.base_profile.faculty_profile

                # Tracing the path: Batch -> sections -> course_assignments (FacultyCourseEnrollment) -> faculty
                return base_qs.filter(
                    sections__course_assignments__faculty=faculty_profile
                ).distinct()
            except AttributeError:
                return base_qs.none()

        # 5. Failsafe
        return base_qs.none()
