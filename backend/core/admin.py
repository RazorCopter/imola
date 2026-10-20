from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from core.models import AppSettings


@admin.register(AppSettings)
class AppSettingsAdmin(SimpleHistoryAdmin):
    list_display = (
        "__str__",
        "hours_per_day",
        "reconciliation_tolerance_days",
        "residual_years_after_closure",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        return not AppSettings.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
