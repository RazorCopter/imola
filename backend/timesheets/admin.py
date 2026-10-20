from django.contrib import admin

from timesheets.models import TimesheetEntry


@admin.register(TimesheetEntry)
class TimesheetEntryAdmin(admin.ModelAdmin):
    list_display = (
        "period",
        "days",
        "source",
        "project",
        "canone_subactivity",
        "wallet_allocation",
        "reverses",
    )
    list_filter = ("source", "period")
    search_fields = ("project__code", "note")
    readonly_fields = ()

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
