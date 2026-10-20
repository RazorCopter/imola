from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from projects.models import BillingMilestone, Project


class BillingMilestoneInline(admin.TabularInline):
    model = BillingMilestone
    extra = 0
    fields = ("planned_date", "actual_date", "amount_days", "status", "move_count")
    readonly_fields = ("move_count",)


@admin.register(Project)
class ProjectAdmin(SimpleHistoryAdmin):
    list_display = (
        "code",
        "title",
        "contract_type",
        "budget_days",
        "timesheet_status",
        "billing_status",
        "offer_status",
        "actual_closure_date",
        "reliability",
    )
    list_filter = (
        "contract_type",
        "timesheet_status",
        "billing_status",
        "offer_status",
        "reliability",
    )
    search_fields = ("code", "title", "aro_code", "rda_code")
    readonly_fields = ("residual_reference_year", "version", "created_at", "updated_at")
    inlines = [BillingMilestoneInline]
    autocomplete_fields = ("client_owner", "supplier_owner")


@admin.register(BillingMilestone)
class BillingMilestoneAdmin(SimpleHistoryAdmin):
    list_display = ("project", "planned_date", "actual_date", "status", "move_count")
    list_filter = ("status",)
    search_fields = ("project__code",)
