"""Routing radice: API v1, admin Django, healthcheck."""

from django.contrib import admin
from django.urls import include, path

from core.views import health

urlpatterns = [
    path("health", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.urls")),
]
