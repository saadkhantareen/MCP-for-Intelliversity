from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.response import Response
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
