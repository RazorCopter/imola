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
    ongoing_project_residual_days: Decimal = ZERO
    ongoing_project_overrun_days: Decimal = ZERO
    total_source_capacity: Decimal = ZERO
    buckets: dict[str, ResidualBucket] = field(default_factory=dict)
    allocations: list[dict] = field(default_factory=list)

    @property
    def available_days(self) -> Decimal:
        """Disponibile del wallet: allocato meno consumato, incluse allocazioni chiuse."""
        return self.available_from_allocations

    @property
    def available_with_project_residuals(self) -> Decimal:
        """Alias interno deprecato; l'API espone `capienza_wallet_potenziale`."""
        return self.potential_wallet_capacity

    @property
    def budget_residuo_progetti_in_corso(self) -> Decimal:
        return self.ongoing_project_residual_days

    @property
    def sforamenti_progetti_in_corso(self) -> Decimal:
        return self.ongoing_project_overrun_days

    @property
    def potential_wallet_capacity(self) -> Decimal:
        """Capienza totale wallet: somma spendibile da progetti validi/in scadenza."""
        if self.total_source_capacity > ZERO:
            return self.total_source_capacity
        return quantize_days(
            self.available_from_open_allocations
            + self.unallocated_valid_days
            + self.unallocated_expiring_days
        )

    @property
    def unallocated_capacity(self) -> Decimal:
        """Residuo del monte wallet non allocato: max(0, capacita - allocato)."""
        return quantize_days(max(ZERO, self.potential_wallet_capacity - self.allocated_days))

    @property
    def allocations_total(self) -> Decimal:
        return self.allocated_days

    def as_dict(self) -> dict:
        unallocated = self.unallocated_capacity
        return {
            "anno": self.year,
            "allocato": self.allocated_days,
            "totale_allocato": self.allocated_days,
            "allocations_total": self.allocated_days,
            "consumato": self.consumed_days,
            "consumato_allocazioni": self.consumed_days,
            "consumed_days": self.consumed_days,
            "disponibile": self.available_days,
            "disponibile_su_allocazioni": self.available_days,
            "available_days": self.available_days,
            "disponibile_da_allocazioni": self.available_from_allocations,
            "disponibile_da_allocazioni_aperte": self.available_from_open_allocations,
            "capienza_wallet_potenziale": self.potential_wallet_capacity,
            "capacita_totale_origini": self.potential_wallet_capacity,
            "potential_wallet_capacity": self.potential_wallet_capacity,
            "residuo_wallet_non_allocato": unallocated,
            "unallocated_capacity": unallocated,
            "residui_validi_non_allocati": self.unallocated_valid_days,
            "residui_in_scadenza": self.unallocated_expiring_days,
            "budget_residuo_progetti_in_corso": self.ongoing_project_residual_days,
            "sforamenti_progetti_in_corso": self.ongoing_project_overrun_days,
            "residui_scaduti": self.unallocated_expired_days,
            "residui_potenziali_da_verificare": self.unverified_potential_days,
            "allocazioni": self.allocations,
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

    from wallet.models import AllocationStatus, WalletAllocation, WalletSourceLot, WalletYear

    today = today or timezone.localdate()
    balance = WalletYearBalance(year=year)
    source_lots = list(
        WalletSourceLot.objects.filter(wallet_year__year=year)
        .select_related("source_project")
        .prefetch_related("funding_tranches")
        .order_by("source_year", "effective_date", "source_project__code")
    )
    if source_lots:
        balance.total_source_capacity = quantize_days(
            sum((lot.capacity_days for lot in source_lots), ZERO)
        )
        wallet_year = WalletYear.objects.filter(year=year).first()
        if wallet_year is not None:
            balance.total_source_capacity = quantize_days(
                balance.total_source_capacity + wallet_year.reconciliation_adjustment_days
            )

    allocations = allocation_balance_qs(
        WalletAllocation.objects.filter(wallet_year__year=year)
    ).select_related("source_project", "activity")

    for allocation in allocations:
        balance.allocated_days = quantize_days(balance.allocated_days + allocation.allocated_days)
        balance.consumed_days = quantize_days(balance.consumed_days + allocation.consumed_days)
        balance.available_from_allocations = quantize_days(
            balance.available_from_allocations + allocation.available_days
        )
        balance.allocations.append(
            {
                "riferimento": allocation.external_ref,
                "progetto_origine": (
                    allocation.source_project.code if allocation.source_project else None
                ),
                "attivita": allocation.activity.code,
                "allocato": allocation.allocated_days,
                "consumato": allocation.consumed_days,
                "disponibile": allocation.available_days,
                "stato": allocation.status,
            }
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

    from projects.models import ContractType, TimesheetStatus

    projects = project_balance_qs().exclude(contract_type=ContractType.CANONE)
    for project in projects:
        explicit_capacity = quantize_days(project.released_to_wallet_days)
        explicit_capacity_applies = project.declared_residual_year in {None, year}
        if not source_lots and explicit_capacity > ZERO and explicit_capacity_applies:
            balance.total_source_capacity = quantize_days(
                balance.total_source_capacity + explicit_capacity
            )

        if project.timesheet_status in {
            TimesheetStatus.ATTIVO,
            TimesheetStatus.NON_AVVIATO,
        }:
            if project.residual_days < ZERO:
                balance.ongoing_project_overrun_days = quantize_days(
                    balance.ongoing_project_overrun_days + project.residual_days
                )
            elif project.residual_days > ZERO:
                balance.ongoing_project_residual_days = quantize_days(
                    balance.ongoing_project_residual_days + project.residual_days
                )
            continue

        if project.residual_days <= ZERO:
            continue

        if project.timesheet_status == TimesheetStatus.CHIUSO and project.actual_closure_date:
            if project.actual_closure_date.year > year:
                continue
            validity = residual_validity(
                timesheet_status=project.timesheet_status,
                closure_date=project.actual_closure_date,
                today=today,
                years_valid_after_closure=years_valid_after_closure,
                expiring_window_days=expiring_window_days,
            )
            balance.buckets[validity.state].add(
                project.code, project.residual_days, validity.expires_on, validity.reason
            )
            if not source_lots and validity.usable and explicit_capacity <= ZERO:
                project_capacity = quantize_days(
                    max(ZERO, project.residual_days + project.allocated_to_wallet_days)
                )
                balance.total_source_capacity = quantize_days(
                    balance.total_source_capacity + project_capacity
                )
            continue

        validity = residual_validity(
            timesheet_status=project.timesheet_status,
            closure_date=project.actual_closure_date,
            today=today,
            years_valid_after_closure=years_valid_after_closure,
            expiring_window_days=expiring_window_days,
        )
        if validity.state == ResidualState.DA_VERIFICARE:
            balance.buckets[ResidualState.DA_VERIFICARE].add(
                project.code, project.residual_days, validity.expires_on, validity.reason
            )

    balance.unallocated_valid_days = balance.buckets[ResidualState.VALIDO].days
    balance.unallocated_expiring_days = balance.buckets[ResidualState.IN_SCADENZA].days
    balance.unallocated_expired_days = balance.buckets[ResidualState.SCADUTO].days
    balance.unverified_potential_days = balance.buckets[ResidualState.DA_VERIFICARE].days
    return balance


def wallet_flow(year: int, *, today: date | None = None) -> list[dict]:
    """Contratto tabellare completo, senza N+1, per le allocazioni dell'anno.

    ``residuo_allocazione`` è ``allocato - consumato``. Il distinto
    ``residuo_spendibile_origine`` è invece il budget del progetto sorgente meno
    consuntivi diretti e tutte le sue allocazioni. Lo stato operativo deriva dal
    campo contabile esplicito ``WalletAllocation.status``.
    """
    from django.utils import timezone

    from core.models import AppSettings
    from timesheets.models import TimesheetEntry
    from wallet.models import AllocationStatus, WalletAllocation

    today = today or timezone.localdate()
    settings_obj = AppSettings.get_solo()
    zero = Value(ZERO, output_field=DAYS_OUTPUT)
    source_consumed = (
        TimesheetEntry.objects.filter(project_id=OuterRef("source_project_id"))
        .order_by()
        .values("project_id")
        .annotate(total=Sum("days", output_field=DAYS_OUTPUT))
        .values("total")[:1]
    )
    source_allocated = (
        WalletAllocation.objects.filter(source_project_id=OuterRef("source_project_id"))
        .order_by()
        .values("source_project_id")
        .annotate(total=Sum("allocated_days", output_field=DAYS_OUTPUT))
        .values("total")[:1]
    )
    rows = (
        allocation_balance_qs(WalletAllocation.objects.filter(wallet_year__year=year))
        .select_related("source_project", "activity", "assignee")
        .prefetch_related("funding_tranches__source_lot__source_project")
        .annotate(
            source_consumed_days=Coalesce(Subquery(source_consumed), zero),
            source_allocated_days=Coalesce(Subquery(source_allocated), zero),
        )
        .order_by("-allocated_days")
    )
    result = []
    for row in rows:
        validity_state = None
        validity_expires_on = None
        source_remaining = None
        if row.source_project_id:
            project = row.source_project
            source_remaining = quantize_days(
                project.budget_days - row.source_consumed_days - row.source_allocated_days
            )
            validity = residual_validity(
                timesheet_status=project.timesheet_status,
                closure_date=project.actual_closure_date,
                today=today,
                years_valid_after_closure=settings_obj.residual_years_after_closure,
                expiring_window_days=settings_obj.residual_expiring_window_days,
            )
            validity_state = validity.state
            validity_expires_on = validity.expires_on
        funding = [
            {
                "ordine": tranche.sequence,
                "lotto": tranche.source_lot.external_ref,
                "progetto_origine": tranche.source_lot.source_project.code,
                "anno_provenienza": tranche.source_lot.source_year,
                "riservato_iniziale": tranche.initial_reserved_days,
                "impegnato": tranche.committed_days,
                "consumato": tranche.consumed_days,
            }
            for tranche in row.funding_tranches.all()
        ]
        result.append(
            {
                "id": row.id,
                "version": row.version,
                "notes": row.notes,
                "riferimento": row.external_ref,
                "origine": row.source_project.code if row.source_project_id else "WALLET-GENERALE",
                "origine_id": row.source_project_id,
                "origine_titolo": (
                    row.source_project.title
                    if row.source_project_id
                    else "Monte Wallet (pool generico)"
                ),
                "fonti_fifo": funding,
                "destinazione": row.activity.code,
                "destinazione_id": row.activity_id,
                "destinazione_titolo": row.activity.title,
                "tipo_attivita": row.activity.kind,
                "architetto_id": row.assignee_id,
                "architetto": row.assignee.full_name if row.assignee_id else None,
                "allocato": row.allocated_days,
                "consumato": row.consumed_days,
                "disponibile": row.available_days,
                "residuo_allocazione": row.available_days,
                "residuo_spendibile_origine": source_remaining,
                "validita_origine": validity_state,
                "scadenza_origine": validity_expires_on,
                "stato": row.status,
                "motivo_chiusura": row.closure_reason,
                "stato_operativo": (
                    "CHIUSA" if row.status == AllocationStatus.CHIUSA else "IN_CORSO"
                ),
            }
        )
    return result


def wallet_by_assignee(year: int) -> list[dict]:
    """Totali di allocato, consumato e residuo raggruppati per architetto."""
    from wallet.models import WalletAllocation

    rows = (
        allocation_balance_qs(
            WalletAllocation.objects.filter(wallet_year__year=year, assignee__isnull=False)
        )
        .values("assignee_id", "assignee__full_name")
        .annotate(
            allocated_total=Sum("allocated_days", output_field=DAYS_OUTPUT),
            consumed_total=Sum("consumed_days", output_field=DAYS_OUTPUT),
            available_total=Sum("available_days", output_field=DAYS_OUTPUT),
        )
        .order_by("assignee__full_name")
    )
    return [
        {
            "architetto_id": row["assignee_id"],
            "architetto": row["assignee__full_name"],
            "allocato": quantize_days(row["allocated_total"]),
            "consumato": quantize_days(row["consumed_total"]),
            "residuo": quantize_days(row["available_total"]),
        }
        for row in rows
    ]


def available_residual_for_allocation(project_id, *, exclude_allocation_id=None) -> Decimal:
    """Residuo spendibile solo per un progetto chiuso, datato e non scaduto."""
    from django.utils import timezone

    from core.models import AppSettings
    from projects.models import Project, TimesheetStatus
    from timesheets.models import TimesheetEntry
    from wallet.models import WalletAllocation

    project = Project.objects.get(pk=project_id)
    allocations = WalletAllocation.objects.filter(source_project=project)
    if exclude_allocation_id is not None:
        allocations = allocations.exclude(pk=exclude_allocation_id)
    allocated = allocations.aggregate(
        total=Coalesce(
            Sum("allocated_days", output_field=DAYS_OUTPUT),
            Value(ZERO, output_field=DAYS_OUTPUT),
        )
    )["total"]

    if project.released_to_wallet_days > ZERO:
        return quantize_days(project.released_to_wallet_days - allocated)

    if project.timesheet_status != TimesheetStatus.CHIUSO or project.actual_closure_date is None:
        return ZERO

    settings_obj = AppSettings.get_solo()
    validity = residual_validity(
        timesheet_status=project.timesheet_status,
        closure_date=project.actual_closure_date,
        today=timezone.localdate(),
        years_valid_after_closure=settings_obj.residual_years_after_closure,
        expiring_window_days=settings_obj.residual_expiring_window_days,
    )
    if not validity.usable:
        return ZERO

    direct = TimesheetEntry.objects.filter(project=project).aggregate(
        total=Coalesce(Sum("days", output_field=DAYS_OUTPUT), Value(ZERO, output_field=DAYS_OUTPUT))
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
    """Allocazioni create dopo la scadenza del residuo sorgente.

    La scadenza successiva non invalida una quota assegnata in tempo. Finché il modello
    non espone una data efficace dedicata, `created_at` è l'unica evidenza disponibile.
    """
    from django.utils import timezone

    from wallet.models import WalletAllocation

    today = today or timezone.localdate()
    offenders = []
    for allocation in WalletAllocation.objects.filter(source_project__isnull=False).select_related(
        "source_project"
    ):
        project = allocation.source_project
        allocated_on = allocation.created_at.date()
        if project is None or project.actual_closure_date is None or allocated_on > today:
            continue
        validity_at_allocation = residual_validity(
            timesheet_status=project.timesheet_status,
            closure_date=project.actual_closure_date,
            today=allocated_on,
            years_valid_after_closure=years_valid_after_closure,
        )
        if validity_at_allocation.state == ResidualState.SCADUTO:
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
