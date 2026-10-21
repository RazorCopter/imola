from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from anomalies.models import Anomaly


@admin.register(Anomaly)
class AnomalyAdmin(SimpleHistoryAdmin):
    list_display = (
        "external_ref",
        "rule_code",
        "severity",
        "scope",
        "status",
        "project",
        "detected_at",
        "superseded_by",
    )
    list_filter = ("severity", "scope", "status", "rule_code")
    search_fields = ("external_ref", "description", "rule_code", "project__code")
    readonly_fields = ("fingerprint", "detected_at", "last_seen_at", "resolved_at")
