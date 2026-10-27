"""R3 lato wallet: disponibile dell'anno, residui per validità, blocco delle allocazioni.

Copre il caso obbligatorio 11.4 (totali del wallet 2026 dopo il seed) con gli stessi numeri
del seed reale, riprodotti qui su progetti sintetici.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from domain.residuals import ResidualState
from domain.wallet_balance import (
    allocation_balance_qs,
    allocations_from_expired_residual,
    available_residual_for_allocation,
    expiring_residuals,
    unallocated_closed_projects,
    wallet_by_assignee,
    wallet_flow,
    wallet_year_balance,
)
from projects.models import TimesheetStatus
from tests.factories import (
    ProjectFactory,
    TimesheetEntryFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)
from wallet.models import AllocationStatus

pytestmark = pytest.mark.django_db


def allocate(
    code: str,
    allocated: str,
    consumed: str,
    *,
    status=AllocationStatus.APERTA,
    project=None,
    year=2026,
):
    """Crea un'allocazione con il relativo consuntivo iniziale."""
    project = project or ProjectFactory(
        code=f"IM26-{code}", budget_days=Decimal(allocated) + Decimal("5")
    )
    allocation = WalletAllocationFactory(
        wallet_year=WalletYearFactory(year=year),
        source_project=project,
        activity=WalletActivityFactory(code=f"ATT-{code}"),
        allocated_days=Decimal(allocated),
        status=status,
    )
    if Decimal(consumed) != 0:
        TimesheetEntryFactory(wallet_allocation=allocation, days=Decimal(consumed))
    return allocation


class TestBilancioAllocazioni:
    def test_consumato_e_disponibile_sono_calcolati(self):
        allocation = allocate("A", "6.3800", "6.6300")
        row = allocation_balance_qs().get(pk=allocation.pk)
        assert row.consumed_days == Decimal("6.6300")
        assert row.available_days == Decimal("-0.2500")  # sforamento, non un blocco

    def test_allocazione_senza_consuntivi_ha_disponibile_pieno(self):
        allocation = allocate("B", "4.0000", "0")
        row = allocation_balance_qs().get(pk=allocation.pk)
        assert row.consumed_days == Decimal("0.0000")
        assert row.available_days == Decimal("4.0000")

    def test_flow_distingue_residuo_allocazione_origine_validita_e_stato(self):
        project = ProjectFactory(
            code="IM26-FLOW",
            budget_days=Decimal("20.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=date(2026, 1, 15),
        )
        TimesheetEntryFactory(project=project, days=Decimal("3.0000"))
        allocation = allocate("FLOW", "8.0000", "2.5000", project=project)

        row = next(
            item
            for item in wallet_flow(2026, today=date(2026, 6, 1))
            if item["id"] == allocation.id
        )

        assert row["allocato"] == Decimal("8.0000")
        assert row["consumato"] == Decimal("2.5000")
        assert row["residuo_allocazione"] == Decimal("5.5000")
        assert row["residuo_spendibile_origine"] == Decimal("9.0000")
        assert row["validita_origine"] in {ResidualState.VALIDO, ResidualState.IN_SCADENZA}
        assert row["stato_operativo"] == "IN_CORSO"

        allocation.status = AllocationStatus.CHIUSA
        allocation.save()
        closed = next(item for item in wallet_flow(2026) if item["id"] == allocation.id)
        assert closed["stato_operativo"] == "CHIUSA"


class TestCaso11_4TotaliWallet2026:
    """Allocato 130,89 - consumato 120,79 -> disponibile da allocazioni 10,10 gg."""

    def setup_allocations(self):
        # Tre allocazioni aperte e una chiusa (bilanciata), per un totale che riproduce
        # le somme del seed reale.
        allocate("W1", "100.8900", "95.7900")
        allocate("W2", "20.0000", "15.0000")
        allocate("W3", "5.0000", "5.0000", status=AllocationStatus.CHIUSA)
        allocate("W4", "5.0000", "5.0000", status=AllocationStatus.CHIUSA)

    def test_totali_del_wallet(self):
        self.setup_allocations()
        balance = wallet_year_balance(2026, today=date(2026, 10, 20))
        assert balance.allocated_days == Decimal("130.8900")
        assert balance.consumed_days == Decimal("120.7900")
        assert balance.available_from_allocations == Decimal("10.1000")

    def test_le_allocazioni_chiuse_bilanciate_non_aggiungono_disponibile(self):
        self.setup_allocations()
        balance = wallet_year_balance(2026, today=date(2026, 10, 20))
        assert balance.available_from_open_allocations == Decimal("10.1000")

    def test_i_residui_da_verificare_restano_separati(self):
        """I progetti con consuntivazione DA_VERIFICARE non entrano nel disponibile."""
        self.setup_allocations()
        ProjectFactory(
            code="IM25151-DA-VERIFICARE",
            budget_days=Decimal("30.0000"),
            timesheet_status=TimesheetStatus.DA_VERIFICARE,
        )
        balance = wallet_year_balance(2026, today=date(2026, 10, 20))
        assert balance.unverified_potential_days == Decimal("30.0000")
        assert Decimal("30.0000") not in (
            balance.unallocated_valid_days,
            balance.unallocated_expiring_days,
        )
        # Il saldo wallet resta allocato - consumato; i residui di progetto sono separati.
        assert balance.available_days == Decimal("10.1000")
        assert balance.available_with_project_residuals == (
            Decimal("10.1000") + balance.unallocated_valid_days
        )
        assert balance.buckets[ResidualState.DA_VERIFICARE].days == Decimal("30.0000")


class TestResiduiPerValidita:
    def test_quota_esplicitamente_rilasciata_alimenta_il_monte_wallet(self):
        project = ProjectFactory(
            code="IM26-WALLET",
            budget_days=Decimal("25.0000"),
            released_to_wallet_days=Decimal("14.5000"),
            declared_residual_year=2026,
            timesheet_status=TimesheetStatus.ATTIVO,
        )
        allocate("RELEASED", "4.0000", "1.0000", project=project)

        balance = wallet_year_balance(2026, today=date(2026, 10, 20))

        assert balance.total_source_capacity == Decimal("14.5000")
        assert balance.unallocated_capacity == Decimal("10.5000")
        assert available_residual_for_allocation(project.id) == Decimal("10.5000")
        assert wallet_year_balance(2025).total_source_capacity == Decimal("0.0000")

    def test_i_bucket_separano_valido_in_scadenza_e_scaduto(self):
        ProjectFactory(
            code="IM26-ATTIVO",
            budget_days=Decimal("20.0000"),
            released_to_wallet_days=Decimal("10.0000"),
        )
        ProjectFactory(
            code="IM25-CHIUSO-IN-SCADENZA",
            budget_days=Decimal("7.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=date(2025, 11, 15),
        )
        ProjectFactory(
            code="IM23-CHIUSO-SCADUTO",
            budget_days=Decimal("3.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=date(2023, 5, 1),
        )
        WalletYearFactory(year=2026)

        balance = wallet_year_balance(2026, today=date(2026, 10, 20))
        assert balance.unallocated_valid_days == Decimal("0.0000")
        assert balance.ongoing_project_residual_days == Decimal("20.0000")
        assert balance.unallocated_expiring_days == Decimal("7.0000")
        assert balance.unallocated_expired_days == Decimal("3.0000")

    def test_residui_in_scadenza_ordinati_per_data(self):
        ProjectFactory(
            code="IM25-A",
            budget_days=Decimal("2.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=date(2025, 1, 10),
        )
        rows = expiring_residuals(today=date(2026, 10, 20))
        assert [row["progetto"].code for row in rows] == ["IM25-A"]
        assert rows[0]["scade_il"] == date(2026, 12, 31)

    def test_progetti_chiusi_con_residuo_valido_non_allocato(self):
        ProjectFactory(
            code="IM26-CHIUSO-CON-RESIDUO",
            budget_days=Decimal("5.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=date(2026, 3, 31),
        )
        rows = unallocated_closed_projects(today=date(2026, 10, 20))
        assert len(rows) == 1
        assert rows[0]["giornate"] == Decimal("5.0000")
        assert rows[0]["scade_il"] == date(2027, 12, 31)

    def test_allocazione_creata_prima_della_scadenza_resta_valida(self):
        expired = ProjectFactory(
            code="IM24-EXP",
            budget_days=Decimal("10.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=date(2024, 12, 1),
        )
        allocation = allocate("EXP", "2.0000", "1.0000", project=expired)
        allocation.created_at = datetime(2025, 6, 1, tzinfo=UTC)
        allocation.save(update_fields=["created_at"])

        offenders = allocations_from_expired_residual(today=date(2026, 10, 20))

        assert offenders == []

    def test_allocazione_creata_dopo_la_scadenza_e_irregolare(self):
        expired = ProjectFactory(
            code="IM24-LATE",
            budget_days=Decimal("10.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=date(2024, 12, 1),
        )
        allocation = allocate("LATE", "2.0000", "0.0000", project=expired)
        allocation.created_at = datetime(2026, 1, 2, tzinfo=UTC)
        allocation.save(update_fields=["created_at"])

        offenders = allocations_from_expired_residual(today=date(2026, 10, 20))

        assert [row.id for row in offenders] == [allocation.id]


class TestResiduoDisponibilePerAllocazione:
    def test_tiene_conto_di_consumi_e_altre_allocazioni(self):
        project = ProjectFactory(
            code="IM26-RESIDUO",
            budget_days=Decimal("25.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=date(2026, 1, 15),
        )
        TimesheetEntryFactory(project=project, days=Decimal("10.5000"))
        allocation = WalletAllocationFactory(
            source_project=project,
            activity=WalletActivityFactory(code="ATT-RESIDUO"),
            allocated_days=Decimal("11.0000"),
            wallet_year=WalletYearFactory(year=2026),
        )
        assert available_residual_for_allocation(project.id) == Decimal("3.5000")
        # Escludendo l'allocazione stessa (caso di modifica) tornano i 14,50 gg.
        assert available_residual_for_allocation(
            project.id, exclude_allocation_id=allocation.id
        ) == Decimal("14.5000")


class TestFlussoWallet:
    def test_il_flusso_elenca_origine_e_destinazione(self):
        allocate("FLOW", "3.0000", "1.0000")
        rows = wallet_flow(2026)
        assert rows[0]["destinazione"] == "ATT-FLOW"
        assert rows[0]["allocato"] == Decimal("3.0000")
        assert rows[0]["consumato"] == Decimal("1.0000")

    def test_allocazione_senza_origine_e_marcata(self):
        WalletAllocationFactory(
            wallet_year=WalletYearFactory(year=2026),
            source_project=None,
            activity=WalletActivityFactory(code="ATT-SENZA-ORIGINE"),
            allocated_days=Decimal("10.0000"),
            status=AllocationStatus.CHIUSA,
        )
        rows = wallet_flow(2026)
        assert rows[0]["origine"] == "WALLET-GENERALE"

    def test_totali_per_architetto_sommano_allocato_consumato_e_residuo(self):
        from tests.factories import PersonFactory

        assignee = PersonFactory(full_name="Architetto Demo")
        first = allocate("ASSIGNEE-1", "3.0000", "1.0000")
        second = allocate("ASSIGNEE-2", "4.0000", "1.5000")
        first.assignee = assignee
        first.save(update_fields=["assignee"])
        second.assignee = assignee
        second.save(update_fields=["assignee"])

        rows = wallet_by_assignee(2026)

        assert rows == [
            {
                "architetto_id": assignee.id,
                "architetto": "Architetto Demo",
                "allocato": Decimal("7.0000"),
                "consumato": Decimal("2.5000"),
                "residuo": Decimal("4.5000"),
            }
        ]

    def test_il_flag_origine_da_attribuire_e_automatico(self):
        allocation = WalletAllocationFactory(
            wallet_year=WalletYearFactory(year=2026),
            source_project=None,
            activity=WalletActivityFactory(code="ATT-FLAG"),
            allocated_days=Decimal("1.0000"),
        )
        allocation.refresh_from_db()
        assert allocation.requires_source_attribution is True

    def test_monte_wallet_e_voci_con_erodibilita(self):
        """Caso d'uso chiarito dall'utente:
        Progetti A, B, C, D, E, F con avanzi 0, 2, 3, 1, 0, 1 -> monte totale 7 gg.
        Nuova voce ATTIVITÀ X con 5 gg allocati -> residuo wallet 2 gg, disponibile voce 5 gg.
        Consuntivo settimanale eroso dal fornitore fino ad arrivare a 0.
        """
        closure = date(2026, 1, 10)
        # Progetti con residui: A(0), B(2), C(3), D(1), E(0), F(1)
        prj_a = ProjectFactory(
            code="PRJ-A",
            budget_days=Decimal("10.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=closure,
        )
        TimesheetEntryFactory(project=prj_a, days=Decimal("10.0000"))

        prj_b = ProjectFactory(
            code="PRJ-B",
            budget_days=Decimal("5.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=closure,
        )
        TimesheetEntryFactory(project=prj_b, days=Decimal("3.0000"))

        prj_c = ProjectFactory(
            code="PRJ-C",
            budget_days=Decimal("6.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=closure,
        )
        TimesheetEntryFactory(project=prj_c, days=Decimal("3.0000"))

        prj_d = ProjectFactory(
            code="PRJ-D",
            budget_days=Decimal("4.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=closure,
        )
        TimesheetEntryFactory(project=prj_d, days=Decimal("3.0000"))

        prj_e = ProjectFactory(
            code="PRJ-E",
            budget_days=Decimal("8.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=closure,
        )
        TimesheetEntryFactory(project=prj_e, days=Decimal("8.0000"))

        prj_f = ProjectFactory(
            code="PRJ-F",
            budget_days=Decimal("2.0000"),
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=closure,
        )
        TimesheetEntryFactory(project=prj_f, days=Decimal("1.0000"))

        # Inizialmente: monte = 7 gg, allocato = 0 gg, residuo non allocato = 7 gg
        b0 = wallet_year_balance(2026, today=date(2026, 6, 1))
        assert b0.potential_wallet_capacity == Decimal("7.0000")
        assert b0.allocated_days == Decimal("0.0000")
        assert b0.unallocated_capacity == Decimal("7.0000")

        # Censisco nuova voce ATTIVITA X con 5 gg prelevati dal monte wallet
        activity_x = WalletActivityFactory(code="ATT-X", title="ATTIVITA X")
        alloc_x = WalletAllocationFactory(
            wallet_year=WalletYearFactory(year=2026),
            source_project=None,
            activity=activity_x,
            allocated_days=Decimal("5.0000"),
        )

        b1 = wallet_year_balance(2026, today=date(2026, 6, 1))
        d1 = b1.as_dict()
        assert d1["capacita_totale_origini"] == Decimal("7.0000")
        assert d1["totale_allocato"] == Decimal("5.0000")
        assert d1["residuo_wallet_non_allocato"] == Decimal("2.0000")
        assert d1["consumato_allocazioni"] == Decimal("0.0000")
        assert d1["disponibile_su_allocazioni"] == Decimal("5.0000")

        # Il fornitore registra 2 gg consuntivati settimanalmente
        TimesheetEntryFactory(wallet_allocation=alloc_x, days=Decimal("2.0000"))

        b2 = wallet_year_balance(2026, today=date(2026, 6, 1))
        d2 = b2.as_dict()
        assert d2["capacita_totale_origini"] == Decimal("7.0000")
        assert d2["totale_allocato"] == Decimal("5.0000")
        assert d2["residuo_wallet_non_allocato"] == Decimal("2.0000")
        assert d2["consumato_allocazioni"] == Decimal("2.0000")
        assert d2["disponibile_su_allocazioni"] == Decimal("3.0000")

        # Flusso espone origine Monte Wallet (pool generico)
        flows = wallet_flow(2026, today=date(2026, 6, 1))
        flow_x = next(f for f in flows if f["id"] == alloc_x.id)
        assert flow_x["origine_titolo"] == "Monte Wallet (pool generico)"
        assert flow_x["destinazione_titolo"] == "ATTIVITA X"
        assert flow_x["residuo_allocazione"] == Decimal("3.0000")
