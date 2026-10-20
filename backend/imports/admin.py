from django.contrib import admin

from imports.models import ImportBatch


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "status", "source_filename", "applied_by", "applied_at")
    list_filter = ("kind", "status")
    readonly_fields = ("report", "error", "applied_at", "rolled_back_at")
