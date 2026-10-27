"""Contratti di scrittura dell'Organico Allargato."""

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from canone.models import Canone, CanoneSubactivity, Office
from projects.models import Project


class CanoneWriteSerializer(serializers.ModelSerializer):
    project_id = serializers.PrimaryKeyRelatedField(
        source="project", queryset=Project.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Canone
        fields = (
            "project_id", "name", "semester", "periodicity", "total_days",
            "target_base_days", "target_days_per_week", "weeks_elapsed_at_import",
            "cap_at_total", "start_date", "end_date", "extracted_at",
        )
        read_only_fields = ("start_date", "end_date")

    def create(self, validated_data):
        validated_data.setdefault("target_base_days", Decimal("0"))
        validated_data.setdefault("target_days_per_week", Decimal("0"))
        start, end = Canone.semester_bounds(validated_data["semester"])
        validated_data.setdefault("start_date", date.fromisoformat(start))
        validated_data.setdefault("end_date", date.fromisoformat(end))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "semester" in validated_data:
            start, end = Canone.semester_bounds(validated_data["semester"])
            validated_data.setdefault("start_date", date.fromisoformat(start))
            validated_data.setdefault("end_date", date.fromisoformat(end))
        return super().update(instance, validated_data)

    def validate(self, attrs):
        instance = self.instance
        semester = attrs.get("semester", getattr(instance, "semester", ""))
        project = attrs.get("project", getattr(instance, "project", None))
        name = attrs.get("name", getattr(instance, "name", "")).strip()
        if not name and project:
            name = project.title or project.code
            attrs["name"] = name
        if not name:
            raise serializers.ValidationError({"name": "Il nome del canone è obbligatorio."})
        candidate = Canone(
            name=name,
            semester=semester,
            periodicity=attrs.get("periodicity", getattr(instance, "periodicity", "SEMESTRALE")),
            total_days=attrs.get("total_days", getattr(instance, "total_days", Decimal("0"))),
            start_date=attrs.get("start_date", getattr(instance, "start_date", None)),
            end_date=attrs.get("end_date", getattr(instance, "end_date", None)),
        )
        candidate.clean()
        duplicate = Canone.objects.filter(name__iexact=name, semester=semester)
        if instance:
            duplicate = duplicate.exclude(pk=instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"semester": "Esiste già un canone con questo nome per il periodo indicato."}
            )
        if instance:
            reserved = instance.subactivities.aggregate(total=Sum("reserved_days"))["total"] or 0
            if attrs.get("total_days", instance.total_days) < reserved:
                raise serializers.ValidationError(
                    {"total_days": "Il monte non può essere inferiore alle giornate già riservate."}
                )
        return attrs


class CanoneSubactivityWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CanoneSubactivity
        fields = (
            "office", "title", "reserved_days", "start_date", "end_date", "redmine_ref",
            "quarter_estimate_days", "forecast_remaining_days", "notes", "needs_review",
        )

    def validate(self, attrs):
        canone = self.context.get("canone") or getattr(self.instance, "canone", None)
        if canone is None:
            return attrs
        reserved = attrs.get("reserved_days", getattr(self.instance, "reserved_days", None))
        if reserved is None or reserved <= 0:
            raise serializers.ValidationError(
                {"reserved_days": "Indicare un numero di giornate riservate maggiore di zero."}
            )
        office = attrs.get("office", getattr(self.instance, "office", ""))
        if office not in {Office.EA, Office.TA, Office.SA, Office.CROSS}:
            raise serializers.ValidationError(
                {"office": "Selezionare il dominio EA, TA, SA oppure CROSS."}
            )
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if self.instance is None:
            start_date = start_date or canone.start_date
            end_date = end_date or canone.end_date
            attrs["start_date"] = start_date
            attrs["end_date"] = end_date
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({"end_date": "La data fine precede la data inizio."})
        allocated = canone.subactivities.all()
        if self.instance:
            allocated = allocated.exclude(pk=self.instance.pk)
        allocated_total = allocated.aggregate(total=Sum("reserved_days"))["total"] or 0
        if allocated_total + reserved > canone.total_days:
            raise serializers.ValidationError(
                {"reserved_days": "La riserva supera le giornate ancora disponibili sul canone."}
            )
        if self.instance:
            consumed = self.instance.timesheet_entries.aggregate(total=Sum("days"))["total"] or 0
            if reserved < consumed:
                raise serializers.ValidationError(
                    {"reserved_days": "La riserva non può essere inferiore alle giornate già consuntivate."}
                )
        return attrs
