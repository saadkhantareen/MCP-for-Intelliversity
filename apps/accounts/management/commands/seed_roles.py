from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
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

        for university in universities:
            # define db_key outside so that, it cannot cause error at finally.
            db_key = None

            try:
                db_key = ensure_tenant_db_configured(university)

                self.stdout.write(f"Creating roles for {university.name}...")

                # create groups
                admin_group, _ = Group.objects.using(db_key).get_or_create(name="admin")
                faculty_group, _ = Group.objects.using(db_key).get_or_create(
                    name="faculty"
                )
                student_group, _ = Group.objects.using(db_key).get_or_create(
                    name="student"
                )

                # Helper lists for common academic structure models (Read-Only for both Faculty and Students)
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

                # Faculty can view general academic structures and student profiles
                faculty_view_models = academic_structure_models + [StudentProfile]
                for model in faculty_view_models:
                    ct = ContentType.objects.using(db_key).get_for_model(model)
                    view_perm = Permission.objects.using(db_key).get(
                        codename=f"view_{model._meta.model_name}", content_type=ct
                    )
                    faculty_group.permissions.add(view_perm)

                # Faculty can manage (add/change/view) their courses, enrollments, and student grades
                faculty_manage_models = [
                    FacultyCourse,
                    FacultyCourseEnrollment,
                    StudentTermRecord,
                    FacultyProfile,
                ]
                for model in faculty_manage_models:
                    ct = ContentType.objects.using(db_key).get_for_model(model)
                    faculty_group.permissions.add(
                        Permission.objects.using(db_key).get(
                            codename=f"view_{model._meta.model_name}", content_type=ct
                        ),
                        Permission.objects.using(db_key).get(
                            codename=f"add_{model._meta.model_name}", content_type=ct
                        ),
                        Permission.objects.using(db_key).get(
                            codename=f"change_{model._meta.model_name}", content_type=ct
                        ),
                    )

                # Students can view general academic structures and faculty profiles
                student_view_models = academic_structure_models + [
                    FacultyProfile,
                    StudentTermRecord,
                    StudentFeeInvoice,
                ]
                for model in student_view_models:
                    ct = ContentType.objects.using(db_key).get_for_model(model)
                    view_perm = Permission.objects.using(db_key).get(
                        codename=f"view_{model._meta.model_name}", content_type=ct
                    )
                    student_group.permissions.add(view_perm)

                # Students can manage (add/change/view) their own enrollments and profiles
                student_manage_models = [StudentCourseEnrollment, StudentProfile]
                for model in student_manage_models:
                    ct = ContentType.objects.using(db_key).get_for_model(model)
                    student_group.permissions.add(
                        Permission.objects.using(db_key).get(
                            codename=f"view_{model._meta.model_name}", content_type=ct
                        ),
                        Permission.objects.using(db_key).get(
                            codename=f"add_{model._meta.model_name}", content_type=ct
                        ),
                        Permission.objects.using(db_key).get(
                            codename=f"change_{model._meta.model_name}", content_type=ct
                        ),
                    )

                # Give Admins full permissions over everything
                all_perms = Permission.objects.using(db_key).all()
                admin_group.permissions.set(all_perms)

                self.stdout.write(
                    self.style.SUCCESS(
                        "Successfully configured Groups and Permissions for all models!"
                    )
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Roles Created and Permissions Assigned in {university.name}."
                    )
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed for {university.name}: {e}")
                )

            finally:
                if db_key:
                    close_tenant_db_connection(alias=db_key)
