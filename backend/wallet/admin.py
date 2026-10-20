from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from wallet.models import WalletActivity, WalletAllocation, WalletYear


@admin.register(WalletYear)
class WalletYearAdmin(SimpleHistoryAdmin):
    list_display = ("year", "notes")


@admin.register(WalletActivity)
class WalletActivityAdmin(SimpleHistoryAdmin):
    list_display = ("code", "title", "kind", "project", "redmine_ref", "is_technical")
    list_filter = ("kind", "is_technical")
    search_fields = ("code", "title", "redmine_ref")


@admin.register(WalletAllocation)
class WalletAllocationAdmin(SimpleHistoryAdmin):
    list_display = (
        "external_ref",
        "wallet_year",
        "source_project",
        "activity",
        "allocated_days",
        "status",
        "reliability",
        "is_technical",
    )
    list_filter = ("wallet_year", "status", "reliability", "is_technical")
    search_fields = ("external_ref", "source_project__code", "activity__code")
    autocomplete_fields = ("source_project", "activity")
