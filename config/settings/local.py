from config.settings.base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("MAIN_POSTGRES_DB", default="intelliversity_main_db"),
        "USER": env("MAIN_POSTGRES_USER", default="intelliversity_user"),
        "PASSWORD": env("MAIN_POSTGRES_PASSWORD", default="intelliversity_main_pass"),
        "HOST": env("MAIN_POSTGRES_HOST", default="db"),
        "PORT": env.int("MAIN_POSTGRES_PORT", default="5432"),
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
