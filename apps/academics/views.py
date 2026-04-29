from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.academics.models import (
    AcademicYear,
    Batch,
    Course,
    Curriculum,
    Department,
    Program,
)
from apps.academics.serializers import (
    AcademicYearSerializer,
    BatchSerializer,
    CourseSerializer,
    CurriculumDetailSerializer,
    CurriculumListSerializer,
    DepartmentSerializer,
    ProgramSerializer,
)


class DepartmentViewSet(ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = (
        []
    )  # Set appropriate permissions (e.g., IsAuthenticated, IsAdminUser)

    # def get_permissions(self):
    #     """
    #     Instantiates and returns the list of permissions that this view requires.
    #     """
    #     if self.action == 'list':
    #         permission_classes = [IsAuthenticated]
    #     else:
    #         permission_classes = [IsAdminUser]
    #     return [permission() for permission in permission_classes]
    @action(detail=False, methods=["get"], url_path="codes")
    def codes(self, request):
        codes = list(self.get_queryset().values_list("code", flat=True))
        return Response(codes)


class ProgramViewSet(ModelViewSet):
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer
    permission_classes = []

    @action(detail=False, methods=["get"], url_path="codes")
    def codes(self, request):
        codes = list(self.get_queryset().values_list("code", flat=True))
        return Response(codes)


class CourseViewSet(ModelViewSet):
    queryset = Course.objects.select_related("department").prefetch_related(
        "prerequisites"
    )
    serializer_class = CourseSerializer
    permission_classes = []

    @action(detail=True, methods=["get"], url_path="prerequisites")
    def list_prerequisites(self, request, pk=None):
        course = self.get_object()
        codes = list(course.prerequisites.values_list("code", flat=True))
        return Response(codes)


class CurriculumViewSet(ModelViewSet):
    queryset = Curriculum.objects.all()
    permission_classes = []

    def get_serializer_class(self):
        # Returns only curriculum instances for 'GET all'
        if self.action == "list":
            return CurriculumListSerializer
        # Handles full nested data for create, retrieve, and update
        return CurriculumDetailSerializer


class AcademicYearViewSet(ModelViewSet):
    queryset = AcademicYear.objects.prefetch_related("term_set")
    serializer_class = AcademicYearSerializer
    permission_classes = []


class BatchViewSet(ModelViewSet):
    queryset = (
        Batch.objects.all()
        .select_related("program", "curriculum")
        .prefetch_related("sections")
    )
    serializer_class = BatchSerializer

    # Example of simple RBAC integration
    def get_permissions(self):
        pass
