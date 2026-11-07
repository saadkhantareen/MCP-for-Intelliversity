from django.urls import path

from apps.predictions.views import CGPAForecastView, CohortForecastView, ModelInfoView

urlpatterns = [
    path("cgpa/", CGPAForecastView.as_view(), name="cgpa-forecast"),
    path("cohort/", CohortForecastView.as_view(), name="cgpa-cohort"),
    path("models/", ModelInfoView.as_view(), name="prediction-models"),
]
