from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.models import AppSettings
from domain.dashboard import dashboard_summary
from projects.models import MilestoneStatus, TimesheetStatus
from tests.factories import MilestoneFactory, ProjectFactory

pytestmark = pytest.mark.django_db


def test_dashboard_include_solo_fatturazioni_aperte_del_mese_corrente_senza_mutarle():
    today = date(2026, 10, 22)
    future_project = ProjectFactory(
        code="B-FUTURE",
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 8, 31),
    )
    current_project = ProjectFactory(code="A-CURRENT")
    overdue = MilestoneFactory(
        project=current_project,
        planned_date=date(2026, 9, 10),
        actual_date=date(2026, 9, 15),
        amount_days=Decimal("2.5000"),
        status=MilestoneStatus.DA_VERIFICARE,
        move_count=1,
        moves=[{"from": "2026-09-01", "to": "2026-09-10", "reason": "Rinvio"}],
    )
    duplicate = MilestoneFactory(
        project=current_project,
        planned_date=date(2026, 9, 10),
        amount_days=Decimal("99"),
        status=MilestoneStatus.PIANIFICATA,
    )
    current = MilestoneFactory(
        project=current_project,
        planned_date=date(2026, 10, 31),
        amount_days=Decimal("3"),
        status=MilestoneStatus.SPOSTATA,
    )
    MilestoneFactory(
        project=future_project,
        planned_date=date(2026, 12, 2),
        amount_days=None,
        status=MilestoneStatus.PIANIFICATA,
    )
    MilestoneFactory(
        project=current_project,
        planned_date=date(2026, 10, 5),
        status=MilestoneStatus.FATTURATA,
    )
    MilestoneFactory(
        project=current_project,
        planned_date=date(2026, 10, 6),
        status=MilestoneStatus.ANNULLATA,
    )

    result = dashboard_summary(today=today, settings_obj=AppSettings.get_solo())

    assert result["progetti_per_stato"] == [
        {"stato": "NON_AVVIATO", "conteggio": 0},
        {"stato": "ATTIVO", "conteggio": 1},
        {"stato": "CHIUSO", "conteggio": 1},
        {"stato": "DA_VERIFICARE", "conteggio": 0},
    ]
    billings = result["prossime_fatturazioni"]
    assert billings["count"] == 1
    assert billings["limit"] == 50
    assert billings["results"] == [
        {
            "id": str(current.id),
            "progetto_id": str(current_project.id),
            "progetto_codice": "A-CURRENT",
            "data_pianificata": "2026-10-31",
            "data_fatturazione": "2026-10-31",
            "data_effettiva": None,
            "classificazione": "MESE_CORRENTE",
            "stato": "SPOSTATA",
            "numero_spostamenti": 0,
            "spostamenti": [],
        }
    ]
    assert str(overdue.id) not in {row["id"] for row in billings["results"]}
    assert str(duplicate.id) not in {row["id"] for row in billings["results"]}
    overdue.refresh_from_db()
    assert overdue.status == MilestoneStatus.DA_VERIFICARE
    assert overdue.planned_date == date(2026, 9, 10)


def test_dashboard_limita_il_payload_ma_espone_il_totale():
    project = ProjectFactory(code="LIMIT")
    for day in range(1, 4):
        MilestoneFactory(project=project, planned_date=date(2026, 10, day))

    result = dashboard_summary(
        today=date(2026, 10, 22),
        settings_obj=AppSettings.get_solo(),
        billing_limit=2,
    )

    assert result["prossime_fatturazioni"]["count"] == 3
    assert result["prossime_fatturazioni"]["limit"] == 2
    assert len(result["prossime_fatturazioni"]["results"]) == 2
