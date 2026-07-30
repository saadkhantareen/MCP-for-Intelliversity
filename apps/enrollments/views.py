from rest_framework import status
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action

from apps.academics.models import CurriculumCourse, Section, Term
from apps.enrollments.filters import CourseOfferingFilter
from apps.enrollments.models import CourseOffering, Enrollment, FacultyAssignment
from apps.enrollments.serializers import (
    CourseOfferingSerializer,
    EnrollmentSerializer,
    FacultyAssignmentSerializer,
    GenerateCourseOfferingsSerializer,
)


class CourseOfferingViewSet(ModelViewSet):
    queryset = CourseOffering.objects.select_related(
        "curriculum_course__course",
        "term",
        "section__batch",
    ).prefetch_related("faculty_assignments__faculty__base_profile__user")

    serializer_class = CourseOfferingSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]
    filterset_class = CourseOfferingFilter

    @action(
        detail=False,
        methods=["post"],
        url_path="generate-enrollments",
        serializer_class=GenerateCourseOfferingsSerializer,
    )
    def generate_offerings(self, request, pk=None):
        serializer = GenerateCourseOfferingsSerializer(data=request.data)
        serializer.is_validate(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)


