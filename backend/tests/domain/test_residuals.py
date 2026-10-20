"""R2 (scadenza dei residui) e R3 (residuo di progetto).

Copre i casi obbligatori del par. 11: 11.1 (progetto 2024 ancora attivo), 11.3 (chiuso il
15/11/2025) e 11.5 (residuo non allocato con allocazione a zero).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.residuals import (
    ResidualState,
    last_usable_day,
    project_balance_qs,
    residual_explanation,
    residual_validity,
    unallocated_residual,
)
from projects.models import TimesheetStatus
from tests.factories import (
    ProjectFactory,
    TimesheetEntryFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)


class TestScadenzaResidui:
    """R2 in forma pura, senza database."""

    def test_progetto_attivo_non_scade_mai(self):
        # Caso 11.1: IM24133 aperto nel 2024 e ancora attivo.
        validity = residual_validity(
            timesheet_status=TimesheetStatus.ATTIVO,
            closure_date=None,
            today=date(2026, 10, 20),
        )
        assert validity.state == ResidualState.VALIDO
        assert validity.expires_on is None
        assert validity.usable

    def test_progetto_non_avviato_non_scade(self):
        validity = residual_validity(
            timesheet_status=TimesheetStatus.NON_AVVIATO,
            closure_date=None,
            today=date(2026, 10, 20),
        )
        assert validity.state == ResidualState.VALIDO

    def test_ultimo_giorno_utile_e_fine_anno_successivo(self):
        assert last_usable_day(date(2025, 11, 15), 1) == date(2026, 12, 31)
        assert last_usable_day(date(2025, 1, 2), 1) == date(2026, 12, 31)
        assert last_usable_day(date(2025, 11, 15), 0) == date(2025, 12, 31)

    @pytest.mark.parametrize(
        ("today", "expected"),
        [
            (date(2025, 11, 16), ResidualState.VALIDO),
            (date(2026, 10, 1), ResidualState.VALIDO),
            (date(2026, 10, 2), ResidualState.IN_SCADENZA),
            (date(2026, 12, 31), ResidualState.IN_SCADENZA),
            (date(2027, 1, 1), ResidualState.SCADUTO),
            (date(2028, 3, 1), ResidualState.SCADUTO),
        ],
    )
    def test_caso_11_3_progetto_chiuso_il_15_11_2025(self, today, expected):
        """Valido al 31/12/2026, scaduto dal 01/01/2027, in scadenza al 02/10/2026."""
        validity = residual_validity(
            timesheet_status=TimesheetStatus.CHIUSO,
            closure_date=date(2025, 11, 15),
            today=today,
            years_valid_after_closure=1,
            expiring_window_days=90,
        )
        assert validity.state == expected
        assert validity.expires_on == date(2026, 12, 31)

    def test_il_31_12_2026_e_ancora_spendibile(self):
        validity = residual_validity(
            timesheet_status=TimesheetStatus.CHIUSO,
            closure_date=date(2025, 11, 15),
            today=date(2026, 12, 31),
        )
        assert validity.usable
        assert validity.days_to_expiry == 0

    def test_chiuso_senza_data_resta_da_verificare(self):
        """D-03: senza data di chiusura la scadenza non è calcolabile."""
        validity = residual_validity(
            timesheet_status=TimesheetStatus.CHIUSO,
            closure_date=None,
            today=date(2026, 10, 20),
        )
        assert validity.state == ResidualState.DA_VERIFICARE
        assert not validity.usable
        assert "senza data" in validity.reason

    def test_consuntivazione_da_verificare_non_entra_nel_disponibile(self):
        validity = residual_validity(
            timesheet_status=TimesheetStatus.DA_VERIFICARE,
            closure_date=None,
            today=date(2026, 10, 20),
        )
        assert validity.state == ResidualState.DA_VERIFICARE
        assert not validity.usable

    def test_la_finestra_di_scadenza_e_configurabile(self):
        validity = residual_validity(
            timesheet_status=TimesheetStatus.CHIUSO,
            closure_date=date(2025, 11, 15),
            today=date(2026, 6, 1),
            expiring_window_days=365,
        )
        assert validity.state == ResidualState.IN_SCADENZA

    def test_due_anni_di_validita(self):
        validity = residual_validity(
            timesheet_status=TimesheetStatus.CHIUSO,
            closure_date=date(2025, 11, 15),
            today=date(2027, 6, 1),
            years_valid_after_closure=2,
        )
        assert validity.state == ResidualState.VALIDO
        assert validity.expires_on == date(2027, 12, 31)


class TestFormulaResiduo:
    """R3 in forma pura."""

    def test_residuo_e_budget_meno_consumi_meno_allocato(self):
        assert unallocated_residual(
            Decimal("25.0000"), Decimal("10.5000"), Decimal("11.0000")
        ) == Decimal("3.5000")

    def test_caso_11_1_residuo_zero(self):
        # IM24133: budget 85, diretti 35, allocato 50 -> residuo 0.
        assert unallocated_residual(
            Decimal("85.0000"), Decimal("35.0000"), Decimal("50.0000")
        ) == Decimal("0.0000")

    def test_il_residuo_puo_essere_negativo_in_caso_di_sforamento(self):
        # IM26292: budget 17, consumato 24,8.
        assert unallocated_residual(
            Decimal("17.0000"), Decimal("24.8000"), Decimal("0.0000")
        ) == Decimal("-7.8000")

    def test_la_spiegazione_mostra_il_calcolo(self):
        text = residual_explanation(Decimal("25.0000"), Decimal("10.5000"), Decimal("11.0000"))
        assert "25,00 gg" in text
        assert "10,50 gg" in text
        assert "11,00 gg" in text
        assert "3,50 gg" in text


@pytest.mark.django_db
class TestProjectBalanceDaDatabase:
    """La vista calcolata non deve mai dipendere da numeri scritti a mano."""

    def test_caso_11_1_im24133(self):
        project = ProjectFactory(
            code="IM24133-3313-BMED-ARCH-NUOVO-PROTECTION-MODEL",
            budget_days=Decimal("85.0000"),
            start_date=date(2024, 4, 22),
            planned_end_date=None,
            timesheet_status=TimesheetStatus.ATTIVO,
        )
        TimesheetEntryFactory(project=project, days=Decimal("35.0000"))
        allocation = WalletAllocationFactory(
            source_project=project,
            activity=WalletActivityFactory(code="ATT-PROTECTION-MODEL"),
            allocated_days=Decimal("50.0000"),
        )
        TimesheetEntryFactory(wallet_allocation=allocation, days=Decimal("50.0000"))

        row = project_balance_qs().get(pk=project.pk)
        assert row.direct_consumed_days == Decimal("35.0000")
        assert row.allocated_to_wallet_days == Decimal("50.0000")
        assert row.consumed_via_wallet_days == Decimal("50.0000")
        assert row.total_consumed_days == Decimal("85.0000")
        assert row.residual_days == Decimal("0.0000")

    def test_caso_11_5_im26254_residuo_non_allocato(self):
        """Allocazione a 0 gg: il residuo resta interamente disponibile (D-09)."""
        project = ProjectFactory(
            code="IM26254-3313-BMED-ARCH-SOLUTION-DESIGN-GESTIONE-DOPPIO-CR",
            budget_days=Decimal("10.0000"),
            start_date=date(2026, 7, 1),
            planned_end_date=date(2026, 9, 30),
        )
        WalletAllocationFactory(
            source_project=project,
            activity=WalletActivityFactory(code="IM26254-ATTIVITA"),
            allocated_days=Decimal("0.0000"),
            wallet_year=WalletYearFactory(year=2026),
        )

        row = project_balance_qs().get(pk=project.pk)
        assert row.residual_days == Decimal("10.0000")
        validity = residual_validity(
            timesheet_status=row.timesheet_status,
            closure_date=row.actual_closure_date,
            today=date(2026, 10, 20),
        )
        assert validity.state == ResidualState.VALIDO

    def test_gli_storni_riducono_il_consumato(self):
        project = ProjectFactory(budget_days=Decimal("10.0000"))
        entry = TimesheetEntryFactory(project=project, days=Decimal("4.0000"))
        reversal = entry.build_reversal()
        reversal.save()

        row = project_balance_qs().get(pk=project.pk)
        assert row.direct_consumed_days == Decimal("0.0000")
        assert row.residual_days == Decimal("10.0000")

    def test_piu_progetti_non_si_contaminano_fra_join(self):
        """Il calcolo usa subquery: i join multipli non devono moltiplicare le somme."""
        first = ProjectFactory(code="IM26001-A", budget_days=Decimal("10.0000"))
        second = ProjectFactory(code="IM26002-B", budget_days=Decimal("20.0000"))
        for _ in range(3):
            TimesheetEntryFactory(project=first, days=Decimal("1.0000"))
        TimesheetEntryFactory(project=second, days=Decimal("5.0000"))
        for index in range(2):
            allocation = WalletAllocationFactory(
                source_project=first,
                activity=WalletActivityFactory(code=f"ATT-MULTI-{index}"),
                allocated_days=Decimal("2.0000"),
            )
            TimesheetEntryFactory(wallet_allocation=allocation, days=Decimal("1.0000"))

        rows = {row.code: row for row in project_balance_qs()}
        assert rows["IM26001-A"].direct_consumed_days == Decimal("3.0000")
        assert rows["IM26001-A"].allocated_to_wallet_days == Decimal("4.0000")
        assert rows["IM26001-A"].consumed_via_wallet_days == Decimal("2.0000")
        assert rows["IM26001-A"].residual_days == Decimal("3.0000")
        assert rows["IM26002-B"].residual_days == Decimal("15.0000")
