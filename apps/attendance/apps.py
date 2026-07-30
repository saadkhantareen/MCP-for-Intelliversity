from django.apps import AppConfig
class AttendanceConfig(AppConfig):
 default_auto_field = "django.db.models.BigAutoField"
 name = "apps.attendance" # full dotted path, not just "atten
 verbose_name = "Attendance" # human-readable name for the app