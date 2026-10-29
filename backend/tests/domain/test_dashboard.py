from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.models import AppSettings
from domain.dashboard import dashboard_summary
from projects.billing import sync_project_billing_schedule
from projects.models import BillingStatus, MilestoneStatus, TimesheetStatus
from tests.factories import (
    MilestoneFactory,
    PersonFactory,
    ProjectFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
)

pytestmark = pytest.mark.django_db


def test_dashboard_include_fatturazioni_aperte_correnti_e_arretrate_senza_mutarle():
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
    assert billings["count"] == 2
    assert billings["limit"] == 50
    assert billings["results"][1:] == [
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
    arretrata = billings["results"][0]
    assert arretrata["classificazione"] == "ARRETRATA"
    assert arretrata["data_fatturazione"] == "2026-09-10"
    assert arretrata["id"] in {str(overdue.id), str(duplicate.id)}
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


def test_dashboard_avvisa_solo_la_tranche_aperta_del_mese_corrente():
    project = ProjectFactory(
        code="BILLING-CURRENT-MONTH",
        start_date=date(2026, 10, 27),
        planned_end_date=date(2026, 12, 31),
        billing_status=BillingStatus.DA_FATTURARE,
    )
    sync_project_billing_schedule(project)

    october = dashboard_summary(today=date(2026, 10, 27), settings_obj=AppSettings.get_solo())
    assert [row["data_fatturazione"] for row in october["prossime_fatturazioni"]["results"]] == [
        "2026-10-31"
    ]

    november = dashboard_summary(today=date(2026, 11, 1), settings_obj=AppSettings.get_solo())
    assert [
        (row["data_fatturazione"], row["classificazione"])
        for row in november["prossime_fatturazioni"]["results"]
    ] == [("2026-10-31", "ARRETRATA")]

    project.billing_status = BillingStatus.PARZIALE
    project.save()
    sync_project_billing_schedule(project)
    october_after_first_invoice = dashboard_summary(
        today=date(2026, 10, 27), settings_obj=AppSettings.get_solo()
    )
    assert october_after_first_invoice["prossime_fatturazioni"]["results"] == []
    december = dashboard_summary(today=date(2026, 12, 1), settings_obj=AppSettings.get_solo())
    assert [row["data_fatturazione"] for row in december["prossime_fatturazioni"]["results"]] == [
        "2026-12-31"
    ]


def test_dashboard_tranche_finale_arretrata_fino_a_fatturazione_totale():
    project = ProjectFactory(
        start_date=date(2026, 1, 1),
        planned_end_date=date(2026, 10, 15),
        billing_status=BillingStatus.PARZIALE,
    )
    sync_project_billing_schedule(project)
    result = dashboard_summary(today=date(2026, 11, 1), settings_obj=AppSettings.get_solo())
    assert [
        (row["data_fatturazione"], row["classificazione"])
        for row in result["prossime_fatturazioni"]["results"]
    ] == [("2026-10-31", "ARRETRATA")]
    project.billing_status = BillingStatus.TOTALE
    project.save()
    sync_project_billing_schedule(project)
    assert (
        dashboard_summary(today=date(2026, 11, 1), settings_obj=AppSettings.get_solo())[
            "prossime_fatturazioni"
        ]["results"]
        == []
    )


def test_distribuzione_referenti_conta_entita_distinte_e_incluse_senza_referente():
    first = PersonFactory(full_name="Mario Rossi")
    second = PersonFactory(full_name="Anna Bianchi")
    ProjectFactory(client_owner=first)
    ProjectFactory(client_owner=first)
    ProjectFactory(client_owner=None)
    WalletActivityFactory(client_owner=first)
    WalletActivityFactory(client_owner=second)
    WalletActivityFactory(client_owner=None)
    WalletActivityFactory(client_owner=first, is_technical=True)
    rows = dashboard_summary(today=date(2026, 10, 22), settings_obj=AppSettings.get_solo())[
        "distribuzione_referenti"
    ]
    assert [(row["referente"], row["progetti"], row["attivita_wallet"]) for row in rows] == [
        ("Mario Rossi", 2, 1),
        ("Anna Bianchi", 0, 1),
        ("Senza referente", 1, 1),
    ]


def test_monte_giornate_per_referente_somma_budget_e_allocazioni_attivita():
    owner = PersonFactory(full_name="Mario Rossi")
    other = PersonFactory(full_name="Anna Bianchi")
    ProjectFactory(client_owner=owner, budget_days=Decimal("20"))
    ProjectFactory(client_owner=owner, budget_days=Decimal("5"))
    activity = WalletActivityFactory(client_owner=owner)
    WalletAllocationFactory(
        activity=activity, source_project__client_owner=other, allocated_days=Decimal("3")
    )
    WalletAllocationFactory(activity=activity, allocated_days=Decimal("2"))
    WalletAllocationFactory(activity=activity, allocated_days=Decimal("99"), is_technical=True)
    technical = WalletActivityFactory(client_owner=owner, is_technical=True)
    WalletAllocationFactory(activity=technical, allocated_days=Decimal("99"))
    rows = dashboard_summary(today=date(2026, 10, 22), settings_obj=AppSettings.get_solo())[
        "distribuzione_referenti"
    ]
    row = next(item for item in rows if item["referente_id"] == str(owner.id))
    assert row["giornate_progetti"] == "25.0000"
    assert row["giornate_wallet"] == "5.0000"
    assert row["monte_giornate"] == "30.0000"
