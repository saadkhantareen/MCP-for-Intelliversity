from rest_framework import serializers
from apps.academics.models import (
    Department,
    Batch,
    Course,
    CoursePrerequisite,
    Curriculum,
    ProgramCurriculum,
    Program,
    Section,
)
from apps.academics.validators import validate_prerequisites
from django.db import transaction


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
        fields = "__all__"

    def validate(self, attrs):
        attrs = validate_prerequisites(self, attrs)
        return attrs

    def _set_prerequisites(self, course, prerequisites):
        CoursePrerequisite.objects.filter(course=course).delete()
        CoursePrerequisite.objects.bulk_create(
            [
                CoursePrerequisite(course=course, prerequisite_course=prereq)
                for prereq in prerequisites
            ]
        )

    @transaction.atomic
    def create(self, validated_data):
        prerequisites = validated_data.pop("prerequisites", [])
        course = super().create(validated_data)
        self._set_prerequisites(course, prerequisites)
        return course

    @transaction.atomic
    def update(self, instance, validated_data):
        prerequisites = validated_data.pop("prerequisites", None)
        course = super().update(instance, validated_data)
        if prerequisites is not None:  # None = not provided, skip. [] = clear all
            self._set_prerequisites(instance, prerequisites)
        return instance


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
            instance.curriculum_courses.all().delete()
            program_courses = [
                ProgramCurriculum(curriculum=instance, **item) for item in courses_data
            ]
            ProgramCurriculum.objects.bulk_create(program_courses)

        return instance


class CurriculumListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Curriculum
        fields = ["id", "name", "program", "total_credit_hours"]


class BatchSerializer(serializers.ModelSerializer):
    program = serializers.SlugRelatedField(
        queryset=Program.objects.all(),
        slug_field="code",
    )
    curriculum = serializers.PrimaryKeyRelatedField(queryset=Curriculum.objects.all())

    class Meta:
        model = Batch
        fields = "__all__"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["curriculum"] = instance.curriculum.name
        return data


class SectionSerializer(serializers.ModelSerializer):
    batch = serializers.SlugRelatedField(
        queryset=Batch.objects.all(),
        slug_field="name",
    )

    class Meta:
        model = Section
        fields = "__all__"
