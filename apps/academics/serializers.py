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
    ProgramCurriculum,
    Section,
    Term,
)
from apps.academics.utils.utils import set_prerequisites
from apps.academics.validators import (
    validate_curriculum_courses,
    validate_prerequisites,
    validate_start_lte_end,
    validate_term_dates_within_academic_year,
    validate_only_one_active_term,
    validate_sections_seats,
)
from apps.profiles.models import FacultyProfile


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


class ProgramCurriculumSerializer(serializers.ModelSerializer):
    course = serializers.SlugRelatedField(
        slug_field="code", queryset=Course.objects.all()
    )

    class Meta:
        model = ProgramCurriculum
        fields = ["course", "recommended_semester", "course_type"]


class CurriculumDetailSerializer(serializers.ModelSerializer):
    courses = ProgramCurriculumSerializer(many=True)
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
            ProgramCurriculum(curriculum=curriculum, **item) for item in courses_data
        ]
        ProgramCurriculum.objects.bulk_create(program_courses)

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
                ProgramCurriculum(curriculum=instance, **item) for item in courses_data
            ]
            ProgramCurriculum.objects.bulk_create(program_courses)

        return instance


class CurriculumListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Curriculum
        fields = ["id", "name", "program", "total_credit_hours"]


class TermSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        validate_start_lte_end(attrs)
        return attrs

    class Meta:
        model = Term
        fields = [
            "id",
            "name",
            "start_date",
            "end_date",
            "course_registration_start_date",
            "course_registration_end_date",
            "course_drop_deadline",
            "fee_deadline",
            "term_type",
            "is_active",
        ]


class AcademicYearSerializer(serializers.ModelSerializer):
    terms = TermSerializer(many=True)

    class Meta:
        model = AcademicYear
        fields = ["id", "name", "start_date", "end_date", "is_active", "terms"]

    def validate(self, attrs):
        validate_start_lte_end(attrs)
        validate_term_dates_within_academic_year(attrs)
        validate_only_one_active_term(attrs, self.instance)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        terms_data = validated_data.pop("terms", [])
        academic_year = AcademicYear.objects.create(**validated_data)

        Term.objects.bulk_create(
            [Term(academic_year=academic_year, **item) for item in terms_data]
        )
        return academic_year

    @transaction.atomic
    def update(self, instance, validated_data):
        terms_data = validated_data.pop("terms", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(update_fields=validated_data.keys())

        if terms_data is not None:
            # Replace all terms for this academic year
            instance.term_set.all().delete()
            Term.objects.bulk_create(
                [Term(academic_year=instance, **item) for item in terms_data]
            )
        return instance


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["id", "name", "total_seats"]


class BatchSerializer(serializers.ModelSerializer):
    program = serializers.SlugRelatedField(
        queryset=Program.objects.all(),
        slug_field="code",
    )
    curriculum = serializers.PrimaryKeyRelatedField(queryset=Curriculum.objects.all())
    sections = SectionSerializer(many=True)
    start_academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(), allow_null=True
    )

    class Meta:
        model = Batch
        fields = [
            "id",
            "name",
            "program",
            "curriculum",
            "start_academic_year",
            "start_date",
            "end_date",
            "is_active",
            "max_students",
            "sections",
        ]

    def validate(self, attrs):
        validate_start_lte_end(attrs)
        validate_sections_seats(attrs, self.instance)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        sections_data = validated_data.pop("sections")
        batch = Batch.objects.create(**validated_data)

        # Create all provided sections
        section_instances = [Section(batch=batch, **data) for data in sections_data]
        Section.objects.bulk_create(section_instances)
        return batch

    @transaction.atomic
    def update(self, instance, validated_data):
        sections_data = validated_data.pop("sections", None)

        # Update Batch main fields (Supports PATCH)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(update_fields=validated_data.keys())

        # update sections
        if sections_data is not None:
            instance.sections.all().delete()
            section_instances = [
                Section(batch=instance, **data) for data in sections_data
            ]
            Section.objects.bulk_create(section_instances)

        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["curriculum"] = instance.curriculum.name
        return data
