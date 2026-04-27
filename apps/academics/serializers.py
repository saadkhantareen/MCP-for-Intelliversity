from rest_framework import serializers
from apps.academics.models import Course, CoursePrerequisite, Department, Program
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
