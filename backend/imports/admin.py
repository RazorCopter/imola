from django.contrib import admin

from imports.models import (
    ImportBatch,
    ImportIssue,
    WorkbookDatasetSnapshot,
    WorkbookSheetSnapshot,
)


class ImportIssueInline(admin.TabularInline):
    model = ImportIssue
    extra = 0
    readonly_fields = ("level", "entity", "key", "message", "created_at")


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "status", "source_filename", "applied_by", "applied_at")
    list_filter = ("kind", "status")
    readonly_fields = ("report", "error", "applied_at", "rolled_back_at")
    inlines = (ImportIssueInline,)


@admin.register(WorkbookSheetSnapshot)
class WorkbookSheetSnapshotAdmin(admin.ModelAdmin):
    list_display = ("name", "position", "dimensions", "batch")
    list_filter = ("state",)
    search_fields = ("name", "batch__source_filename")


@admin.register(WorkbookDatasetSnapshot)
class WorkbookDatasetSnapshotAdmin(admin.ModelAdmin):
    list_display = ("dataset_id", "sheet_name", "row_count", "column_count", "batch")
    search_fields = ("dataset_id", "sheet_name", "batch__source_filename")
