from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from directory.models import Organization, Person


@admin.register(Organization)
class OrganizationAdmin(SimpleHistoryAdmin):
    list_display = ("code", "name", "kind")
    search_fields = ("code", "name")


@admin.register(Person)
class PersonAdmin(SimpleHistoryAdmin):
    list_display = ("full_name", "organization", "email", "is_active", "needs_review")
    list_filter = ("organization", "is_active", "needs_review")
    search_fields = ("full_name", "email")
