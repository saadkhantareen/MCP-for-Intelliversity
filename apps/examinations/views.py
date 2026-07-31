from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.academics.models import CourseOffering, StudentTermRecord, Term
from apps.accounts.models import Roles
from apps.examinations.models import (
    Assessment,
    AssessmentPolicy,
    AssessmentType,
    GradePolicy,
    GradeScale,
    StudentAssessment,
)
from apps.examinations.serializers import (
    AssessmentPolicySerializer,
    AssessmentSerializer,
    AssessmentTypeSerializer,
    FacultyGradebookUpdateSerializer,
    GradePolicySerializer,
    GradeScaleSerializer,
    StudentAssessmentSerializer,
)

from .permissions import IsAdminUserOrReadOnly, IsFacultyUser
from .services import calculate_and_save_term_results

# 1. ADMIN APIS (Types, Policies & Grading Setup)


class AssessmentTypeViewSet(viewsets.ModelViewSet):
    queryset = AssessmentType.objects.all()
    serializer_class = AssessmentTypeSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["is_active"]
    search_fields = ["name", "code"]


class AssessmentPolicyViewSet(viewsets.ModelViewSet):
    queryset = AssessmentPolicy.objects.select_related("term", "assessment_type").all()
    serializer_class = AssessmentPolicySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["term", "assessment_type"]


class GradePolicyViewSet(viewsets.ModelViewSet):
    queryset = (
        GradePolicy.objects.prefetch_related("grade_scales")
        .select_related("term")
        .all()
    )
    serializer_class = GradePolicySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filterset_fields = ["term"]


class GradeScaleViewSet(viewsets.ModelViewSet):
    queryset = GradeScale.objects.select_related("grade_policy").all()
    serializer_class = GradeScaleSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filterset_fields = ["grade_policy"]


# 2. FACULTY APIS (Course Offering Assessments & Marks Entry)


class FacultyAssessmentViewSet(viewsets.ModelViewSet):
    """
    Faculty endpoints mapped to CourseOffering -> FacultyCourse -> FacultyProfile
    """

    queryset = Assessment.objects.select_related(
        "course_offering__faculty_course__faculty",
        "course_offering__faculty_course__course",
        "assessment_type",
    ).all()
    serializer_class = AssessmentSerializer
    permission_classes = [IsFacultyUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["course_offering", "assessment_type", "marks_submitted"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # Filtering according to CourseOffering -> FacultyCourse relation
        if getattr(user, "role", None) == Roles.FACULTY:
            return queryset.filter(
                course_offering__faculty_course__faculty=user.profile
            )
        return queryset

    @action(detail=True, methods=["get"], url_path="gradebook")
    def gradebook(self, request, pk=None):
        """Returns all enrolled student scores for a given assessment."""
        assessment = self.get_object()
        student_assessments = StudentAssessment.objects.filter(
            assessment=assessment
        ).select_related("student")

        serializer = StudentAssessmentSerializer(student_assessments, many=True)
        return Response(
            {
                "assessment_id": assessment.id,
                "assessment_title": assessment.title,
                "total_marks": assessment.total_marks,
                "marks_submitted": assessment.marks_submitted,
                "students": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="bulk-grade")
    def bulk_grade(self, request, pk=None):
        """Bulk update or finalize marks for a class section."""
        assessment = self.get_object()

        if assessment.marks_submitted:
            return Response(
                {"detail": "Assessment marks have already been finalized and locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = FacultyGradebookUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        total_marks = serializer.validated_data["total_marks"]
        marks_submitted = serializer.validated_data["marks_submitted"]
        students_marks = serializer.validated_data["students_marks"]

        with transaction.atomic():
            assessment.total_marks = total_marks
            assessment.marks_submitted = marks_submitted
            assessment.save()

            for item in students_marks:
                StudentAssessment.objects.update_or_create(
                    assessment=assessment,
                    student_id=item["student_id"],
                    defaults={
                        "obtained_marks": item.get("obtained_marks"),
                        "remarks": item.get("remarks", ""),
                    },
                )

        return Response(
            {
                "message": "Gradebook updated successfully.",
                "marks_submitted": assessment.marks_submitted,
            },
            status=status.HTTP_200_OK,
        )


class FacultyStudentAssessmentViewSet(viewsets.ModelViewSet):
    """
    Allows Faculty to view, add or edit marks for an individual student.
    """

    queryset = StudentAssessment.objects.select_related(
        "assessment__course_offering__faculty_course", "student"
    ).all()
    serializer_class = StudentAssessmentSerializer
    permission_classes = [IsFacultyUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["assessment", "student"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if getattr(user, "role", None) == Roles.FACULTY:
            return queryset.filter(
                assessment__course_offering__faculty_course__faculty=user.profile
            )
        return queryset


# ==============================================================================
# 3. RESULT, SGPA, & CGPA APIS
# ==============================================================================


class StudentResultViewSet(viewsets.ViewSet):
    """
    View Student Term Results, SGPA (from StudentTermRecord) and Overall CGPA (from StudentProfile).
    """

    def list(self, request):
        user = request.user
        student_profile = None

        if getattr(user, "role", None) == Roles.STUDENT:
            student_profile = getattr(user, "profile", None)
        else:
            student_id = request.query_params.get("student_id")
            if not student_id:
                return Response(
                    {
                        "detail": "student_id query parameter is required for Admin/Faculty."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            from apps.profiles.models import StudentProfile

            student_profile = StudentProfile.objects.filter(id=student_id).first()

        if not student_profile:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Retrieve per-term SGPA and Standing records
        term_records = StudentTermRecord.objects.filter(
            student=student_profile
        ).select_related("term")

        semesters_data = []
        for tr in term_records:
            semesters_data.append(
                {
                    "term_id": tr.term.id,
                    "term_name": tr.term.name,
                    "sgpa": tr.gpa,
                    "academic_standing": tr.academic_standing,
                    "status": tr.status,
                }
            )

        return Response(
            {
                "student_id": student_profile.id,
                "overall_cgpa": getattr(student_profile, "cgpa", 0.0),
                "term_records": semesters_data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="calculate-term-result")
    def calculate_term(self, request):
        """
        Admin action to finalize term marks and compute SGPA & CGPA for a student.
        Payload: {"student_id": 1, "term_id": 2}
        """
        student_id = request.data.get("student_id")
        term_id = request.data.get("term_id")

        if not student_id or not term_id:
            return Response(
                {"detail": "student_id and term_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.profiles.models import StudentProfile

        student = StudentProfile.objects.filter(id=student_id).first()
        term = Term.objects.filter(id=term_id).first()

        if not student or not term:
            return Response(
                {"detail": "Student or Term not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        summary = calculate_and_save_term_results(student, term)
        return Response(summary, status=status.HTTP_200_OK)
