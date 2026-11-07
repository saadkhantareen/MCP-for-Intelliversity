"""
Single source of truth for "auto-generate sections for a batch".
Used by:
  - BatchAutoSectionSerializer (API)
  - the `seed_sections` management command

It raises plain domain exceptions (no DRF dependency) so callers decide how to report them: the serializer turns them into ValidationError, the seed command turns them into log lines.
"""

import math
import string

from django.db import router, transaction

from apps.academics.models import Section
from apps.profiles.models import StudentProfile


class SectionGenerationError(Exception):
    """Base class for auto-section generation failures."""


class SectionsAlreadyGeneratedError(SectionGenerationError):
    pass


class NoStudentsError(SectionGenerationError):
    pass


class TooManySectionsError(SectionGenerationError):
    pass


def generate_sections_for_batch(batch, *, using=None):
    """
    Create sections A, B, C... for `batch` and spread its students evenly.

    `using` is the database alias. If omitted it defaults to the alias the batch was loaded from, then to whatever the router picks for writes (the current tenant during a request).
    """
    using = using or router.db_for_write(Section)

    # NOTE: atomic(using=...) matters. A bare transaction.atomic() wraps the `default` database, not the tenant database the rows are written to.
    with transaction.atomic(using=using):
        if Section.objects.using(using).filter(batch=batch).exists():
            raise SectionsAlreadyGeneratedError(
                "Sections have already been generated for this batch."
            )

        students = list(
            StudentProfile.objects.using(using)
            .filter(batch=batch)
            .select_related("base_profile__user")
            .order_by(
                "base_profile__user__first_name",
                "base_profile__user__last_name",
                "registration_id",  # tie-breaker: identical names stay deterministic
            )
        )

        total_students = len(students)
        if total_students == 0:
            raise NoStudentsError("No students found registered for this batch.")

        num_sections = math.ceil(total_students / batch.per_section_capacity)

        section_names = string.ascii_uppercase
        if num_sections > len(section_names):
            raise TooManySectionsError(
                "Calculated sections exceed the A-Z naming limit (26 sections)."
            )

        created_sections = Section.objects.using(using).bulk_create(
            [Section(name=section_names[i], batch=batch) for i in range(num_sections)]
        )

        # Even distribution: the first `remainder` sections get one extra student.
        base_chunk_size = total_students // num_sections
        remainder = total_students % num_sections

        start_idx = 0
        students_to_update = []
        for i in range(num_sections):
            chunk_size = base_chunk_size + (1 if i < remainder else 0)
            end_idx = start_idx + chunk_size

            for student in students[start_idx:end_idx]:
                student.section = created_sections[i]
                students_to_update.append(student)

            start_idx = end_idx

        StudentProfile.objects.using(using).bulk_update(students_to_update, ["section"])

    return {
        "total_students": total_students,
        "sections_created": [s.name for s in created_sections],
        "students_per_section": (
            f"{base_chunk_size} to {base_chunk_size + 1}"
            if remainder
            else str(base_chunk_size)
        ),
    }