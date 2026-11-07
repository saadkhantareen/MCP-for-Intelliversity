"""Populate ``AdmissionRecord`` rows for students that do not have one yet.

The CGPA models take matric and FSc marks as their admission-side inputs, so a
student enrolled before this feature shipped has no forecast until those marks
exist. Retyping them by hand does not scale, hence two import paths:

    python manage.py seed_admissions --tenant fast --demo
        Deterministic synthetic marks, spread around each student's current
        CGPA. For the demo tenant only. Every row is tagged ``is_demo=True``
        and must be excluded from any validation set.

    python manage.py seed_admissions --tenant fast --csv admissions.csv
        Real marks. Header row, comma separated:
            registration_id,matric_obtained,matric_total,fsc_obtained,fsc_total

Tenant-aware: the command resolves ``--tenant`` before touching data, because
tenant-scoped models now raise when no tenant is in context.

Neither mode trains or alters a model: it only fills an input record.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.predictions.feature_engineering import (
    DEFAULT_FSC_TOTAL,
    DEFAULT_MATRIC_TOTAL,
)
from apps.profiles.models import AdmissionRecord, StudentProfile
from apps.tenants.context import clear_current_tenant, set_current_tenant
from apps.tenants.models import University
from apps.tenants.utils.db_utils import ensure_tenant_db_configured

# Single source of truth: the same constants the serving path falls back to.
MATRIC_TOTAL = DEFAULT_MATRIC_TOTAL
FSC_TOTAL = DEFAULT_FSC_TOTAL


class Command(BaseCommand):
    help = "Create missing AdmissionRecord rows (demo data or CSV import)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            required=True,
            help="University subdomain (for example 'fast'). Required.",
        )
        parser.add_argument(
            "--demo",
            action="store_true",
            help="Generate deterministic synthetic marks (demo tenants only).",
        )
        parser.add_argument(
            "--csv",
            type=Path,
            help="CSV file with registration_id,matric_obtained,matric_total,"
            "fsc_obtained,fsc_total",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Update students that already have an admission record.",
        )
        parser.add_argument(
            "--seed", type=int, default=2026, help="RNG seed for --demo."
        )

    def handle(self, *args, **options):
        self._activate_tenant(options["tenant"])

        try:
            self._run(options)
        finally:
            clear_current_tenant()

    def _run(self, options):
        demo = options["demo"]
        csv_path = options.get("csv")
        overwrite = options["overwrite"]

        if bool(demo) == bool(csv_path):
            raise CommandError("Pass exactly one of --demo or --csv.")

        students = StudentProfile.objects.select_related("base_profile__user")
        if not overwrite:
            students = students.filter(admission__isnull=True)

        if not students.exists():
            self.stdout.write(
                self.style.WARNING(
                    "Every student already has admission marks "
                    "(use --overwrite to replace them)."
                )
            )
            return

        if demo:
            created = self._load_demo(list(students), options["seed"])
        else:
            created = self._load_csv(csv_path, overwrite)

        self.stdout.write(
            self.style.SUCCESS(f"Admission records written: {created}.")
        )
        if demo:
            self.stdout.write(
                self.style.WARNING(
                    "Rows written by --demo are tagged is_demo=True. "
                    "They are demonstration data, not evidence about the models."
                )
            )

    # -- tenant -------------------------------------------------------------

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

    # -- demo ---------------------------------------------------------------

    def _load_demo(self, students, seed: int) -> int:
        rng = random.Random(seed)
        written = 0

        with transaction.atomic():
            for student in students:
                # Aim at the band an advisor would expect for this CGPA: ~52%
                # at a 1.5 CGPA up to ~90% for a 4.0, plus spread so the demo
                # cohort contains both at-risk and comfortable students.
                cgpa = float(student.cgpa or 0) or rng.uniform(2.0, 3.5)
                centre = 52.0 + (min(max(cgpa, 0.0), 4.0) / 4.0) * 38.0
                matric_pct = min(98.0, max(40.0, rng.gauss(centre, 7.0)))
                fsc_pct = min(98.0, max(40.0, rng.gauss(centre + 2.0, 7.0)))

                AdmissionRecord.objects.update_or_create(
                    student=student,
                    defaults={
                        "matric_obtained": round(matric_pct / 100 * MATRIC_TOTAL),
                        "matric_total": MATRIC_TOTAL,
                        "fsc_obtained": round(fsc_pct / 100 * FSC_TOTAL),
                        "fsc_total": FSC_TOTAL,
                        "is_demo": True,
                    },
                )
                written += 1

        return written

    # -- csv ----------------------------------------------------------------

    def _load_csv(self, csv_path: Path, overwrite: bool) -> int:
        if not csv_path.exists():
            raise CommandError(f"No such file: {csv_path}")

        by_registration = {
            s.registration_id: s
            for s in StudentProfile.objects.only("id", "registration_id")
        }

        written, missing, invalid = 0, [], []

        with transaction.atomic(), csv_path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            required = {"registration_id", "matric_obtained", "fsc_obtained"}
            if not required.issubset({(c or "").strip() for c in reader.fieldnames or []}):
                raise CommandError(
                    "CSV must have columns: registration_id, matric_obtained, "
                    "matric_total, fsc_obtained, fsc_total"
                )

            for line_number, row in enumerate(reader, start=2):
                registration_id = (row.get("registration_id") or "").strip()
                student = by_registration.get(registration_id)
                if student is None:
                    missing.append(registration_id)
                    continue

                try:
                    values = self._validated_row(row)
                except ValueError as exc:
                    invalid.append(f"line {line_number} ({registration_id}): {exc}")
                    continue

                if not overwrite and AdmissionRecord.objects.filter(
                    student=student
                ).exists():
                    continue

                AdmissionRecord.objects.update_or_create(
                    student=student, defaults=values
                )
                written += 1

        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(missing)} registration id(s) not found, e.g. {missing[:5]}"
                )
            )
        if invalid:
            for message in invalid[:10]:
                self.stderr.write(self.style.ERROR(f"skipped {message}"))
            self.stderr.write(
                self.style.ERROR(f"{len(invalid)} row(s) skipped as invalid.")
            )
        return written

    @staticmethod
    def _validated_row(row) -> dict:
        """Same rules as the API serializer: totals positive, obtained <= total."""
        def _int(field, default=None):
            raw = row.get(field)
            if raw in (None, ""):
                return default
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                raise ValueError(f"{field} is not a number: {raw!r}")

        matric_total = _int("matric_total", MATRIC_TOTAL)
        fsc_total = _int("fsc_total", FSC_TOTAL)
        matric_obtained = _int("matric_obtained")
        fsc_obtained = _int("fsc_obtained")

        if matric_total is not None and matric_total <= 0:
            raise ValueError("matric_total must be greater than zero")
        if fsc_total is not None and fsc_total <= 0:
            raise ValueError("fsc_total must be greater than zero")
        if matric_obtained is not None and matric_total and matric_obtained > matric_total:
            raise ValueError("matric_obtained cannot exceed matric_total")
        if fsc_obtained is not None and fsc_total and fsc_obtained > fsc_total:
            raise ValueError("fsc_obtained cannot exceed fsc_total")

        return {
            "matric_obtained": matric_obtained,
            "matric_total": matric_total,
            "fsc_obtained": fsc_obtained,
            "fsc_total": fsc_total,
            "is_demo": False,
        }
