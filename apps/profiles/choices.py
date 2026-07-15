from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentType(models.TextChoices):
    # Student documents
    MATRIC_RESULT = "matric_result", _("Matric Result")
    FSC_RESULT = "fsc_result", _("FSC Result")
    BACHELOR_DEGREE = "bachelor_degree", _("Bachelor Degree")
    TRANSCRIPT = "transcript", _("Transcript")
    ADMISSION_LETTER = "admission_letter", _("Admission Letter")

    # Faculty documents
    PHD_DEGREE = "phd_degree", _("PhD Degree")
    MASTER_DEGREE = "master_degree", _("Master Degree")
    EXPERIENCE_LETTER = "experience_letter", _("Experience Letter")
    RESEARCH_PAPER = "research_paper", _("Research Paper")
    APPOINTMENT_LETTER = "appointment_letter", _("Appointment Letter")

    # Common documents
    CNIC = "cnic", _("CNIC")
    PASSPORT = "passport", _("Passport")
    OTHER = "other", _("Other")
