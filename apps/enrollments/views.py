from rest_framework import status
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.academics.models import CurriculumCourse, Section, Term
from apps.enrollments.models import FacultyCourseAssignment, StudentCourseEnrollment
from apps.enrollments.serializers import (
    FacultyCourseAssignmentSerializer,
    OfferedCourseSerializer,
    StudentCourseEnrollmentSerializer,
)
from apps.profiles.permissions import IsOwnerOrAdmin


class GetCoursesForFacultyEnrollementView(APIView):
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get(self, request):
        section_id = request.query_params.get("section_id")
        semester_number = request.query_params.get("semester_number")

        if not section_id or not semester_number:
            return Response(
                {"detail": "section_id and semester_number are required."},
                status=400,
            )

        section = Section.objects.select_related("batch__curriculum").get(id=section_id)
        curriculum_id = section.batch.curriculum.id

        offered_courses = CurriculumCourse.objects.filter(
            curriculum_id=curriculum_id,
            recommended_semester=semester_number,
        ).select_related("course")

        serializer = OfferedCourseSerializer(offered_courses, many=True)

        return Response(serializer.data)


class FacultyCourseAssignmentViewSet(ModelViewSet):
    queryset = FacultyCourseAssignment.objects.select_related(
        "faculty",
        "course",
        "term",
        "section",
    )
    serializer_class = FacultyCourseAssignmentSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions, IsOwnerOrAdmin]


class GetCoursesForStudentEnrollmentView(APIView):
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get(self, request):
        student_profile = request.user.base_profile.student_profile

        offered_courses = CurriculumCourse.objects.filter(
            curriculum=student_profile.batch.curriculum,
            recommended_semester=student_profile.current_semester,
        ).select_related("course")

        serializer = OfferedCourseSerializer(offered_courses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class StudentCourseEnrollmentListCreateAPIView(APIView):
    serializer_class = StudentCourseEnrollmentSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions, IsOwnerOrAdmin]
    queryset = StudentCourseEnrollment.objects.select_related(
        "course", "term", "section"
    )

    def get(self, request):
        student_profile = request.user.base_profile.student_profile
        active_term = Term.objects.filter(is_active=True).first()

        enrollments = StudentCourseEnrollment.objects.filter(
            student=student_profile, term=active_term
        ).select_related("course", "term", "section")

        serializer = self.serializer_class(enrollments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        enrollment = serializer.save()
        return Response(
            self.serializer_class(enrollment).data,
            status=status.HTTP_201_CREATED,
        )


class StudentCourseEnrollmentDeleteAPIView(APIView):
    serializer_class = StudentCourseEnrollmentSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions, IsOwnerOrAdmin]
    queryset = StudentCourseEnrollment.objects.select_related(
        "course", "term", "section"
    )

    def delete(self, request, pk):
        student_profile = request.user.base_profile.student_profile
        active_term = Term.objects.filter(is_active=True).first()

        try:
            enrollment = StudentCourseEnrollment.objects.get(
                id=pk, student=student_profile, term=active_term
            )
        except StudentCourseEnrollment.DoesNotExist:
            return Response(
                {"detail": "Enrollment not found"}, status=status.HTTP_404_NOT_FOUND
            )

        enrollment.delete()

        return Response(
            {"message": "Course DROPPED successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )
