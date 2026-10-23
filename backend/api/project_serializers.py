"""Contratto API esplicito per la modifica dell'anagrafica progetto."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from directory.models import OrganizationKind, Person
from projects.models import Project

PROJECT_EDITABLE_FIELDS = {
    "actual_closure_date",
    "aro_code",
    "billing_status",
    "budget_days",
    "client_owner",
    "contract_type",
    "deliverable",
    "notes",
    "offer_status",
    "planned_end_date",
    "rda_code",
    "reliability",
    "start_date",
    "supplier_owner",
    "timesheet_status",
    "title",
    "verification_points",
}
PROJECT_ANNOTATION_FIELDS = {"notes", "verification_points", "planned_end_date"}
PROJECT_CONTROL_FIELDS = {"expected_version"}


class ProjectUpdateSerializer(serializers.ModelSerializer):
    """Campi semanticamente modificabili; provenienza, ledger e derivati restano esclusi."""

    client_owner = serializers.PrimaryKeyRelatedField(
        queryset=Person.objects.filter(is_active=True), allow_null=True, required=False
    )
    supplier_owner = serializers.PrimaryKeyRelatedField(
        queryset=Person.objects.filter(is_active=True), allow_null=True, required=False
    )

    class Meta:
        model = Project
        fields = sorted(PROJECT_EDITABLE_FIELDS)
        extra_kwargs = {
            "title": {"required": False},
            "budget_days": {"required": False},
        }

    def validate_client_owner(self, value: Person | None) -> Person | None:
        if value is not None and value.organization.kind != OrganizationKind.CLIENT:
            raise serializers.ValidationError("Il referente cliente deve appartenere a un cliente.")
        return value

    def validate_supplier_owner(self, value: Person | None) -> Person | None:
        if value is not None and value.organization.kind != OrganizationKind.SUPPLIER:
            raise serializers.ValidationError(
                "Il referente fornitore deve appartenere a un fornitore."
            )
        return value

    def validate(self, attrs):
        if not self.instance:
            return attrs
        candidate = Project.objects.get(pk=self.instance.pk)
        for field, value in attrs.items():
            setattr(candidate, field, value)
        try:
            candidate.full_clean(exclude=["residual_reference_year"])
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError({"non_field_errors": exc.messages}) from exc
        return attrs
