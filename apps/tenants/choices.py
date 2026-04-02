from django.db import models
from django.utils.translation import gettext_lazy as _


class PortalType(models.TextChoices):
    STUDENT = "student", _("Student Portal")
    FACULTY = "faculty", _("Faculty Portal")
    ADMIN = "admin", _("Admin Portal")
    PARENT = "parent", _("Parent Portal")


class PageType(models.TextChoices):

    LOGIN = "login", _("Login")
    REGISTER = "register", _("Register")
    FORGOT_PASSWORD = "forgot_password", _("Forgot Password")
    RESET_PASSWORD = "reset_password", _("Reset Password")
    DASHBOARD = "dashboard", _("Dashboard")
    LANDING = "landing", _("Landing / Home")


class DomainSSLStatus(models.TextChoices):

    PENDING = "pending", _("Pending Verification")
    PROVISIONING = "provisioning", _("Provisioning Certificate")
    ACTIVE = "active", _("Active")
    FAILED = "failed", _("Provisioning Failed")
    EXPIRED = "expired", _("Certificate Expired")
