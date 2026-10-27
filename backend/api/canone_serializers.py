"""Contratti di scrittura dell'Organico Allargato (naming interno canone)."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from canone.models import Canone, CanoneSubactivity
from projects.models import Project


class CanoneWriteSerializer(serializers.ModelSerializer):
    project_id = serializers.PrimaryKeyRelatedField(
        source="project", queryset=Project.objects.all()
    )

    class Meta:
        model = Canone
        fields = (
            "project_id",
            "semester",
            "total_days",
            "target_base_days",
            "target_days_per_week",
            "weeks_elapsed_at_import",
            "cap_at_total",
            "start_date",
            "end_date",
            "extracted_at",
        )

    def create(self, validated_data):
        validated_data.setdefault("target_base_days", Decimal("2"))
        validated_data.setdefault("target_days_per_week", Decimal("0"))
        return super().create(validated_data)

    def validate(self, attrs):
        instance = self.instance
        semester = attrs.get("semester", getattr(instance, "semester", ""))
        project = attrs.get("project", getattr(instance, "project", None))
        candidate = Canone(
            semester=semester,
            project=project,
            total_days=attrs.get("total_days", getattr(instance, "total_days", Decimal("0"))),
            start_date=attrs.get("start_date", getattr(instance, "start_date", None)),
            end_date=attrs.get("end_date", getattr(instance, "end_date", None)),
        )
        candidate.clean()
        duplicate = Canone.objects.filter(project=project, semester=semester)
        if instance:
            duplicate = duplicate.exclude(pk=instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"semester": "Esiste già un canone per questo progetto e semestre."}
            )
        return attrs


class CanoneSubactivityWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CanoneSubactivity
        fields = (
            "office",
            "title",
            "redmine_ref",
            "quarter_estimate_days",
            "forecast_remaining_days",
            "notes",
            "needs_review",
        )
