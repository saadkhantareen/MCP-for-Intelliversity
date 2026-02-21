from config.settings.base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("Saas_DB", "telehealth_db"),
        "USER": env("POSTGRES_USER", "telehealth_user"),
        "PASSWORD": env("POSTGRES_PASSWORD", "telehealth_pass"),
        "HOST": env("POSTGRES_HOST", "db"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }
}

# CORS - Allow all origins in development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Security settings - disabled in development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_BROWSER_XSS_FILTER = False
SECURE_CONTENT_TYPE_NOSNIFF = False
X_FRAME_OPTIONS = "SAMEORIGIN"

# Static files - disable compression in development
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"


# Email backend - console output for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
