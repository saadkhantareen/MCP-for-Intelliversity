from django.db import models
from django.utils.translation import gettext_lazy as _


class DegreeLevel(models.TextChoices):
    BACHELORS = "UG", _("Undergraduate")
    MASTERS = "PG", _("Postgraduate")
    PHD = "PHD", _("Doctorate")
    DIPLOMA = "DIP", _("Diploma")


class CourseType(models.TextChoices):
    CORE = "CORE", _("Core / Compulsory")
    ELECTIVE = "ELEC", _("Elective")
    GENERAL = "GEN", _("General Education")


class TermType(models.TextChoices):
    FALL = "FALL", _("Fall")
    SPRING = "SPRING", _("Spring")
    SUMMER = "SUMMER", _("Summer")
    WINTER = "WINTER", _("Winter")


class StudentTermStatus(models.TextChoices):
    ENROLLED = "ENROLLED", _("Enrolled")
    GRADUATED = "COMPLETED", _("Graduated")
    DROPPED_OUT = "DROPPED_OUT", _("Dropped Out")
    FAILED = "FAILED", _("Failed")


class AcademicStanding(models.TextChoices):
    GOOD = "GOOD", _("Good Standing")
    PROBATION = "PROBATION", _("Academic Probation")
    SUSPENDED = "SUSPENDED", _("Suspended")
    EXPELLED = "EXPELLED", _("Expelled")


class BatchStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("Active")
    INACTIVE = "INACTIVE", _("Inactive")
    GRADUATED = "GRADUATED", _("Graduated")
