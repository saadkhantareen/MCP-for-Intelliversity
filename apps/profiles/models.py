# apps/profiles/models.py
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.profiles.choices import DocumentType


class BaseProfile(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="base_profile",
    )
    profile_picture_public_id = models.CharField(
        _("profile picture public id"), max_length=255, null=True, blank=True
    )
    # Personal Info
    father_name = models.CharField(
        _("father name"), max_length=150, null=True, blank=True
    )
    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    gender = models.CharField(
        _("gender"),
        max_length=10,
        choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
        null=True,
        blank=True,
    )
    nationality = models.CharField(
        _("nationality"), max_length=100, null=True, blank=True
    )
    cnic = models.CharField(_("CNIC"), max_length=15, null=True, blank=True)
    religion = models.CharField(_("religion"), max_length=50, null=True, blank=True)

    # Contact Info
    phone_number = models.CharField(
        _("phone number"), max_length=20, null=True, blank=True
    )
    emergency_contact = models.CharField(
        _("emergency contact"), max_length=20, null=True, blank=True
    )
    address = models.TextField(_("address"), null=True, blank=True)
    city = models.CharField(_("city"), max_length=100, null=True, blank=True)
    country = models.CharField(_("country"), max_length=100, null=True, blank=True)

    # Bio
    bio = models.TextField(_("bio"), null=True, blank=True)

    class Meta:
        verbose_name = _("base profile")
        verbose_name_plural = _("base profiles")

    def __str__(self):
        return f"{self.user.email} - Base Profile"


class StudentProfile(BaseModel):
    base_profile = models.OneToOneField(
        BaseProfile,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    registration_id = models.CharField(_("registration id"), max_length=50, unique=True)
    section = models.ForeignKey(
        "academics.Section",
        on_delete=models.PROTECT,
        related_name="students",
    )
    cgpa = models.DecimalField(_("CGPA"), max_digits=4, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = _("student profile")
        verbose_name_plural = _("student profiles")

    def __str__(self):
        return f"{self.base_profile.user.email} - Student Profile"


class FacultyProfile(BaseModel):
    base_profile = models.OneToOneField(
        BaseProfile,
        on_delete=models.CASCADE,
        related_name="faculty_profile",
    )
    registration_id = models.CharField(_("registration id"), max_length=50, unique=True)
    designation = models.CharField(
        _("designation"), max_length=150, null=True, blank=True
    )
    qualification = models.CharField(
        _("qualification"), max_length=255, null=True, blank=True
    )
    specialization = models.CharField(
        _("specialization"), max_length=255, null=True, blank=True
    )
    experience_years = models.PositiveIntegerField(
        _("experience years"), null=True, blank=True
    )
    office_number = models.CharField(
        _("office number"), max_length=20, null=True, blank=True
    )
    office_location = models.CharField(
        _("office location"), max_length=150, null=True, blank=True
    )
    department = models.ForeignKey(
        "academics.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="faculty_members",
    )

    class Meta:
        verbose_name = _("faculty profile")
        verbose_name_plural = _("faculty profiles")

    def __str__(self):
        return f"{self.base_profile.user.email} - Faculty Profile"


class AdminProfile(BaseModel):
    base_profile = models.OneToOneField(
        BaseProfile,
        on_delete=models.CASCADE,
        related_name="admin_profile",
    )
    designation = models.CharField(
        _("designation"), max_length=150, null=True, blank=True
    )
    office_number = models.CharField(
        _("office number"), max_length=20, null=True, blank=True
    )
    office_location = models.CharField(
        _("office location"), max_length=150, null=True, blank=True
    )

    class Meta:
        verbose_name = _("admin profile")
        verbose_name_plural = _("admin profiles")

    def __str__(self):
        return f"{self.base_profile.user.email} - Admin Profile"


class Document(BaseModel):
    """
    Private documents linked to a user's BaseProfile.
    Files are stored on Cloudinary as 'authenticated' type.

    Upload flow:
        1. GET  /api/v1/storage/uploads/signature/document/  → get signed Cloudinary params
        2. POST file directly to Cloudinary                   → file uploaded privately
        3. PATCH /api/v1/profiles/documents/                  → save public_id + resource_type here

    View flow:
        - Signed URL (1 hour valid) is auto-generated in every
          document serializer response as the 'url' field.
    """

    base_profile = models.ForeignKey(
        BaseProfile,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(
        _("document type"),
        max_length=50,
        choices=DocumentType.choices,
    )
    title = models.CharField(_("title"), max_length=255)

    resource_type = models.CharField(
        _("resource type"), max_length=20, default="raw"
    )  # raw / image / video

    description = models.TextField(_("description"), null=True, blank=True)
    is_verified = models.BooleanField(_("is verified"), default=False)

    # Cloudinary public_id — saved after upload, used to generate signed URLs
    document_public_id = models.CharField(
        _("document public id"), max_length=255, null=True, blank=True
    )

    class Meta:
        verbose_name = _("document")
        verbose_name_plural = _("documents")

    def __str__(self):
        return f"{self.base_profile.user.email} - {self.document_type}"
