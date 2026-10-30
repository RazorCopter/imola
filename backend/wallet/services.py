from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from domain.money import ZERO, quantize_days
from wallet.models import (
    AllocationClosureReason,
    AllocationStatus,
    SourceLotStatus,
    WalletAllocation,
    WalletFundingTranche,
    WalletSourceLot,
)


def source_lot_totals(lot: WalletSourceLot) -> tuple[Decimal, Decimal, Decimal]:
    totals = lot.funding_tranches.aggregate(
        committed=Sum("committed_days"), consumed=Sum("consumed_days")
    )
    committed = quantize_days(totals["committed"] or ZERO)
    consumed = quantize_days(totals["consumed"] or ZERO)
    available = quantize_days(max(ZERO, lot.capacity_days - committed))
    return committed, consumed, available


def refresh_source_lot_status(lot: WalletSourceLot) -> None:
    committed, consumed, available = source_lot_totals(lot)
    if consumed >= lot.capacity_days and lot.capacity_days > ZERO:
        status = SourceLotStatus.CHIUSURA_DA_VALIDARE
    elif committed > ZERO or available < lot.capacity_days:
        status = SourceLotStatus.IMPEGNATO
    else:
        status = SourceLotStatus.DISPONIBILE
    if lot.status != SourceLotStatus.CHIUSO and lot.status != status:
        lot.status = status
        lot.save(update_fields=["status", "updated_at", "version"])


AUTO_LOT_PREFIX = "AUTO-CHIUSURA"


def wallet_capacity_of(project) -> Decimal:
    """Giornate del progetto che entrano nel wallet alla chiusura.

    E' la stessa grandezza che `domain.wallet_balance` attribuisce al progetto quando non
    esistono lotti: la quota esplicitamente rilasciata, se dichiarata, altrimenti il budget
    non consumato in diretta. Le allocazioni FIFO non hanno progetto di origine, quindi non
    vanno sottratte qui: a scalare il lotto pensano le tranche di finanziamento.
    """
    from timesheets.models import TimesheetEntry

    declared = quantize_days(project.released_to_wallet_days or ZERO)
    if declared > ZERO:
        return declared
    direct = (
        TimesheetEntry.objects.filter(project=project).aggregate(total=Sum("days"))["total"] or ZERO
    )
    return quantize_days(max(ZERO, project.budget_days - quantize_days(direct)))


@transaction.atomic
def ensure_source_lot(project, *, today=None) -> WalletSourceLot | None:
    """Crea (o aggiorna) il lotto wallet del residuo di un progetto chiuso.

    Senza questo lotto la capienza del wallet resta una grandezza solo calcolata: il
    bilancio la mostra partendo dai residui dei progetti chiusi, ma `reserve_fifo` non
    trova nulla da prelevare e ogni nuovo utilizzo viene rifiutato per capienza
    insufficiente. Il lotto rende quel residuo una fonte reale e tracciabile.

    Idempotente: un progetto ha un solo lotto per anno wallet (vincolo di unicita). La
    capienza viene riallineata solo finche nessuna tranche ha impegnato giornate, perche
    oltre quel punto ridurla falsificherebbe utilizzi gia registrati.
    """
    from django.utils import timezone

    from core.models import AppSettings
    from domain.residuals import residual_validity
    from projects.models import ContractType, TimesheetStatus
    from wallet.models import WalletYear

    if project.contract_type == ContractType.CANONE:
        return None
    if project.timesheet_status != TimesheetStatus.CHIUSO or not project.actual_closure_date:
        return None

    settings_obj = AppSettings.get_solo()
    validity = residual_validity(
        timesheet_status=project.timesheet_status,
        closure_date=project.actual_closure_date,
        today=today or timezone.localdate(),
        years_valid_after_closure=settings_obj.residual_years_after_closure,
        expiring_window_days=settings_obj.residual_expiring_window_days,
    )
    if not validity.usable:
        return None

    capacity = wallet_capacity_of(project)
    # `source_year` dice da dove arrivano le giornate, `wallet_year` quale wallet le spende:
    # il residuo di un progetto chiuso l'anno scorso, se ancora valido, si spende da quello
    # corrente. Tenerlo nell'anno di chiusura lo renderebbe invisibile al wallet in uso.
    source_year = project.actual_closure_date.year
    wallet_year_number = max(source_year, (today or timezone.localdate()).year)
    existing = WalletSourceLot.objects.select_for_update().filter(source_project=project).first()
    if existing is not None:
        committed = source_lot_totals(existing)[0]
        fields: list[str] = []
        if committed <= ZERO and existing.capacity_days != capacity:
            existing.capacity_days = capacity
            fields.append("capacity_days")
        # Finche nessuna tranche ha impegnato giornate il lotto puo ancora cambiare wallet:
        # cosi un lotto finito nell'anno sbagliato si riallinea al wallet che lo spende,
        # invece di restare invisibile e richiedere una correzione a mano.
        if committed <= ZERO and existing.wallet_year.year != wallet_year_number:
            existing.wallet_year, _ = WalletYear.objects.get_or_create(year=wallet_year_number)
            fields.append("wallet_year")
        if fields:
            existing.save(update_fields=[*fields, "updated_at", "version"])
            refresh_source_lot_status(existing)
        return existing
    if capacity <= ZERO:
        return None

    wallet_year, _ = WalletYear.objects.get_or_create(year=wallet_year_number)
    return WalletSourceLot.objects.create(
        wallet_year=wallet_year,
        source_project=project,
        source_year=source_year,
        capacity_days=capacity,
        effective_date=project.actual_closure_date,
        external_ref=f"{AUTO_LOT_PREFIX}:{project.code}:{wallet_year_number}",
        notes="Lotto creato alla chiusura del progetto.",
    )


@transaction.atomic
def reserve_fifo(
    allocation: WalletAllocation,
    requested_days: Decimal,
) -> list[WalletFundingTranche]:
    remaining = quantize_days(requested_days)
    qs = (
        WalletSourceLot.objects.select_for_update()
        .filter(wallet_year=allocation.wallet_year)
        .exclude(status=SourceLotStatus.CHIUSO)
        .select_related("source_project")
    )
    qs = qs.order_by("source_year", "effective_date", "source_project__code", "pk")
    lots = list(qs)
    available = [(lot, source_lot_totals(lot)[2]) for lot in lots]
    if sum((days for _, days in available), ZERO) < remaining:
        raise ValueError("Capienza wallet insufficiente per la riserva richiesta.")
    created: list[WalletFundingTranche] = []
    start_sequence = (
        allocation.funding_tranches.order_by("-sequence").values_list("sequence", flat=True).first()
        or 0
    )
    for lot, lot_available in available:
        if remaining <= ZERO:
            break
        take = quantize_days(min(remaining, lot_available))
        if take <= ZERO:
            continue
        sequence = start_sequence + len(created) + 1
        created.append(
            WalletFundingTranche.objects.create(
                allocation=allocation,
                source_lot=lot,
                sequence=sequence,
                initial_reserved_days=take,
                committed_days=take,
                external_ref=f"{allocation.external_ref or allocation.pk}:F{sequence:02d}",
            )
        )
        remaining = quantize_days(remaining - take)
        refresh_source_lot_status(lot)
    if created and allocation.requires_source_attribution:
        allocation.requires_source_attribution = False
        allocation.save(update_fields=["requires_source_attribution", "updated_at", "version"])
    return created


@transaction.atomic
def resize_allocation(allocation: WalletAllocation, new_days: Decimal) -> None:
    sync_allocation_funding(allocation)
    current = quantize_days(allocation.allocated_days)
    target = quantize_days(new_days)
    if target > current:
        reserve_fifo(allocation, target - current)
    elif target < current:
        to_release = current - target
        for tranche in allocation.funding_tranches.select_for_update().order_by("-sequence"):
            releasable = max(ZERO, tranche.committed_days - tranche.consumed_days)
            released = min(to_release, releasable)
            if released > ZERO:
                tranche.committed_days = quantize_days(tranche.committed_days - released)
                tranche.save(update_fields=["committed_days", "updated_at", "version"])
                refresh_source_lot_status(tranche.source_lot)
                to_release = quantize_days(to_release - released)
            if to_release <= ZERO:
                break
        if to_release > ZERO:
            raise ValueError("La riduzione richiesta intacca giornate già consumate.")
    allocation.allocated_days = target
    allocation.initial_allocated_days = target
    allocation.save()


@transaction.atomic
def sync_allocation_funding(allocation: WalletAllocation) -> Decimal:
    consumed_total = allocation.timesheet_entries.aggregate(total=Sum("days"))["total"] or ZERO
    consumed_total = quantize_days(max(ZERO, consumed_total))
    remaining = consumed_total
    tranches = list(
        allocation.funding_tranches.select_for_update()
        .select_related("source_lot")
        .order_by("sequence")
    )
    for tranche in tranches:
        consumed = quantize_days(min(max(remaining, ZERO), tranche.committed_days))
        if tranche.consumed_days != consumed:
            tranche.consumed_days = consumed
            tranche.save(update_fields=["consumed_days", "updated_at", "version"])
        remaining = quantize_days(remaining - consumed)
    for tranche in tranches:
        refresh_source_lot_status(tranche.source_lot)
    return consumed_total


@transaction.atomic
def close_allocation(allocation: WalletAllocation) -> Decimal:
    consumed = sync_allocation_funding(allocation)
    released = ZERO
    for tranche in allocation.funding_tranches.select_for_update().select_related("source_lot"):
        if tranche.committed_days > tranche.consumed_days:
            released = quantize_days(released + tranche.committed_days - tranche.consumed_days)
            tranche.committed_days = tranche.consumed_days
            tranche.save(update_fields=["committed_days", "updated_at", "version"])
        refresh_source_lot_status(tranche.source_lot)
    allocation.status = AllocationStatus.CHIUSA
    allocation.closure_reason = (
        AllocationClosureReason.ESAURITA
        if consumed >= allocation.initial_allocated_days
        else AllocationClosureReason.CON_RESIDUO
    )
    allocation.allocated_days = consumed
    allocation.closed_at = timezone.now()
    allocation.save()
    return released
