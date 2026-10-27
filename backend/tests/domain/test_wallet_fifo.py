from datetime import date
from decimal import Decimal

import pytest

from projects.models import OfferStatus, TimesheetStatus
from tests.factories import ProjectFactory, TimesheetEntryFactory, WalletActivityFactory
from wallet.models import (
    AllocationClosureReason,
    AllocationStatus,
    SourceLotStatus,
    WalletAllocation,
    WalletSourceLot,
    WalletYear,
)
from wallet.services import close_allocation, reserve_fifo, source_lot_totals

pytestmark = pytest.mark.django_db


def _project(code: str):
    return ProjectFactory(
        code=code,
        offer_status=OfferStatus.ACCETTATA,
        timesheet_status=TimesheetStatus.ATTIVO,
    )


def _lot(wallet_year, project, year, capacity, effective_date):
    return WalletSourceLot.objects.create(
        wallet_year=wallet_year,
        source_project=project,
        source_year=year,
        capacity_days=Decimal(capacity),
        effective_date=effective_date,
        external_ref=f"LOT-{project.code}",
    )


def test_riserva_fifo_erode_prima_anno_precedente_e_rilascia_residuo():
    wallet_year = WalletYear.objects.create(year=2026)
    lot_a = _lot(wallet_year, _project("FIFO-A"), 2025, "3.0000", date(2025, 1, 31))
    lot_b = _lot(wallet_year, _project("FIFO-B"), 2025, "4.0000", date(2025, 6, 30))
    _lot(wallet_year, _project("FIFO-C"), 2026, "8.0000", date(2026, 1, 31))
    allocation = WalletAllocation.objects.create(
        wallet_year=wallet_year,
        activity=WalletActivityFactory(code="FIFO-USE"),
        allocated_days=Decimal("5.0000"),
        initial_allocated_days=Decimal("5.0000"),
        external_ref="USE-FIFO",
    )

    tranches = reserve_fifo(allocation, Decimal("5.0000"))

    assert [(item.source_lot_id, item.committed_days) for item in tranches] == [
        (lot_a.id, Decimal("3.0000")),
        (lot_b.id, Decimal("2.0000")),
    ]

    TimesheetEntryFactory(wallet_allocation=allocation, days=Decimal("3.0000"))
    released = close_allocation(allocation)
    allocation.refresh_from_db()
    lot_a.refresh_from_db()

    assert released == Decimal("2.0000")
    assert allocation.status == AllocationStatus.CHIUSA
    assert allocation.closure_reason == AllocationClosureReason.CON_RESIDUO
    assert lot_a.status == SourceLotStatus.CHIUSURA_DA_VALIDARE
    assert source_lot_totals(lot_b) == (
        Decimal("0.0000"),
        Decimal("0.0000"),
        Decimal("4.0000"),
    )


def test_un_progetto_chiuso_non_diventa_lotto_implicitamente():
    wallet_year = WalletYear.objects.create(year=2026)
    ProjectFactory(
        code="CLOSED-NOT-WALLET",
        budget_days=Decimal("10.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2025, 12, 31),
    )
    allocation = WalletAllocation.objects.create(
        wallet_year=wallet_year,
        activity=WalletActivityFactory(code="NO-IMPLICIT-LOT"),
        allocated_days=Decimal("1.0000"),
        initial_allocated_days=Decimal("1.0000"),
        external_ref="USE-NO-LOT",
    )

    with pytest.raises(ValueError, match="Capienza wallet insufficiente"):
        reserve_fifo(allocation, Decimal("1.0000"))

    assert WalletSourceLot.objects.count() == 0
