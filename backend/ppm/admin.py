from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from ppm.models import ImportProfile, PpmSnapshot, PpmSnapshotRow


class SnapshotRowInline(admin.TabularInline):
    model = PpmSnapshotRow
    extra = 0
    fields = (
        "project_code",
        "project",
        "ppm_status",
        "planned_days",
        "residual_days",
        "total_days",
        "unmatched_reason",
    )
    readonly_fields = fields


@admin.register(PpmSnapshot)
class PpmSnapshotAdmin(admin.ModelAdmin):
    list_display = ("extracted_at", "kind", "source_filename", "row_count", "balanced")
    list_filter = ("kind", "balanced")
    inlines = [SnapshotRowInline]


@admin.register(ImportProfile)
class ImportProfileAdmin(SimpleHistoryAdmin):
    list_display = ("name", "kind", "is_default")
    list_filter = ("kind", "is_default")
