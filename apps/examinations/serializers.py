from rest_framework import serializers
from django.db.models import Sum

from .models import (
    AssessmentType,
    AssessmentPolicy,
    Assessment,
    StudentAssessment,
    GradePolicy,
    GradeScale,
)


class AssessmentTypeSerializer(serializers.ModelSerializer):
    """
    PURPOSE:
    Handles university-level assessment categories (e.g., Quiz, Assignment, Midterm, Final Exam).

    VALIDATIONS:
    - Automatically converts the 'code' field to uppercase (e.g., 'quiz' -> 'QUIZ').
    """

    class Meta:
        model = AssessmentType
        fields = [
            "id",
            "name",
            "code",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_code(self, value):
        return value.upper()



class AssessmentPolicySerializer(serializers.ModelSerializer):
    """
    PURPOSE:
    Configures university/admin assessment policy per academic term (e.g., defining 
    how many quizzes/midterms exist and their total percentage weightage).

    VALIDATIONS:
    1. Active Status Check: Prevents assigning an inactive AssessmentType to a policy.
    2. Total Weightage Check: Ensures the cumulative policy weightage for a term 
       does not exceed 100%.
    """

    assessment_type_name = serializers.CharField(
        source="assessment_type.name", read_only=True
    )

    class Meta:
        model = AssessmentPolicy
        fields = [
            "id",
            "term",
            "assessment_type",
            "assessment_type_name",
            "number_of_assessments",
            "total_weightage",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        term = attrs.get("term", getattr(self.instance, "term", None))
        assessment_type = attrs.get(
            "assessment_type", getattr(self.instance, "assessment_type", None)
        )
        total_weightage = attrs.get(
            "total_weightage", getattr(self.instance, "total_weightage", None)
        )

        # 1. Ensure the linked AssessmentType is active
        if assessment_type and not assessment_type.is_active:
            raise serializers.ValidationError({
                "assessment_type": "Cannot assign an inactive assessment type to a policy."
            })

        # 2. Ensure total term weightage does not exceed 100%
        if term and total_weightage is not None:
            existing_policies = AssessmentPolicy.objects.filter(term=term)
            if self.instance:
                existing_policies = existing_policies.exclude(pk=self.instance.pk)

            current_total = (
                existing_policies.aggregate(sum=Sum("total_weightage"))["sum"] or 0
            )

            if current_total + total_weightage > 100:
                remaining = 100 - current_total
                raise serializers.ValidationError({
                    "total_weightage": f"Total weightage for term '{term}' cannot exceed 100%. Remaining available: {remaining}%."
                })

        return attrs


class GradeScaleSerializer(serializers.ModelSerializer):
    """
    PURPOSE:
    Handles individual grade boundaries within a Grade Policy (e.g., Grade 'A': 85.00% to 100.00%, Points: 4.00).

    VALIDATIONS:
    1. Percentage Range Check: min_percentage must be strictly less than max_percentage.
    2. Bounds Check: Percentage values must be between 0.00 and 100.00.
    """

    class Meta:
        model = GradeScale
        fields = [
            "id",
            "grade_policy",
            "grade",
            "min_percentage",
            "max_percentage",
            "grade_points",
            "remarks",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        min_pct = attrs.get("min_percentage", getattr(self.instance, "min_percentage", None))
        max_pct = attrs.get("max_percentage", getattr(self.instance, "max_percentage", None))

        if min_pct is not None and max_pct is not None:
            if min_pct >= max_pct:
                raise serializers.ValidationError({
                    "min_percentage": "Minimum percentage must be less than maximum percentage."
                })

            if min_pct < 0 or max_pct > 100:
                raise serializers.ValidationError(
                    "Percentage range must fall between 0 and 100."
                )

        return attrs



class GradePolicySerializer(serializers.ModelSerializer):
    """
    PURPOSE:
    Manages the overarching grading policy for a term and nests its corresponding GradeScales.

    VALIDATIONS:
    - Overlap Check: Ensures that grade scale percentage ranges inside a policy do not overlap each other.
    """

    grade_scales = GradeScaleSerializer(many=True, read_only=True)

    class Meta:
        model = GradePolicy
        fields = [
            "id",
            "term",
            "name",
            "description",
            "grade_scales",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]



class AssessmentSerializer(serializers.ModelSerializer):
    """
    PURPOSE:
    Manages individual assessment instances (e.g., Quiz 1, Midterm 1) linked to a Course Offering.

    VALIDATIONS:
    1. Lock Check: Prevents modifying 'total_marks' once marks have been finalized (marks_submitted=True).
    2. Finalize Check: Requires 'total_marks' to be set before marks can be finalized.
    """

    title = serializers.ReadOnlyField()

    class Meta:
        model = Assessment
        fields = [
            "id",
            "course_offering",
            "assessment_type",
            "sequence_number",
            "title",
            "assessment_date",
            "total_marks",
            "marks_submitted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "title", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = self.instance
        marks_submitted = attrs.get(
            "marks_submitted", getattr(instance, "marks_submitted", False)
        )
        total_marks = attrs.get(
            "total_marks", getattr(instance, "total_marks", None)
        )

        # 1. Prevent editing total marks if already finalized
        if instance and instance.marks_submitted:
            if "total_marks" in attrs and attrs["total_marks"] != instance.total_marks:
                raise serializers.ValidationError({
                    "total_marks": "Total marks cannot be modified after results have been finalized."
                })

        # 2. Require valid total marks prior to final submission
        if marks_submitted and (total_marks is None or total_marks <= 0):
            raise serializers.ValidationError({
                "marks_submitted": "Cannot finalize assessment without specifying valid total marks."
            })

        return attrs


class StudentAssessmentSerializer(serializers.ModelSerializer):
    """
    PURPOSE:
    Displays or updates an individual student's assessment score.

    VALIDATIONS:
    1. Lock Check: Blocks modifications if the parent assessment is finalized.
    2. Upper Bound Check: Ensures 'obtained_marks' does not exceed 'total_marks'.
    3. Enrollment Check: Verifies that the student is actively enrolled in the course offering.
    """

    student_name = serializers.CharField(source="student.full_name", read_only=True)
    roll_number = serializers.CharField(source="student.roll_number", read_only=True)

    class Meta:
        model = StudentAssessment
        fields = [
            "id",
            "assessment",
            "student",
            "student_name",
            "roll_number",
            "obtained_marks",
            "remarks",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        assessment = attrs.get(
            "assessment", getattr(self.instance, "assessment", None)
        )
        student = attrs.get("student", getattr(self.instance, "student", None))
        obtained_marks = attrs.get(
            "obtained_marks", getattr(self.instance, "obtained_marks", None)
        )

        # 1. Prevent modifications on finalized assessments
        if assessment and assessment.marks_submitted:
            raise serializers.ValidationError(
                "This assessment has been finalized. Marks cannot be modified."
            )

        # 2. Check upper bound limit
        if obtained_marks is not None and assessment:
            if assessment.total_marks is None:
                raise serializers.ValidationError({
                    "obtained_marks": "Set the assessment total marks before assigning student scores."
                })
            if obtained_marks > assessment.total_marks:
                raise serializers.ValidationError({
                    "obtained_marks": f"Obtained marks ({obtained_marks}) cannot exceed total marks ({assessment.total_marks})."
                })

        # 3. Verify student enrollment in the course offering
        if student and assessment:
            is_enrolled = student.enrollments.filter(
                course_offering=assessment.course_offering, is_active=True
            ).exists()
            if not is_enrolled:
                raise serializers.ValidationError({
                    "student": f"Student '{student}' is not actively enrolled in this course offering."
                })

        return attrs



class GradebookStudentMarkItemSerializer(serializers.Serializer):
    """
    PURPOSE:
    Helper serializer representing a single student row within the faculty gradebook payload.
    """

    student_id = serializers.IntegerField()
    obtained_marks = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True
    )
    remarks = serializers.CharField(required=False, allow_blank=True, default="")


class FacultyGradebookUpdateSerializer(serializers.Serializer):
    """
    PURPOSE:
    Main bulk serializer for the faculty grading workflow:
    1. Faculty sets 'total_marks' (e.g., 10).
    2. Receives scores for all students in the section within a single request payload.
    3. Option to publish immediately by setting 'marks_submitted=True'.

    VALIDATIONS:
    1. Ensures 'total_marks' is greater than 0.
    2. Verifies that no student score exceeds the specified total marks.
    """

    total_marks = serializers.IntegerField(
        min_value=1,
        help_text="Total marks specified by the faculty (e.g., 10).",
    )
    marks_submitted = serializers.BooleanField(
        default=False,
        help_text="Set to True to publish marks to students.",
    )
    students_marks = GradebookStudentMarkItemSerializer(
        many=True, help_text="List of scores for students in the section."
    )

    def validate(self, attrs):
        total_marks = attrs.get("total_marks")
        students_marks = attrs.get("students_marks", [])

        # Validate that no student score exceeds the total marks
        for item in students_marks:
            obtained = item.get("obtained_marks")
            if obtained is not None and obtained > total_marks:
                raise serializers.ValidationError({
                    "students_marks": f"Marks ({obtained}) for Student ID {item['student_id']} exceed total marks ({total_marks})."
                })

        return attrs



class StudentPortalAssessmentSerializer(serializers.ModelSerializer):
    """
    PURPOSE:
    Read-only serializer for student portal dashboards.
    Displays assessment details along with obtained scores and remarks for published assessments.
    """

    assessment_title = serializers.CharField(
        source="assessment.title", read_only=True
    )
    assessment_type = serializers.CharField(
        source="assessment.assessment_type.name", read_only=True
    )
    total_marks = serializers.IntegerField(
        source="assessment.total_marks", read_only=True
    )
    assessment_date = serializers.DateField(
        source="assessment.assessment_date", read_only=True
    )

    class Meta:
        model = StudentAssessment
        fields = [
            "id",
            "assessment_title",
            "assessment_type",
            "total_marks",
            "obtained_marks",
            "remarks",
            "assessment_date",
        ]
        read_only_fields = fields