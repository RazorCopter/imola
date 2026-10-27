"""Analisi economica read-only dei consuntivi append-only."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from domain.money import cost_for_days, quantize_days
from timesheets.models import TimesheetEntry

UNASSIGNED_PROJECT = "Senza progetto"
UNASSIGNED_SUPPLIER = "Senza fornitore"


def _bucket() -> dict[str, Any]:
    return {"days": Decimal("0"), "project_id": None, "supplier_id": None}


def build_cost_analysis(
    *, daily_cost: Decimal, date_from: date | None = None, date_to: date | None = None
) -> dict[str, Any]:
    """Aggrega ogni movimento una sola volta; gli storni negativi riducono i totali."""
    entries = TimesheetEntry.objects.all()
    if date_from:
        entries = entries.filter(period__gte=date_from)
    if date_to:
        entries = entries.filter(period__lte=date_to)
    entries = entries.select_related(
        "project__supplier_owner__organization",
        "canone_subactivity__canone__project__supplier_owner__organization",
        "wallet_allocation__activity__project__supplier_owner__organization",
        "wallet_allocation__activity__supplier_owner__organization",
    ).order_by("period", "id")

    projects: dict[str, dict[str, Any]] = defaultdict(_bucket)
    suppliers: dict[str, dict[str, Any]] = defaultdict(_bucket)
    sources: dict[str, Decimal] = defaultdict(Decimal)
    months: dict[str, Decimal] = defaultdict(Decimal)
    total_days = Decimal("0")

    for entry in entries:
        project = None
        supplier = None
        if entry.project_id:
            source = "PROJECT"
            project = entry.project
            if project and project.supplier_owner:
                supplier = project.supplier_owner.organization
        elif entry.canone_subactivity_id:
            source = "CANONE"
            subactivity = entry.canone_subactivity
            canone = subactivity.canone if subactivity else None
            project = canone.project if canone else None
            if project and project.supplier_owner:
                supplier = project.supplier_owner.organization
        else:
            source = "WALLET"
            allocation = entry.wallet_allocation
            activity = allocation.activity if allocation else None
            project = activity.project if activity else None
            owner = (
                activity.supplier_owner or (project.supplier_owner if project else None)
                if activity
                else None
            )
            if owner:
                supplier = owner.organization

        days = entry.days
        total_days += days
        project_label = f"{project.code} — {project.title}" if project else UNASSIGNED_PROJECT
        supplier_label = supplier.name if supplier else UNASSIGNED_SUPPLIER
        project_row = projects[project_label]
        project_row["days"] += days
        project_row["project_id"] = str(project.id) if project else None
        supplier_row = suppliers[supplier_label]
        supplier_row["days"] += days
        supplier_row["supplier_id"] = str(supplier.id) if supplier else None
        sources[source] += days
        months[entry.period.strftime("%Y-%m")] += days

    def rows(values: dict[str, dict[str, Any]], id_key: str) -> list[dict[str, Any]]:
        return [
            {
                id_key: row[id_key],
                "label": label,
                "days": str(quantize_days(row["days"])),
                "cost": str(cost_for_days(row["days"], daily_cost)),
            }
            for label, row in sorted(values.items())
        ]

    total_days = quantize_days(total_days)
    return {
        "policy": "Costo globale corrente, non storicizzato e non differenziato per fornitore.",
        "filters": {
            "from": date_from.isoformat() if date_from else None,
            "to": date_to.isoformat() if date_to else None,
        },
        "kpi": {
            "total_days": str(total_days),
            "total_cost": str(cost_for_days(total_days, daily_cost)),
            "daily_person_cost": str(daily_cost),
        },
        "by_project": rows(projects, "project_id"),
        "by_supplier": rows(suppliers, "supplier_id"),
        "by_source": [
            {
                "source": source,
                "days": str(quantize_days(sources.get(source, Decimal("0")))),
                "cost": str(cost_for_days(sources.get(source, Decimal("0")), daily_cost)),
            }
            for source in ("PROJECT", "CANONE", "WALLET")
        ],
        "monthly_trend": [
            {
                "month": month,
                "days": str(quantize_days(days)),
                "cost": str(cost_for_days(days, daily_cost)),
            }
            for month, days in sorted(months.items())
        ],
    }
