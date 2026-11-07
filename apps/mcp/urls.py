from django.urls import path

from .views import ChatView, HealthView

urlpatterns = [
    path("chat/", ChatView.as_view(), name="mcp-chat"),
    path("health/", HealthView.as_view(), name="mcp-health"),
]
