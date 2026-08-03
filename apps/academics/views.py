from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.academics.filters import RoleBasedBatchFilter
from apps.academics.models import (
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
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

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

    @action(detail=True, methods=["post"], serializer_class=TermActivateSerializer)
    def activate(self, request, pk=None):
        term = self.get_object()
        serializer = self.get_serializer(term, data={})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        response_serializer = TermSerializer(term)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class BatchViewSet(ModelViewSet):
    serializer_class = BatchSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]
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
    permission_classes = [IsAuthenticated, DjangoModelPermissions]
