from django.contrib.auth.models import Group, Permission, User
from django.core.management.base import BaseCommand

from apps.academics.models import (
    AcademicYear,
    Batch,
    Course,
    CoursePrerequisite,
    Curriculum,
    Department,
    FacultyCourse,
    Program,
    ProgramCurriculum,
    Section,
    StudentTermRecord,
    Term,
)
from apps.enrollments.models import FacultyCourseEnrollment, StudentCourseEnrollment
from apps.finance.models import StudentFeeInvoice
from apps.profiles.models import (
    AdminProfile,
    BaseProfile,
    Document,
    FacultyProfile,
    StudentProfile,
)
from apps.tenants.models import University
from apps.tenants.utils.db_utils import (
    close_tenant_db_connection,
    ensure_tenant_db_configured,
)


class Command(BaseCommand):
    """
    Custom management command to seed three roles on all tenant databases.

    python manage.py seed_roles
    """

    help = "seed three roles on all tenant databases with permissions"

    def handle(self, *args, **kwargs):
        universities = University.objects.using("default").all()

        if not universities.exists():
            self.stdout.write(
                self.style.WARNING(
                    "No tenants found. Add universities first via admin panel."
                )
            )
            return

        # 1. Grab the ManyToMany 'through' model directly to force routing
        GroupPermission = Group.permissions.through

        for university in universities:
            db_key = None

            try:
                db_key = ensure_tenant_db_configured(university)
                self.stdout.write(f"Creating roles for {university.name}...")

                # Create groups
                admin_group, _ = Group.objects.using(db_key).get_or_create(name="admin")
                faculty_group, _ = Group.objects.using(db_key).get_or_create(
                    name="faculty"
                )
                student_group, _ = Group.objects.using(db_key).get_or_create(
                    name="student"
                )

                # Helper lists for common academic structure models
                academic_structure_models = [
                    Department,
                    Program,
                    Course,
                    CoursePrerequisite,
                    Curriculum,
                    ProgramCurriculum,
                    AcademicYear,
                    Term,
                    Batch,
                    Section,
                    Document,
                ]

                # 2. Helper to fetch permissions cleanly (avoids ContentType cache contamination across DBs)
                def get_permission(model_class, action):
                    return Permission.objects.using(db_key).get(
                        content_type__app_label=model_class._meta.app_label,
                        content_type__model=model_class._meta.model_name,
                        codename=f"{action}_{model_class._meta.model_name}",
                    )

                # 3. Helper to explicitly assign permissions strictly to the target DB
                def assign_perms(group, models_list, actions):
                    perms_to_add = []
                    for model in models_list:
                        for action in actions:
                            perm = get_permission(model, action)
                            # Create instances for the M2M through-model
                            perms_to_add.append(
                                GroupPermission(
                                    group_id=group.id, permission_id=perm.id
                                )
                            )

                    # bulk_create with ignore_conflicts=True avoids errors if script is run multiple times
                    if perms_to_add:
                        GroupPermission.objects.using(db_key).bulk_create(
                            perms_to_add, ignore_conflicts=True
                        )

                # --- Assign Faculty Permissions ---
                faculty_view_models = academic_structure_models + [StudentProfile]
                assign_perms(faculty_group, faculty_view_models, ["view"])

                faculty_manage_models = [
                    FacultyCourse,
                    FacultyCourseEnrollment,
                    StudentTermRecord,
                    FacultyProfile,
                    Document,
                ]
                assign_perms(
                    faculty_group,
                    faculty_manage_models,
                    ["view", "add", "change", "delete"],
                )

                # --- Assign Student Permissions ---
                student_view_models = academic_structure_models + [
                    FacultyProfile,
                    StudentTermRecord,
                    StudentFeeInvoice,
                    Document,
                ]
                assign_perms(student_group, student_view_models, ["view"])

                student_manage_models = [StudentCourseEnrollment, StudentProfile]
                assign_perms(
                    student_group,
                    student_manage_models,
                    ["view", "add", "change", "delete"],
                )

                # --- Assign Admin Permissions ---
                all_perms = Permission.objects.using(db_key).all()
                admin_perms_to_add = [
                    GroupPermission(group_id=admin_group.id, permission_id=perm.id)
                    for perm in all_perms
                ]
                if admin_perms_to_add:
                    GroupPermission.objects.using(db_key).bulk_create(
                        admin_perms_to_add, ignore_conflicts=True
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully Configured Roles and Assigned Permissions in {university.name}."
                    )
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed for {university.name}: {e}")
                )

            finally:
                if db_key:
                    close_tenant_db_connection(alias=db_key)
