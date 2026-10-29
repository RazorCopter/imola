"""Aggregazioni read-only per la dashboard."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum

from domain.wallet_balance import wallet_year_balance
from projects.models import BillingMilestone, MilestoneStatus, Project, TimesheetStatus
from wallet.models import WalletActivity, WalletAllocation

UPCOMING_BILLINGS_LIMIT = 50
OPEN_MILESTONE_STATUSES = (
    MilestoneStatus.PIANIFICATA,
    MilestoneStatus.SPOSTATA,
    MilestoneStatus.DA_VERIFICARE,
)


def _month_end(value: date) -> date:
    return value.replace(day=monthrange(value.year, value.month)[1])


def _decimal_string(value: Decimal | None) -> str | None:
    return format(value, ".4f") if value is not None else None


def dashboard_summary(
    *, today: date, settings_obj, billing_limit: int = UPCOMING_BILLINGS_LIMIT
) -> dict:
    """Restituisce il contratto dashboard usando aggregazioni e query senza N+1."""
    project_counts = dict.fromkeys(TimesheetStatus.values, 0)
    for row in Project.objects.values("timesheet_status").annotate(count=Count("id")):
        project_counts[row["timesheet_status"]] = row["count"]

    distribution = {}
    for field, queryset in (
        ("progetti", Project.objects.all()),
        ("attivita_wallet", WalletActivity.objects.filter(is_technical=False)),
    ):
        for row in queryset.values("client_owner_id", "client_owner__full_name").annotate(
            count=Count("id")
        ):
            owner_id = row["client_owner_id"]
            entry = distribution.setdefault(
                owner_id,
                {
                    "referente_id": str(owner_id) if owner_id is not None else None,
                    "referente": row["client_owner__full_name"] or "Senza referente",
                    "progetti": 0,
                    "attivita_wallet": 0,
                    "giornate_progetti": Decimal("0"),
                    "giornate_wallet": Decimal("0"),
                },
            )
            entry[field] = row["count"]

    for row in Project.objects.values("client_owner_id").annotate(total=Sum("budget_days")):
        distribution[row["client_owner_id"]]["giornate_progetti"] = row["total"] or Decimal("0")
    for row in (
        WalletAllocation.objects.filter(is_technical=False, activity__is_technical=False)
        .values("activity__client_owner_id")
        .annotate(total=Sum("allocated_days"))
    ):
        distribution[row["activity__client_owner_id"]]["giornate_wallet"] = row["total"] or Decimal(
            "0"
        )
    for entry in distribution.values():
        project_days = entry["giornate_progetti"]
        wallet_days = entry["giornate_wallet"]
        entry["monte_giornate"] = _decimal_string(project_days + wallet_days)
        entry["giornate_progetti"] = _decimal_string(project_days)
        entry["giornate_wallet"] = _decimal_string(wallet_days)

    by_referent = sorted(
        distribution.values(),
        key=lambda row: (
            row["referente_id"] is None,
            -(row["progetti"] + row["attivita_wallet"]),
            row["referente"].casefold(),
            row["referente_id"] or "",
        ),
    )

    wallet = wallet_year_balance(
        today.year,
        today=today,
        years_valid_after_closure=settings_obj.residual_years_after_closure,
        expiring_window_days=settings_obj.residual_expiring_window_days,
    )

    current_month_start = today.replace(day=1)
    current_month_end = _month_end(today)
    milestones = (
        BillingMilestone.objects.filter(
            status__in=OPEN_MILESTONE_STATUSES,
            planned_date__lte=current_month_end,
        )
        .select_related("project")
        .order_by("project_id", "planned_date", "created_at", "id")
    )

    billings = []
    natural_keys_seen: set[tuple[object, date]] = set()
    for milestone in milestones:
        planned_date = milestone.planned_date
        if planned_date is None:  # Narrowing esplicito; la queryset la esclude già.
            continue
        natural_key = (milestone.project_id, planned_date)
        if natural_key in natural_keys_seen:
            continue
        natural_keys_seen.add(natural_key)

        billings.append(
            {
                "id": str(milestone.id),
                "progetto_id": str(milestone.project_id),
                "progetto_codice": milestone.project.code,
                "data_pianificata": planned_date.isoformat(),
                "data_fatturazione": planned_date.isoformat(),
                "data_effettiva": (
                    milestone.actual_date.isoformat() if milestone.actual_date else None
                ),
                "classificazione": "ARRETRATA"
                if planned_date < current_month_start
                else "MESE_CORRENTE",
                "stato": milestone.status,
                "numero_spostamenti": milestone.move_count,
                "spostamenti": milestone.moves,
            }
        )

    billings.sort(
        key=lambda row: (
            row["data_fatturazione"],
            row["progetto_codice"],
            row["data_pianificata"],
            row["id"],
        )
    )

    return {
        "generato_il": today.isoformat(),
        "distribuzione_referenti": by_referent,
        "progetti_per_stato": [
            {"stato": status, "conteggio": project_counts[status]}
            for status in TimesheetStatus.values
        ],
        "wallet": {
            "anno": wallet.year,
            "allocato": _decimal_string(wallet.allocated_days),
            "consumato": _decimal_string(wallet.consumed_days),
            "disponibile": _decimal_string(wallet.available_days),
        },
        "prossime_fatturazioni": {
            "count": len(billings),
            "limit": billing_limit,
            "results": billings[:billing_limit],
        },
    }
