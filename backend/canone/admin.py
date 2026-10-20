from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from canone.models import Canone, CanoneSubactivity


class SubactivityInline(admin.TabularInline):
    model = CanoneSubactivity
    extra = 0
    fields = (
        "office",
        "title",
        "redmine_ref",
        "quarter_estimate_days",
        "forecast_remaining_days",
        "needs_review",
    )
    readonly_fields = ("redmine_ref",)


@admin.register(Canone)
class CanoneAdmin(SimpleHistoryAdmin):
    list_display = (
        "semester",
        "project",
        "total_days",
        "target_base_days",
        "target_days_per_week",
        "start_date",
        "end_date",
    )
    list_filter = ("semester",)
    inlines = [SubactivityInline]


@admin.register(CanoneSubactivity)
class CanoneSubactivityAdmin(SimpleHistoryAdmin):
    list_display = ("title", "canone", "office", "redmine_ref", "needs_review")
    list_filter = ("canone", "office", "needs_review")
    search_fields = ("title", "redmine_ref")
