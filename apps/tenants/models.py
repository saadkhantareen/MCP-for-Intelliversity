from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.tenants.choices import DomainSSLStatus, PageType, PortalType


class University(BaseModel):
    """
    Each university gets its own isolated database connection.
    The M2M to Portal now goes through UniversityPortal so we can attach
    per-pairing state (is_active, ordering, etc.) without extra lookups.
    """

    name = models.CharField(max_length=255)
    subdomain = models.SlugField(max_length=100, unique=True)

    db_name = models.CharField(max_length=255)
    db_host = models.CharField(max_length=255)
    db_port = models.CharField(max_length=10, default="5432")

    is_active = models.BooleanField(default=True)

    # M2M via explicit through model — gives us a FK we can reference in child
    # models (PortalBranding, PageAsset, etc.) without a composite natural key.
    portals = models.ManyToManyField(
        "Portal", through="UniversityPortal", related_name="universities"
    )

    class Meta:
        verbose_name = "University"
        verbose_name_plural = "Universities"

    def __str__(self):
        return self.name

    @property
    def db_alias(self) -> str:
        return f"intelliversity_{self.subdomain}"


class Portal(BaseModel):
    """
    Portal records are shared across all tenants; per-tenant configuration
    lives in UniversityPortal and its related models.
    """

    name = models.CharField(choices=PortalType.choices, max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Portal"
        verbose_name_plural = "Portals"

    def __str__(self):
        return self.name


class UniversityPortal(BaseModel):
    """
    Explicit through model for the University ↔ Portal many-to-many.

    All per-(university, portal) configuration: all other have one FK
    instead of two separate FKs to University and Portal.This eliminates
    the risk of mismatched (university, portal) pairs in child models
    and keeps referential integrity tight.
    """

    university = models.ForeignKey(
        University, on_delete=models.CASCADE, related_name="university_portals"
    )
    portal = models.ForeignKey(
        Portal, on_delete=models.CASCADE, related_name="university_portals"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("university", "portal")
        verbose_name = "University Portal"
        verbose_name_plural = "University Portals"

    def __str__(self):
        return f"{self.university.name} — {self.portal.name}"


class PortalBranding(BaseModel):
    """
    White-label branding for a specific university portal.
    One record per UniversityPortal pair.

    image url: Cloudinary delivery URL for direct public access
    public_id: Cloudinary public_id — required for deletion / transformation.

    theme_config shape (stored as JSON, validated at the serializer layer):
        {
            "colors": {
                "primary":    "#1A73E8",
                "secondary":  "#FFA000",
                "accent":     "#00BCD4",
                "background": "#F5F5F5",
                "surface":    "#FFFFFF",
                "text":       "#212121",
                "text_muted": "#757575",
                "sidebar_bg": "#1E2A38"
            },
            "typography": {
                "font_family":   "Inter, sans-serif",
                "heading_family": "Poppins, sans-serif",
                "base_size_px":  16
            },
            "border_radius_px": 8
        }
    """

    university_portal = models.OneToOneField(
        UniversityPortal, on_delete=models.CASCADE, related_name="branding"
    )

    logo_public_id = models.CharField(max_length=500, blank=True, default="")
    logo_dark_public_id = models.CharField(max_length=500, blank=True, default="")
    favicon_public_id = models.CharField(max_length=500, blank=True, default="")

    theme_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full theme definition: colors, typography, border radius, dark mode.",
    )

    class Meta:
        verbose_name = "Portal Branding"
        verbose_name_plural = "Portal Brandings"

    def __str__(self):
        return f"Branding → {self.university_portal}"


class PageAsset(BaseModel):
    """
    Per-page visual assets for a university portal.

    Allows each page (Login, Register, Dashboard, etc.) to have its own
    background image and overlay metadata — independently managed.

    One record per (university_portal, page_type) by UniqueConstraint

    metadata shape (stored as JSON):
        {
            "overlay_color":   "#000000",
            "overlay_opacity": 0.45,
            "tagline":         "Welcome to Oxford University Portal",
            "tagline_color":   "#FFFFFF",
            "show_logo":       true,
            "background_position": "center center",
            "background_size":     "cover"
        }
    """

    university_portal = models.ForeignKey(
        UniversityPortal, on_delete=models.CASCADE, related_name="page_assets"
    )
    page_type = models.CharField(max_length=50, choices=PageType.choices)

    background_image_public_id = models.CharField(
        max_length=500, blank=True, default=""
    )

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Page Asset"
        verbose_name_plural = "Page Assets"
        constraints = [
            models.UniqueConstraint(
                fields=["university_portal", "page_type"],
                name="unique_page_asset_per_portal_page",
            )
        ]

    def __str__(self):
        return f"PageAsset [{self.page_type}] → {self.university_portal}"


# For handling Custom Domain & Default domains
class UniversityDomain(BaseModel):
    """
    Domain routing record for a university portal.

    Auto-generated default:  portal.<subdomain>.<app>.com
    Custom domain example:   myportal.oxford.ac.uk

    SSL status is managed asynchronously (e.g. via Let's Encrypt / Cloudflare)
    and updated by a background task after DNS verification.

    Enforce exactly one is_primary=True per UniversityPortal at the
    application layer (serializer or model.save override) — a DB partial
    unique index handles it cleanly:

        CREATE UNIQUE INDEX one_primary_per_portal
        ON tenants_tenantdomain (university_portal_id)
        WHERE is_primary = true;

    Add this via a RunSQL migration.
    """

    university_portal = models.ForeignKey(
        UniversityPortal, on_delete=models.CASCADE, related_name="domains"
    )

    # IETF Compliance RFC 5321 max domain length is 253 characters.
    domain = models.CharField(max_length=253, unique=True)
    is_primary = models.BooleanField(
        default=False,
        help_text="The canonical domain used for redirects and email links.",
    )
    is_custom = models.BooleanField(default=False)

    ssl_status = models.CharField(
        max_length=20, choices=DomainSSLStatus.choices, default=DomainSSLStatus.PENDING
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "University Domain"
        verbose_name_plural = "University Domains"
        indexes = [
            # Fast lookup by domain string — hit on every inbound HTTP request.
            models.Index(fields=["domain"], name="idx_universitydomain_domain"),
            models.Index(
                fields=["university_portal", "is_primary"],
                name="one_primary_per_portal",
            ),
        ]

    def __str__(self):
        tag = "✦" if self.is_primary else "○"
        return f"{tag} {self.domain}"
