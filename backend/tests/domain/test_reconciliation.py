"""R6 — riconciliazione con l'ultimo snapshot PPM.

Casi obbligatori: 11.9 (IM25138 entro tolleranza) e 11.1 (IM24133 con delta -1,5 gg).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from domain.reconciliation import reconcile, reconciliation_summary, unmatched_ppm_rows
from ppm.models import SnapshotKind, normalize_project_code
from tests.factories import (
    PpmSnapshotFactory,
    PpmSnapshotRowFactory,
    ProjectFactory,
    TimesheetEntryFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)

pytestmark = pytest.mark.django_db


def aware(year, month, day, hour=11, minute=5):
    """Datetime con fuso Europe/Rome, come le date di estrazione degli snapshot."""
    return timezone.make_aware(datetime(year, month, day, hour, minute))  # noqa: DTZ001


class TestNormalizzazioneCodici:
    def test_ignora_il_segmento_bmed_e_le_maiuscole(self):
        assert normalize_project_code("IM25138-3313-BMED-ARCH-SOLUTION") == normalize_project_code(
            "im25138-3313-arch-solution"
        )

    def test_ignora_spazi_e_underscore(self):
        assert normalize_project_code("IM25138 3313_ARCH") == "IM251383313ARCH"


class TestRiconciliazione:
    def test_caso_11_9_delta_entro_tolleranza(self):
        """Interno 5,25 + 3,44 = 8,69 contro PPM 8,6875 -> delta 0,0025, esito OK."""
        project = ProjectFactory(
            code="IM25138-3313-BMED-ARCH-SOLUTION-DESIGN-ACCESSO-DIRETTO-FASE-2",
            budget_days=Decimal("10.0000"),
        )
        TimesheetEntryFactory(project=project, days=Decimal("5.2500"))
        allocation = WalletAllocationFactory(
            source_project=project,
            activity=WalletActivityFactory(code="ATT-ACCESSO-DIRETTO"),
            allocated_days=Decimal("3.4400"),
            wallet_year=WalletYearFactory(year=2026),
        )
        TimesheetEntryFactory(wallet_allocation=allocation, days=Decimal("3.4400"))
        snapshot = PpmSnapshotFactory(extracted_at=aware(2026, 10, 16))
        PpmSnapshotRowFactory(
            snapshot=snapshot,
            project=project,
            project_code=project.code,
            planned_days=Decimal("10.0000"),
            residual_days=Decimal("1.3125"),
            total_days=Decimal("8.6875"),
        )

        row = next(r for r in reconcile() if r.project_code == project.code)
        assert row.internal_days == Decimal("8.6900")
        assert row.ppm_days == Decimal("8.6875")
        assert row.delta == Decimal("0.0025")
        assert row.within_tolerance
        assert row.outcome == "OK"

    def test_caso_11_1_delta_negativo_fuori_tolleranza(self):
        """IM24133: interno 85, PPM 86,5 -> delta -1,5 gg."""
        project = ProjectFactory(
            code="IM24133-3313-BMED-ARCH-NUOVO-PROTECTION-MODEL",
            budget_days=Decimal("85.0000"),
            planned_end_date=None,
        )
        TimesheetEntryFactory(project=project, days=Decimal("35.0000"))
        allocation = WalletAllocationFactory(
            source_project=project,
            activity=WalletActivityFactory(code="ATT-PROTECTION"),
            allocated_days=Decimal("50.0000"),
            wallet_year=WalletYearFactory(year=2026),
        )
        TimesheetEntryFactory(wallet_allocation=allocation, days=Decimal("50.0000"))
        PpmSnapshotRowFactory(
            snapshot=PpmSnapshotFactory(extracted_at=aware(2026, 10, 16)),
            project=project,
            project_code=project.code,
            planned_days=Decimal("85.0000"),
            residual_days=Decimal("-1.5000"),
            total_days=Decimal("86.5000"),
        )

        row = next(r for r in reconcile() if r.project_code == project.code)
        assert row.internal_days == Decimal("85.0000")
        assert row.delta == Decimal("-1.5000")
        assert not row.within_tolerance
        assert row.outcome == "KO"
        assert "1,50 gg" in row.suggested_action

    def test_progetto_assente_dallo_snapshot(self):
        """Caso 11.2: IM25379 non compare nell'estratto wallet."""
        project = ProjectFactory(
            code="IM25379-3313-BMED-ARCH-ONBOARDING", budget_days=Decimal("22")
        )
        TimesheetEntryFactory(project=project, days=Decimal("12.6300"))
        PpmSnapshotFactory(extracted_at=aware(2026, 10, 16))

        row = next(r for r in reconcile() if r.project_code == project.code)
        assert row.missing_in_ppm
        assert row.outcome == "ASSENTE_IN_PPM"
        assert row.ppm_days is None
        assert "non compare" in row.suggested_action

    def test_vince_lo_snapshot_piu_recente(self):
        project = ProjectFactory(code="IM26-SNAP", budget_days=Decimal("10.0000"))
        TimesheetEntryFactory(project=project, days=Decimal("5.0000"))
        PpmSnapshotRowFactory(
            snapshot=PpmSnapshotFactory(extracted_at=aware(2026, 9, 1)),
            project=project,
            project_code=project.code,
            total_days=Decimal("3.0000"),
        )
        PpmSnapshotRowFactory(
            snapshot=PpmSnapshotFactory(extracted_at=aware(2026, 10, 16)),
            project=project,
            project_code=project.code,
            total_days=Decimal("5.0000"),
        )

        row = next(r for r in reconcile() if r.project_code == project.code)
        assert row.ppm_days == Decimal("5.0000")
        assert row.delta == Decimal("0.0000")

    def test_filtra_per_tipo_di_snapshot(self):
        project = ProjectFactory(code="IM26-KIND", budget_days=Decimal("10.0000"))
        TimesheetEntryFactory(project=project, days=Decimal("4.0000"))
        PpmSnapshotRowFactory(
            snapshot=PpmSnapshotFactory(
                kind=SnapshotKind.PPM_PROGETTI, extracted_at=aware(2026, 10, 16)
            ),
            project=project,
            project_code=project.code,
            total_days=Decimal("9.0000"),
        )
        rows = {r.project_code: r for r in reconcile(kinds=(SnapshotKind.PPM_WALLET,))}
        assert rows[project.code].missing_in_ppm

    def test_la_spiegazione_mostra_il_calcolo(self):
        project = ProjectFactory(code="IM26-SPIEGA", budget_days=Decimal("10.0000"))
        TimesheetEntryFactory(project=project, days=Decimal("4.0000"))
        PpmSnapshotRowFactory(
            snapshot=PpmSnapshotFactory(extracted_at=aware(2026, 10, 16)),
            project=project,
            project_code=project.code,
            total_days=Decimal("4.5000"),
        )
        row = next(r for r in reconcile() if r.project_code == project.code)
        assert "4,00 gg" in row.explanation
        assert "4,50 gg" in row.explanation


class TestRiepilogo:
    def test_conta_ok_ko_e_assenti(self):
        ok_project = ProjectFactory(code="IM26-OK", budget_days=Decimal("10.0000"))
        TimesheetEntryFactory(project=ok_project, days=Decimal("4.0000"))
        ko_project = ProjectFactory(code="IM26-KO", budget_days=Decimal("10.0000"))
        TimesheetEntryFactory(project=ko_project, days=Decimal("4.0000"))
        absent = ProjectFactory(code="IM26-ASSENTE", budget_days=Decimal("10.0000"))
        TimesheetEntryFactory(project=absent, days=Decimal("1.0000"))

        snapshot = PpmSnapshotFactory(extracted_at=aware(2026, 10, 16))
        PpmSnapshotRowFactory(
            snapshot=snapshot,
            project=ok_project,
            project_code=ok_project.code,
            total_days=Decimal("4.0000"),
        )
        PpmSnapshotRowFactory(
            snapshot=snapshot,
            project=ko_project,
            project_code=ko_project.code,
            total_days=Decimal("6.0000"),
        )

        summary = reconciliation_summary()
        assert summary["ok"] == 1
        assert summary["ko"] == 1
        assert summary["assenti_in_ppm"] == 1
        assert summary["delta_massimo"] == Decimal("2.0000")
        # La percentuale di allineamento la calcola il backend, non il client (D-15).
        assert summary["percentuale_allineati"] == Decimal("33.3333")  # 1 OK su 3 righe
        assert summary["snapshot_estratto_il"] == snapshot.extracted_at


class TestRighePpmNonRiconosciute:
    def test_le_righe_senza_progetto_finiscono_in_revisione(self):
        snapshot = PpmSnapshotFactory(extracted_at=aware(2026, 10, 16))
        PpmSnapshotRowFactory(
            snapshot=snapshot,
            project=None,
            project_code="IM99999-SCONOSCIUTO",
            unmatched_reason="Nessun progetto con questo codice.",
        )
        rows = unmatched_ppm_rows()
        assert [row.project_code for row in rows] == ["IM99999-SCONOSCIUTO"]

    def test_nessuno_snapshot_nessuna_riga(self):
        assert unmatched_ppm_rows().count() == 0
