"""
Management command that seeds one Django Group per Role (student, faculty,
admin, ...) on every tenant database, and keeps each group's permissions in
sync with the declarative ROLE_PERMISSIONS matrix below.

Usage:
    python manage.py seed_roles
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role
from apps.academics.models import (
    AcademicPolicy,
    AcademicYear,
    Batch,
    Course,
    CoursePrerequisite,
    Curriculum,
    CurriculumCourse,
    Department,
    FacultyCourse,
    Program,
    Section,
    StudentTermRecord,
    Term,
)
from apps.attendance.models import (
    AttendanceLog,
    AttendancePolicy,
    AttendanceRecord,
    ClassSession,
)
from apps.enrollments.models import CourseOffering, Enrollment, FacultyAssignment
from apps.examinations.models import (
    Assessment,
    AssessmentPolicy,
    AssessmentType,
    GradePolicy,
    GradeScale,
    StudentAssessment,
)
from apps.finance.models import StudentFeeInvoice
from apps.profiles.models import Document, FacultyProfile, StudentProfile
from apps.tenants.models import University
from apps.tenants.utils.db_utils import (
    close_tenant_db_connection,
    ensure_tenant_db_configured,
)

VIEW = ("view",)
MANAGE = ("view", "add", "change", "delete")
ALL_PERMS = "__all__"

# Django's own bookkeeping apps. A tenant "admin" business role that gets
# every model permission generally should NOT get write access to these --
# that's effectively a privilege-escalation path (editing Permission/Group
# rows, forging ContentTypes, hijacking Sessions), not a business need.
# Adjust to taste; leave empty to truly grant everything.
ADMIN_EXCLUDED_APPS = {"contenttypes", "sessions", "admin"}

ACADEMIC_STRUCTURE = [
    Department,
    Program,
    Course,
    CoursePrerequisite,
    Curriculum,
    CurriculumCourse,
    AcademicYear,
    Term,
    Batch,
    Section,
]

POLICY_MODELS = [AcademicPolicy, AttendancePolicy, AssessmentPolicy, GradePolicy]

# Declarative permission matrix keyed by Role. To support a new role, add one
# entry here -- the seeding loop below needs no changes.
#
# NOTE: this grants model-level permissions only. "Own record" access (e.g.
# a student only being able to change *their* StudentProfile) still has to
# be enforced in your views/serializers/querysets -- Django groups don't do
# row-level permissions on their own.
ROLE_PERMISSIONS = {
    Role.STUDENT: {
        VIEW: ACADEMIC_STRUCTURE
        + POLICY_MODELS
        + [
            FacultyProfile,
            CourseOffering,
            StudentTermRecord,
            StudentFeeInvoice,
            AttendanceRecord,
            AttendanceLog,
            AssessmentType,
            Assessment,
            StudentAssessment,
            GradeScale,
        ],
        MANAGE: [StudentProfile, Enrollment, Document],
    },
    Role.FACULTY: {
        VIEW: ACADEMIC_STRUCTURE
        + POLICY_MODELS
        + [
            CourseOffering,
            StudentProfile,
            StudentTermRecord,
            AssessmentType,
            GradeScale,
        ],
        MANAGE: [
            FacultyProfile,
            FacultyCourse,
            FacultyAssignment,
            ClassSession,
            AttendanceRecord,
            AttendanceLog,
            Assessment,
            StudentAssessment,
            Document,
        ],
    },
    Role.ADMIN: ALL_PERMS,
}


class Command(BaseCommand):
    help = "Seed role groups (student, faculty, admin, ...) with permissions on every tenant database."

    def handle(self, *args, **kwargs):
        universities = University.objects.using("default").all()
        if not universities.exists():
            self.stdout.write(
                self.style.WARNING(
                    "No tenants found. Add universities first via admin panel."
                )
            )
            return

        self.group_perm_through = Group.permissions.through

        for university in universities:
            db_key = None
            try:
                db_key = ensure_tenant_db_configured(university)
                self.stdout.write(f"Seeding roles for {university.name}...")
                with transaction.atomic(using=db_key):
                    self._seed_for_tenant(db_key)
                self.stdout.write(
                    self.style.SUCCESS(f"Roles configured for {university.name}.")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed for {university.name}: {e}")
                )
            finally:
                if db_key:
                    close_tenant_db_connection(alias=db_key)

    def _seed_for_tenant(self, db_key):
        through = self.group_perm_through

        # One query for every permission row on this tenant DB, instead of
        # one query per (model, action) pair as the original get_permission()
        # helper did.
        all_perms = list(
            Permission.objects.using(db_key).select_related("content_type")
        )
        perm_lookup = {}
        for perm in all_perms:
            action = perm.codename.split("_", 1)[0]
            perm_lookup[
                (perm.content_type.app_label, perm.content_type.model, action)
            ] = perm

        for role, spec in ROLE_PERMISSIONS.items():
            group, _ = Group.objects.using(db_key).get_or_create(name=role.value)

            if spec == ALL_PERMS:
                perm_ids = {
                    perm.id
                    for perm in all_perms
                    if perm.content_type.app_label not in ADMIN_EXCLUDED_APPS
                }
            else:
                perm_ids = set()
                for actions, models_list in spec.items():
                    for model in models_list:
                        for action in actions:
                            key = (
                                model._meta.app_label,
                                model._meta.model_name,
                                action,
                            )
                            perm = perm_lookup.get(key)
                            if perm is None:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"  Missing {action}_{model._meta.model_name} "
                                        f"permission -- has this tenant been migrated?"
                                    )
                                )
                                continue
                            perm_ids.add(perm.id)

            # Sync rather than only add: anything currently on the group but
            # no longer in ROLE_PERMISSIONS gets revoked, so re-running the
            # command after editing the matrix actually converges instead of
            # only ever growing.
            existing_ids = set(
                through.objects.using(db_key)
                .filter(group_id=group.id)
                .values_list("permission_id", flat=True)
            )
            to_add = perm_ids - existing_ids
            to_remove = existing_ids - perm_ids

            if to_add:
                through.objects.using(db_key).bulk_create(
                    [through(group_id=group.id, permission_id=pid) for pid in to_add],
                    ignore_conflicts=True,
                )
            if to_remove:
                through.objects.using(db_key).filter(
                    group_id=group.id, permission_id__in=to_remove
                ).delete()

            self.stdout.write(
                f"  {role.label}: {len(perm_ids)} permissions "
                f"(+{len(to_add)} added, -{len(to_remove)} removed)"
            )
