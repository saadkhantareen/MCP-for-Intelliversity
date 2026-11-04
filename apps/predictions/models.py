from django.db import models

from apps.core.models import BaseModel


class PredictionRecord(BaseModel):
    """Audit trail of forecasts served.

    Tenant-scoped: the university router sends this model to the tenant
    database, so one university's prediction history is never visible to
    another. The ``features`` snapshot makes each prediction reproducible after
    the fact and is the only honest source of a future real-data validation set
    (the shipped models were trained on synthetic data).

    Retention: a row is written only when the inputs or the model version have
    changed since the previous forecast for that student and semester, so a
    page refresh does not append a duplicate. ``purge_predictions`` removes
    rows older than the configured retention window.

    The student link is ``SET_NULL`` with the registration id retained, so
    deleting a student neither silently destroys the audit history nor blocks
    the deletion.
    """

    student = models.ForeignKey(
        "profiles.StudentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cgpa_predictions",
    )
    student_registration_id = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Retained when the student row is deleted, so the audit trail survives.",
    )
    semester = models.PositiveSmallIntegerField(
        help_text="Current semester used to select the model (1-8)."
    )
    predicted_cgpa = models.FloatField(
        null=True, blank=True, help_text="Guardrailed forecast, if the inputs allowed one."
    )
    raw_prediction = models.FloatField(
        null=True, blank=True, help_text="Model output before the guardrail."
    )
    guardrail_applied = models.BooleanField(default=False)
    model_name = models.CharField(max_length=64, blank=True)
    model_version = models.CharField(max_length=64, blank=True)
    features = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["student", "-created_at"])]
        verbose_name = "Prediction record"
        verbose_name_plural = "Prediction records"

    def __str__(self):
        who = self.student_registration_id or "deleted student"
        return f"{who} — semester {self.semester}: {self.predicted_cgpa}"
