"""Run a forecast from the command line (demos, smoke tests, support).

    python manage.py predict_cgpa --tenant fast --student <uuid> [--semester 4] [--json]
    python manage.py predict_cgpa --tenant fast --model-info

Tenant-aware on purpose: tenant-scoped models now raise when no tenant is in
context, so the command resolves one from ``--tenant`` before touching data.
Forecasts written from the CLI are audited like API forecasts; ``--unaudited``
skips the audit row and says so in the output.
"""

import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.predictions import services
from apps.profiles.models import StudentProfile
from apps.tenants.context import clear_current_tenant, set_current_tenant
from apps.tenants.models import University
from apps.tenants.utils.db_utils import ensure_tenant_db_configured


class Command(BaseCommand):
    help = "Forecast a student's final CGPA using the bundled pre-trained models."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            required=True,
            help="University subdomain (for example 'fast'). Required.",
        )
        parser.add_argument("--student", help="StudentProfile UUID")
        parser.add_argument("--semester", type=int, help="Force semester model 1-8")
        parser.add_argument(
            "--model-info",
            action="store_true",
            help="Print the shipped models, their offline metrics, and health",
        )
        parser.add_argument("--json", action="store_true", help="Raw JSON output")
        parser.add_argument(
            "--unaudited",
            action="store_true",
            help="Do not write a PredictionRecord audit row",
        )

    def handle(self, *args, **options):
        self._activate_tenant(options["tenant"])

        try:
            if options["model_info"]:
                self.stdout.write(json.dumps(services.model_info(), indent=2))
                return

            student_id = options["student"]
            if not student_id:
                raise CommandError("--student is required (or use --model-info).")

            student = self._get_student(student_id)

            try:
                result = services.predict_student(student, options["semester"])
            except services.InvalidSemester as exc:
                raise CommandError(str(exc)) from exc
            except services.ArtifactError as exc:
                raise CommandError(f"Model bundle unavailable: {exc}") from exc

            audited = False
            if not options["unaudited"]:
                try:
                    services.record_prediction(student, result)
                    audited = True
                except Exception as exc:  # an audit failure must not hide a forecast
                    self.stderr.write(
                        self.style.WARNING(f"Audit row not written: {exc}")
                    )

            self._render(result, options["json"], audited)
        finally:
            clear_current_tenant()

    # -- helpers ------------------------------------------------------------

    def _activate_tenant(self, subdomain: str):
        try:
            tenant = University.objects.using("default").get(subdomain=subdomain)
        except University.DoesNotExist as exc:
            raise CommandError(
                f"No university with subdomain {subdomain!r} in the main database."
            ) from exc

        ensure_tenant_db_configured(tenant)
        set_current_tenant(tenant)
        self.tenant = tenant

    def _get_student(self, student_id: str) -> StudentProfile:
        try:
            return StudentProfile.objects.select_related(
                "base_profile", "batch", "admission"
            ).get(id=student_id)
        except StudentProfile.DoesNotExist as exc:
            raise CommandError(
                f"No student {student_id} in tenant {self.tenant.subdomain!r}."
            ) from exc
        except (DjangoValidationError, ValueError, TypeError) as exc:
            raise CommandError(f"{student_id!r} is not a valid UUID.") from exc

    def _render(self, result: dict, as_json: bool, audited: bool):
        if as_json:
            self.stdout.write(json.dumps(result, indent=2))
            return

        if not result["meaningful"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Student {result['student_id']}: forecast not meaningful yet "
                    "(no admission marks and no completed semesters)."
                )
            )
            return

        guard = ""
        if result["guardrail_applied"]:
            guard = (
                f" [guardrail {', '.join(result['guardrail_reasons'])}: "
                f"raw {result['raw_prediction']:.2f}]"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"semester {result['semester']}: projected final CGPA "
                f"{result['predicted_cgpa']:.2f}{guard} "
                f"(model {result['model']['name']} {result['model']['version'][:12]}, "
                f"{'audited' if audited else 'unaudited'})"
            )
        )
        for warning in result["warnings"]:
            self.stdout.write(self.style.WARNING(f"  warning: {warning}"))
        self.stdout.write(f"  {result['disclaimer']}")
