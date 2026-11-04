import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdmissionRecord",
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
                ("matric_obtained", models.PositiveIntegerField(blank=True, null=True)),
                ("matric_total", models.PositiveIntegerField(default=1100)),
                ("fsc_obtained", models.PositiveIntegerField(blank=True, null=True)),
                ("fsc_total", models.PositiveIntegerField(default=1100)),
                (
                    "entry_test_score",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=6, null=True
                    ),
                ),
                (
                    "student",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="admission",
                        to="profiles.studentprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "admission record",
                "verbose_name_plural": "admission records",
            },
        ),
    ]
