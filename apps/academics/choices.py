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


class BatchType(models.TextChoices):
    FALL = "FALL", _("Fall")
    SPRING = "SPRING", _("Spring")
    SUMMER = "SUMMER", _("Summer")
    WINTER = "WINTER", _("Winter")
