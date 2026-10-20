"""R3 lato wallet: quanto è davvero disponibile in un anno.

    disponibile_anno = somma(gg_allocati - gg_consumati) delle allocazioni APERTE dell'anno
                     + somma(residui non allocati dei progetti con residuo valido secondo R2)

I residui dei progetti con stato di consuntivazione DA_VERIFICARE non entrano nel
disponibile ufficiale: finiscono in un indicatore separato (residui potenziali).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from domain.money import ZERO, quantize_days
from domain.residuals import ResidualState, project_balance_qs, residual_validity

DAYS_OUTPUT = DecimalField(max_digits=12, decimal_places=4)


def allocation_balance_qs(queryset=None):
    """Allocazioni con consumato e disponibile calcolati."""
    from timesheets.models import TimesheetEntry
    from wallet.models import WalletAllocation

    qs = queryset if queryset is not None else WalletAllocation.objects.all()
    consumed = (
        TimesheetEntry.objects.filter(wallet_allocation=OuterRef("pk"))
        .order_by()
        .values("wallet_allocation")
        .annotate(total=Sum("days", output_field=DAYS_OUTPUT))
        .values("total")[:1]
    )
    zero = Value(ZERO, output_field=DAYS_OUTPUT)
    return qs.annotate(
        consumed_days=Coalesce(Subquery(consumed, output_field=DAYS_OUTPUT), zero),
    ).annotate(
        available_days=F("allocated_days") - F("consumed_days"),
    )


@dataclass
class ResidualBucket:
    """Residui raggruppati per stato di validità (R2)."""

    state: str
    days: Decimal = ZERO
    projects: list[dict] = field(default_factory=list)

    def add(self, code: str, days: Decimal, expires_on: date | None, reason: str) -> None:
        self.days = quantize_days(self.days + days)
        self.projects.append(
            {
                "codice": code,
                "giornate": days,
                "scade_il": expires_on,
                "motivo": reason,
            }
        )


@dataclass
class WalletYearBalance:
    """Vista calcolata `wallet_year_balance` (par. 3.2)."""

    year: int
    allocated_days: Decimal = ZERO
    consumed_days: Decimal = ZERO
    available_from_allocations: Decimal = ZERO
    available_from_open_allocations: Decimal = ZERO
    unallocated_valid_days: Decimal = ZERO
    unallocated_expiring_days: Decimal = ZERO
    unallocated_expired_days: Decimal = ZERO
    unverified_potential_days: Decimal = ZERO
    buckets: dict[str, ResidualBucket] = field(default_factory=dict)

    @property
    def available_days(self) -> Decimal:
        """Disponibile ufficiale: allocazioni aperte + residui ancora spendibili."""
        return quantize_days(
            self.available_from_open_allocations
            + self.unallocated_valid_days
            + self.unallocated_expiring_days
        )

    def as_dict(self) -> dict:
        return {
            "anno": self.year,
            "allocato": self.allocated_days,
            "consumato": self.consumed_days,
            "disponibile_da_allocazioni": self.available_from_allocations,
            "disponibile_da_allocazioni_aperte": self.available_from_open_allocations,
            "residui_validi_non_allocati": self.unallocated_valid_days,
            "residui_in_scadenza": self.unallocated_expiring_days,
            "residui_scaduti": self.unallocated_expired_days,
            "residui_potenziali_da_verificare": self.unverified_potential_days,
            "disponibile": self.available_days,
            "dettaglio_residui": {
                state: {"giornate": bucket.days, "progetti": bucket.projects}
                for state, bucket in self.buckets.items()
            },
        }


def wallet_year_balance(
    year: int,
    *,
    today: date | None = None,
    years_valid_after_closure: int = 1,
    expiring_window_days: int = 90,
) -> WalletYearBalance:
    """Calcola il bilancio di un anno di wallet."""
    from django.utils import timezone

    from wallet.models import AllocationStatus, WalletAllocation

    today = today or timezone.localdate()
    balance = WalletYearBalance(year=year)

    allocations = allocation_balance_qs(
        WalletAllocation.objects.filter(wallet_year__year=year)
    ).select_related("source_project")

    for allocation in allocations:
        balance.allocated_days = quantize_days(balance.allocated_days + allocation.allocated_days)
        balance.consumed_days = quantize_days(balance.consumed_days + allocation.consumed_days)
        balance.available_from_allocations = quantize_days(
            balance.available_from_allocations + allocation.available_days
        )
        if allocation.status == AllocationStatus.APERTA:
            balance.available_from_open_allocations = quantize_days(
                balance.available_from_open_allocations + allocation.available_days
            )

    for state in (
        ResidualState.VALIDO,
        ResidualState.IN_SCADENZA,
        ResidualState.SCADUTO,
        ResidualState.DA_VERIFICARE,
    ):
        balance.buckets[state] = ResidualBucket(state=state)

    projects = project_balance_qs().filter(residual_days__gt=0)
    for project in projects:
        validity = residual_validity(
            timesheet_status=project.timesheet_status,
            closure_date=project.actual_closure_date,
            today=today,
            years_valid_after_closure=years_valid_after_closure,
            expiring_window_days=expiring_window_days,
        )
        bucket = balance.buckets[validity.state]
        bucket.add(project.code, project.residual_days, validity.expires_on, validity.reason)

    balance.unallocated_valid_days = balance.buckets[ResidualState.VALIDO].days
    balance.unallocated_expiring_days = balance.buckets[ResidualState.IN_SCADENZA].days
    balance.unallocated_expired_days = balance.buckets[ResidualState.SCADUTO].days
    balance.unverified_potential_days = balance.buckets[ResidualState.DA_VERIFICARE].days
    return balance


def wallet_flow(year: int) -> list[dict]:
    """Dati per il diagramma di flusso progetto di origine -> attività."""
    from wallet.models import WalletAllocation

    rows = (
        allocation_balance_qs(WalletAllocation.objects.filter(wallet_year__year=year))
        .select_related("source_project", "activity")
        .order_by("-allocated_days")
    )
    return [
        {
            "origine": row.source_project.code if row.source_project_id else "WALLET-GENERALE",
            "origine_titolo": (
                row.source_project.title if row.source_project_id else "Wallet senza origine"
            ),
            "destinazione": row.activity.code,
            "destinazione_titolo": row.activity.title,
            "allocato": row.allocated_days,
            "consumato": row.consumed_days,
            "disponibile": row.available_days,
            "stato": row.status,
        }
        for row in rows
    ]


def available_residual_for_allocation(project_id, *, exclude_allocation_id=None) -> Decimal:
    """Residuo spendibile di un progetto, usato per bloccare le allocazioni eccessive."""
    from projects.models import Project
    from timesheets.models import TimesheetEntry
    from wallet.models import WalletAllocation

    project = Project.objects.get(pk=project_id)
    direct = TimesheetEntry.objects.filter(project=project).aggregate(
        total=Coalesce(Sum("days", output_field=DAYS_OUTPUT), Value(ZERO, output_field=DAYS_OUTPUT))
    )["total"]
    allocations = WalletAllocation.objects.filter(source_project=project)
    if exclude_allocation_id is not None:
        allocations = allocations.exclude(pk=exclude_allocation_id)
    allocated = allocations.aggregate(
        total=Coalesce(
            Sum("allocated_days", output_field=DAYS_OUTPUT),
            Value(ZERO, output_field=DAYS_OUTPUT),
        )
    )["total"]
    return quantize_days(project.budget_days - direct - allocated)


def expiring_residuals(
    *,
    today: date | None = None,
    years_valid_after_closure: int = 1,
    expiring_window_days: int = 90,
) -> list[dict]:
    """Residui in scadenza entro la finestra, per la dashboard e i controlli."""
    from django.utils import timezone

    today = today or timezone.localdate()
    result: list[dict] = []
    for project in project_balance_qs().filter(residual_days__gt=0):
        validity = residual_validity(
            timesheet_status=project.timesheet_status,
            closure_date=project.actual_closure_date,
            today=today,
            years_valid_after_closure=years_valid_after_closure,
            expiring_window_days=expiring_window_days,
        )
        if validity.state == ResidualState.IN_SCADENZA:
            result.append(
                {
                    "progetto": project,
                    "giornate": project.residual_days,
                    "scade_il": validity.expires_on,
                    "giorni_residui": validity.days_to_expiry,
                }
            )
    return sorted(result, key=lambda row: row["scade_il"])


def unallocated_closed_projects(
    *, today: date | None = None, years_valid_after_closure: int = 1
) -> list[dict]:
    """Progetti chiusi con residuo ancora valido e non allocato."""
    from django.utils import timezone

    from projects.models import TimesheetStatus

    today = today or timezone.localdate()
    rows: list[dict] = []
    closed = project_balance_qs().filter(
        timesheet_status=TimesheetStatus.CHIUSO, residual_days__gt=0
    )
    for project in closed:
        validity = residual_validity(
            timesheet_status=project.timesheet_status,
            closure_date=project.actual_closure_date,
            today=today,
            years_valid_after_closure=years_valid_after_closure,
        )
        if validity.usable:
            rows.append(
                {
                    "progetto": project,
                    "giornate": project.residual_days,
                    "scade_il": validity.expires_on,
                }
            )
    return rows


def allocations_from_expired_residual(
    *, today: date | None = None, years_valid_after_closure: int = 1
) -> list:
    """Allocazioni che poggiano su un residuo già scaduto (R2 violata)."""
    from django.utils import timezone

    from wallet.models import WalletAllocation

    today = today or timezone.localdate()
    offenders = []
    for allocation in WalletAllocation.objects.filter(source_project__isnull=False).select_related(
        "source_project"
    ):
        project = allocation.source_project
        if project is None:
            continue
        validity = residual_validity(
            timesheet_status=project.timesheet_status,
            closure_date=project.actual_closure_date,
            today=today,
            years_valid_after_closure=years_valid_after_closure,
        )
        if validity.state == ResidualState.SCADUTO:
            offenders.append(allocation)
    return offenders


__all__ = [
    "WalletYearBalance",
    "allocation_balance_qs",
    "allocations_from_expired_residual",
    "available_residual_for_allocation",
    "expiring_residuals",
    "unallocated_closed_projects",
    "wallet_flow",
    "wallet_year_balance",
]
