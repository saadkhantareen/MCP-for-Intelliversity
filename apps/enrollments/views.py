from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.enrollments.filters import CourseOfferingFilter
from apps.enrollments.models import CourseOffering, Enrollment, FacultyAssignment
from apps.enrollments.serializers import (
    CourseOfferingSerializer,
    EnrollmentSerializer,
    FacultyAssignmentSerializer,
    GenerateCourseOfferingsSerializer,
)
from apps.profiles.permissions import (
    IsAdminOrFaculty,
    IsAdminOrStudent,
    IsFaculty,
    IsStudent,
)


class CourseOfferingViewSet(ModelViewSet):
    queryset = CourseOffering.objects.select_related(
        "curriculum_course__course",
        "term",
        "section__batch",
    ).prefetch_related("faculty_assignments__faculty__base_profile__user")

    serializer_class = CourseOfferingSerializer
    permission_classes = [DjangoModelPermissions]
    filterset_class = CourseOfferingFilter

    @action(
        detail=False,
        methods=["post"],
        url_path="generate-offerings",
        serializer_class=GenerateCourseOfferingsSerializer,
    )
    def generate_offerings(self, request, pk=None):
        serializer = GenerateCourseOfferingsSerializer(data=request.data)
        serializer.is_validate(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=["get"],
        url_path="me/faculty",
        permission_classes=[DjangoModelPermissions, IsFaculty],
    )
    def faculty_offerings(self, request):

        try:
            faculty_profile = request.user.base_profile.faculty_profile
        except AttributeError:
            return Response(
                {"detail": "Faculty profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        queryset = (
            CourseOffering.objects.select_related(
                "curriculum_course__course",
                "term",
                "section__batch",
            )
            .filter(
                curriculum_course__course__available_faculty__faculty=faculty_profile
            )
            .distinct()
        )

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["get"],
        url_path="me/student",
        permission_classes=[DjangoModelPermissions, IsStudent],
    )
    def student_offerings(self, request):

        try:
            student_profile = request.user.base_profile.student_profile
        except AttributeError:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        current_semester = student_profile.batch.expected_current_semester
        if current_semester == 1:
            # return empty offerings for first semester students as they will be enrolled automatically.
            return Response([], status=status.HTTP_200_OK)

        base_queryset = CourseOffering.objects.select_related(
            "curriculum_course__course",
            "term",
            "section__batch",
        ).filter(
            section__batch=student_profile.batch,
            curriculum_course__recommended_semester=current_semester,
        )

        # TODO: add failed course logic here when we have a way to track failed courses from examinations module.
        retake_course_ids = Enrollment.objects.filter(
            student=student_profile,
            status__in=[
                "dropped",
                "withdrawn",
            ],
        ).values_list("course_offering__curriculum_course__course_id", flat=True)

        retake_queryset = CourseOffering.objects.select_related(
            "curriculum_course__course",
            "term",
            "section__batch",
        ).filter(
            section__batch=student_profile.batch,
            curriculum_course__course_id__in=retake_course_ids,
        )

        queryset = (base_queryset | retake_queryset).distinct()

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FacultyAssignmentViewSet(ModelViewSet):

    serializer_class = FacultyAssignmentSerializer
    permission_classes = [DjangoModelPermissions, IsAdminOrFaculty]

    def get_queryset(self):
        queryset = FacultyAssignment.objects.select_related(
            "course_offering__curriculum_course__course",
            "course_offering__term",
            "course_offering__section__batch",
            "faculty__base_profile__user",
        )

        user = self.request.user

        if user.is_admin:
            return queryset

        if user.is_faculty:
            return queryset.filter(faculty__base_profile__user=user)

        return queryset.none()


class EnrollmentViewSet(ModelViewSet):

    serializer_class = EnrollmentSerializer
    permission_classes = [DjangoModelPermissions, IsAdminOrStudent]

    def get_queryset(self):
        queryset = Enrollment.objects.select_related(
            "course_offering__curriculum_course__course",
            "course_offering__term",
            "course_offering__section__batch",
            "student__base_profile__user",
        )

        user = self.request.user

        if user.is_admin:
            return queryset

        if user.is_student:
            return queryset.filter(student__base_profile__user=user)

        return queryset.none()
