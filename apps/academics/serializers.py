import math
import string

from django.db import transaction
from rest_framework import serializers

from apps.academics.models import (
    AcademicYear,
    Batch,
    Course,
    Curriculum,
    Department,
    FacultyCourse,
    Program,
    CurriculumCourse,
    Section,
    Term,
)
from apps.academics.utils.utils import set_prerequisites
from apps.academics.validators import (
    validate_curriculum_courses,
    validate_prerequisites,
    validate_start_lte_end,
    validate_already_active,
    validate_no_previous_active_year,
    validate_no_previous_active_term,
    validate_program_curriculum_same,
    validate_max_students_available_capacity,
    validate_max_students_per_section,
)
from apps.profiles.models import FacultyProfile, StudentProfile


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = "__all__"


class ProgramSerializer(serializers.ModelSerializer):
    department = serializers.SlugRelatedField(
        queryset=Department.objects.all(), slug_field="code"
    )

    class Meta:
        model = Program
        fields = "__all__"


class CourseSerializer(serializers.ModelSerializer):
    department = serializers.SlugRelatedField(
        queryset=Department.objects.all(),
        slug_field="code",
    )
    prerequisites = serializers.SlugRelatedField(
        many=True,
        queryset=Course.objects.all(),
        slug_field="code",
        required=False,
    )

    class Meta:
        model = Course
        fields = [
            "id",
            "code",
            "name",
            "description",
            "credit_hours",
            "department",
            "prerequisites",
        ]

    def validate(self, attrs):
        attrs = validate_prerequisites(self, attrs)
        return attrs

    def _set_prerequisites(self, course, prerequisites):
        set_prerequisites(self, course, prerequisites)

    @transaction.atomic
    def create(self, validated_data):
        prerequisites = validated_data.pop("prerequisites", [])
        course = super().create(validated_data)
        self._set_prerequisites(course, prerequisites)
        return course

    @transaction.atomic
    def update(self, instance, validated_data):
        prerequisites = validated_data.pop("prerequisites", None)
        super().update(instance, validated_data)

        if prerequisites is not None:  # None = not provided, skip. [] = clear all
            self._set_prerequisites(instance, prerequisites)
        return instance


class FacultyCourseSerializer(serializers.ModelSerializer):
    faculty = serializers.SlugRelatedField(
        queryset=FacultyProfile.objects.all(),
        slug_field="registration_id",
    )
    course = serializers.SlugRelatedField(
        queryset=Course.objects.all(),
        slug_field="code",
    )

    class Meta:
        model = FacultyCourse
        fields = ["id", "faculty", "course"]


class CurriculumCourseSerializer(serializers.ModelSerializer):
    course = serializers.SlugRelatedField(
        slug_field="code", queryset=Course.objects.all()
    )

    class Meta:
        model = CurriculumCourse
        fields = ["course", "recommended_semester", "course_type"]


class CurriculumDetailSerializer(serializers.ModelSerializer):
    courses = CurriculumCourseSerializer(many=True)
    program = serializers.SlugRelatedField(
        queryset=Program.objects.all(),
        slug_field="code",
    )

    class Meta:
        model = Curriculum
        fields = [
            "id",
            "name",
            "program",
            "total_credit_hours",
            "description",
            "courses",
        ]

    def validate(self, attrs):
        attrs = validate_curriculum_courses(attrs)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        courses_data = validated_data.pop("courses")
        curriculum = Curriculum.objects.create(**validated_data)

        # Create the links between the new curriculum and existing courses
        program_courses = [
            CurriculumCourse(curriculum=curriculum, **item) for item in courses_data
        ]
        CurriculumCourse.objects.bulk_create(program_courses)

        return curriculum

    @transaction.atomic
    def update(self, instance, validated_data):
        courses_data = validated_data.pop("courses", None)

        # Update main Curriculum fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(update_fields=validated_data.keys())

        if courses_data is not None:
            # Refresh courses: Delete existing and bulk create new ones
            instance.courses.all().delete()
            program_courses = [
                CurriculumCourse(curriculum=instance, **item) for item in courses_data
            ]
            CurriculumCourse.objects.bulk_create(program_courses)

        return instance


class CurriculumListSerializer(serializers.ModelSerializer):
    program_name = serializers.CharField(source="program.name", read_only=True)

    class Meta:
        model = Curriculum
        fields = ["id", "name", "program", "program_name", "total_credit_hours"]


class AcademicYearSerializer(serializers.ModelSerializer):

    class Meta:
        model = AcademicYear
        fields = ["id", "name", "start_date", "end_date", "is_active"]
        read_only_fields = ["is_active"]

    def validate(self, attrs):
        validate_start_lte_end(attrs)
        return attrs


class AcademicYearActivateSerializer(serializers.Serializer):

    def validate(self, attrs):

        validate_already_active(self, attrs)
        validate_no_previous_active_year(self, attrs)
        return attrs

    def save(self, instance):
        instance.is_active = True
        instance.save()
        return instance


class TermSerializer(serializers.ModelSerializer):
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all()
    )

    def validate(self, attrs):
        validate_start_lte_end(attrs)
        return attrs

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Swap the ID out for the name
        if instance.academic_year:
            representation["academic_year"] = instance.academic_year.name
        return representation

    class Meta:
        model = Term
        fields = "__all__"
        read_only_fields = ["is_active"]


class TermActivateSerializer(serializers.Serializer):
    def validate(self, attrs):
        validate_already_active(self, attrs)
        validate_no_previous_active_term(self, attrs)
        return attrs

    def save(self, instance):
        instance.is_active = True
        instance.save()
        return instance


class BatchSerializer(serializers.ModelSerializer):
    program = serializers.SlugRelatedField(
        queryset=Program.objects.all(),
        slug_field="code",
    )
    curriculum = serializers.PrimaryKeyRelatedField(queryset=Curriculum.objects.all())
    admission_term = serializers.PrimaryKeyRelatedField(queryset=Term.objects.all())

    class Meta:
        model = Batch
        fields = [
            "id",
            "name",
            "program",
            "curriculum",
            "admission_term",
            "status",
            "max_students",
            "expected_current_semester",
            "max_students_per_section",
        ]
        read_only_fields = ["status", "expected_current_semester"]

    def validate(self, attrs):
        validate_program_curriculum_same(attrs, self.instance)
        validate_max_students_available_capacity(attrs, self.instance)
        validate_max_students_per_section(attrs, self.instance)

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["curriculum"] = instance.curriculum.name
        data["admission_term"] = instance.admission_term.name
        return data


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["id", "name", "total_seats"]


class BatchAutoSectionSerializer(serializers.Serializer):

    def validate(self, attrs):
        batch = self.context["batch"]  
        if batch.sections.exists():
            raise serializers.ValidationError(
                {"batch": "Sections have already been generated for this batch."}
            )

        return attrs

    def create(self, validated_data):
        batch = self.context['batch']

        with transaction.atomic():
            students = list(
                StudentProfile.objects.filter(batch=batch)
                .select_related("base_profile__user")
                .order_by(
                    "base_profile__user__first_name", "base_profile__user__last_name"
                )
            )

            total_students = len(students)
            if total_students == 0:
                raise serializers.ValidationError(
                    "No students found registered for this batch."
                )

            # Calculate required number of sections based on batch capacity
            max_per_section = batch.max_students_per_section
            num_sections = math.ceil(total_students / max_per_section)

            section_names = string.ascii_uppercase
            if num_sections > len(section_names):
                raise serializers.ValidationError(
                    "Calculated sections exceed the A-Z naming limit (26 sections)."
                )

            # Create the Sections
            created_sections = []
            for i in range(num_sections):
                section = Section.objects.create(
                    name=f"Section {section_names[i]}",
                    batch=batch,
                    total_seats=max_per_section,
                )
                created_sections.append(section)

            # Calculate how to distribute students evenly
            base_chunk_size = total_students // num_sections
            remainder = total_students % num_sections

            start_idx = 0
            students_to_update = []

            for i in range(num_sections):
                # Distribute the remainder by adding 1 extra student to the first few sections
                chunk_size = base_chunk_size + (1 if i < remainder else 0)
                end_idx = start_idx + chunk_size

                section_students = students[start_idx:end_idx]
                for student in section_students:
                    student.section = created_sections[i]
                    students_to_update.append(student)

                start_idx = end_idx

            # Save all student updates efficiently in a single query
            StudentProfile.objects.bulk_update(students_to_update, ["section"])

        # Return data that will be passed to to_representation
        return {
            "total_students": total_students,
            "sections_created": [s.name for s in created_sections],
            "students_per_section": (
                f"{base_chunk_size} to {base_chunk_size + 1}"
                if remainder
                else str(base_chunk_size)
            ),
        }

    def to_representation(self, instance):
        return {
            "message": "Sections created and students distributed successfully.",
            "data": {
                "total_students": instance["total_students"],
                "sections_created": instance["sections_created"],
                "students_per_section": instance["students_per_section"],
            },
        }
