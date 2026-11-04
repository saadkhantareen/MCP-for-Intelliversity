from django.apps import AppConfig


class PredictionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.predictions"
    verbose_name = "Predictions"

    def ready(self):
        # No artifact warm-up here on purpose: that would import scikit-learn
        # during every management command (`migrate`, `collectstatic`, checks).
        # The first forecast pays the one-off joblib load; later requests reuse
        # the in-process cache. The exact cost is recorded in VERIFICATION.md
        # rather than asserted here.
        pass
