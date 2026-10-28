"""Analisi economica read-only dei consuntivi append-only."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone

from canone.models import Canone
from domain.money import cost_for_days, quantize_days, quantize_money
from timesheets.models import TimesheetEntry

UNASSIGNED_PROJECT = "Senza progetto"
UNASSIGNED_SUPPLIER = "Senza fornitore"


def _bucket() -> dict[str, Any]:
    return {
        "days": Decimal("0"),
        "fixed_cost": Decimal("0"),
        "has_canone": False,
        "project_id": None,
        "supplier_id": None,
    }


def build_cost_analysis(
    *,
    daily_cost: Decimal,
    date_from: date | None = None,
    date_to: date | None = None,
    canone_fixed_cost: Decimal = Decimal("0.00"),
    include_canone: bool = False,
) -> dict[str, Any]:
    """Aggrega ogni movimento una sola volta; gli storni negativi riducono i totali."""
    # Canone activity days are operational tracking, never daily-rate costs.
    entries = TimesheetEntry.objects.filter(canone_subactivity__isnull=True).exclude(
        project__contract_type="CANONE"
    )
    if date_from:
        entries = entries.filter(period__gte=date_from)
    if date_to:
        entries = entries.filter(period__lte=date_to)
    entries = entries.select_related(
        "project__supplier_owner__organization",
        "wallet_allocation__activity__project__supplier_owner__organization",
        "wallet_allocation__activity__supplier_owner__organization",
    ).order_by("period", "id")

    projects: dict[str, dict[str, Any]] = defaultdict(_bucket)
    suppliers: dict[str, dict[str, Any]] = defaultdict(_bucket)
    sources: dict[str, Decimal] = defaultdict(Decimal)
    months: dict[str, Decimal] = defaultdict(Decimal)
    total_days = Decimal("0")
    fixed_total = Decimal("0")
    canone_count = 0
    month_fixed_costs: dict[str, Decimal] = defaultdict(Decimal)

    for entry in entries:
        project = None
        supplier = None
        if entry.project_id:
            source = "PROJECT"
            project = entry.project
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

        if project and project.contract_type == "CANONE":
            continue

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

    if include_canone:
        today = timezone.localdate()
        canoni = Canone.objects.select_related("project__supplier_owner__organization")
        for canone in canoni:
            activation = canone.start_date
            if activation is None:
                activation = date.fromisoformat(Canone.semester_bounds(canone.semester)[0])
            # The full fee is paid at activation, not prorated over activity days.
            if activation > today:
                continue
            if date_from and activation < date_from:
                continue
            if date_to and activation > date_to:
                continue
            fee = quantize_money(canone_fixed_cost)
            fixed_total += fee
            canone_count += 1
            project_row = projects["Canone"]
            project_row["fixed_cost"] += fee
            project_row["has_canone"] = True
            project = canone.project
            owner = project.supplier_owner if project else None
            supplier = owner.organization if owner else None
            supplier_row = suppliers[supplier.name if supplier else UNASSIGNED_SUPPLIER]
            supplier_row["fixed_cost"] += fee
            supplier_row["has_canone"] = True
            supplier_row["supplier_id"] = str(supplier.id) if supplier else None
            month = activation.strftime("%Y-%m")
            month_fixed_costs[month] += fee
            months.setdefault(month, Decimal("0"))

    def rows(values: dict[str, dict[str, Any]], id_key: str) -> list[dict[str, Any]]:
        return [
            {
                id_key: row[id_key],
                "label": label,
                "days": (
                    None
                    if row["has_canone"] and row["days"] == 0
                    else str(quantize_days(row["days"]))
                ),
                "cost": str(
                    quantize_money(cost_for_days(row["days"], daily_cost) + row["fixed_cost"])
                ),
            }
            for label, row in sorted(values.items())
        ]

    total_days = quantize_days(total_days)
    return {
        "policy": (
            "Progetti e wallet a tariffa giornaliera corrente; consuntivi del canone esclusi. "
            "Se incluso, il canone \u00e8 conteggiato per intero alla data di attivazione, "
            "con importo forfettario corrente per ciascun contratto, non storicizzato."
        ),
        "filters": {
            "from": date_from.isoformat() if date_from else None,
            "to": date_to.isoformat() if date_to else None,
            "include_canone": include_canone,
        },
        "kpi": {
            "total_days": str(total_days),
            "total_cost": str(quantize_money(cost_for_days(total_days, daily_cost) + fixed_total)),
            "daily_person_cost": str(daily_cost),
            "canone_fixed_cost": str(canone_fixed_cost),
            "canone_total_cost": str(quantize_money(fixed_total)),
            "canone_count": canone_count,
        },
        "by_project": rows(projects, "project_id"),
        "by_supplier": rows(suppliers, "supplier_id"),
        "by_source": [
            {
                "source": source,
                "days": (
                    None
                    if source == "CANONE"
                    else str(quantize_days(sources.get(source, Decimal("0"))))
                ),
                "cost": (
                    str(quantize_money(fixed_total))
                    if source == "CANONE"
                    else str(cost_for_days(sources.get(source, Decimal("0")), daily_cost))
                ),
            }
            for source in (
                "PROJECT",
                "WALLET",
                *(["CANONE"] if include_canone and canone_count else []),
            )
        ],
        "monthly_trend": [
            {
                "month": month,
                "days": str(quantize_days(days)),
                "cost": str(
                    quantize_money(cost_for_days(days, daily_cost) + month_fixed_costs[month])
                ),
            }
            for month, days in sorted(months.items())
        ],
    }
