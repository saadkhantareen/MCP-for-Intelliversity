import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("profiles", "0002_admissionrecord"),
    ]

    operations = [
        migrations.CreateModel(
            name="PredictionRecord",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "semester",
                    models.PositiveSmallIntegerField(
                        help_text="Current semester used to select the model (1-8)."
                    ),
                ),
                ("predicted_cgpa", models.FloatField()),
                (
                    "raw_prediction",
                    models.FloatField(
                        blank=True,
                        help_text="Model output before guardrails.",
                        null=True,
                    ),
                ),
                ("guardrail_applied", models.BooleanField(default=False)),
                ("model_name", models.CharField(blank=True, max_length=64)),
                ("model_version", models.CharField(blank=True, max_length=64)),
                ("features", models.JSONField(default=dict)),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cgpa_predictions",
                        to="profiles.studentprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "Prediction record",
                "verbose_name_plural": "Prediction records",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["student", "-created_at"],
                        name="predictions_student_c528b9_idx",
                    )
                ],
            },
        ),
    ]
