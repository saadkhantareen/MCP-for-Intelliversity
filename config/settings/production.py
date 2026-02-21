# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases
import dj_database_url

from config.settings.base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG", default=False)

ALLOWED_HOSTS = ["*"]


DATABASES = {
    "default": dj_database_url.config(
        default=env("MAIN_DATABASE_URL"),
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,
    )
}
