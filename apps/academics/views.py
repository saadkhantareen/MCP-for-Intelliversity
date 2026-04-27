from rest_framework.viewsets import ModelViewSet
from apps.academics.models import Course, Department, Program
from apps.academics.serializers import (
    CourseSerializer,
    DepartmentSerializer,
    ProgramSerializer,
)
from rest_framework.decorators import action
from rest_framework.response import Response


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
