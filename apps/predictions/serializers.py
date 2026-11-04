from rest_framework import serializers

from apps.predictions.models import PredictionRecord


class CGPAForecastRequestSerializer(serializers.Serializer):
    student_id = serializers.UUIDField(
        required=False,
        help_text="Only admins/faculty may forecast another student. Students are "
        "always scoped to their own profile.",
    )
    semester = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=8,
        help_text="Force a specific semester model. Defaults to the student's current semester.",
    )


class PredictionRecordSerializer(serializers.ModelSerializer):
    """Read-only audit row.

    ``student`` is null after the student is deleted; ``student_registration_id``
    is retained so the trail remains readable.
    """

    class Meta:
        model = PredictionRecord
        fields = [
            "id",
            "student",
            "student_registration_id",
            "semester",
            "predicted_cgpa",
            "raw_prediction",
            "guardrail_applied",
            "model_name",
            "model_version",
            "created_at",
        ]
        read_only_fields = fields
