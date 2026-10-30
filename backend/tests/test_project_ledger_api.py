from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core import roles
from tests.factories import (
    ProjectFactory,
    TimesheetEntryFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)
from tests.test_roles_object_permissions import make_client_for_role
from timesheets.models import TimesheetEntry, TimesheetSource

pytestmark = pytest.mark.django_db


def test_fornitore_consuntiva_progetto_e_vede_utente_descrizione_e_saldo():
    client, user = make_client_for_role(roles.SUPPLIER)
    project = ProjectFactory(code="PRJ-LEDGER", budget_days=Decimal("10.0000"))

    response = client.post(
        f"/api/v1/projects/{project.id}/ledger",
        {
            "giornate": "2.5000",
            "data": "2026-10-15",
            "descrizione": "Analisi architetturale",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    entry = TimesheetEntry.objects.get(project=project)
    assert entry.days == Decimal("2.5000")
    assert entry.period.isoformat() == "2026-10-15"
    assert entry.note == "Analisi architetturale"
    assert entry.source == TimesheetSource.MANUALE
    assert entry.created_by == user

    ledger = client.get(f"/api/v1/projects/{project.id}/ledger")
    assert ledger.status_code == 200
    assert ledger.json()["consuntivi"][0] == {
        "id": str(entry.id),
        "data": "2026-10-15",
        "giornate": "2.5000",
        "descrizione": "Analisi architetturale",
        "utente": user.username,
        "utente_id": user.pk,
        "origine": "MANUALE",
    }
    balances = client.get("/api/v1/projects/balances").json()["results"]
    row = next(item for item in balances if item["id"] == str(project.id))
    assert row["consuntivi_diretti"] == "2.5000"
    assert row["consumato_totale"] == "2.5000"
    assert row["residuo"] == "7.5000"


def test_admin_modifica_consuntivo_con_storno_e_nuova_riga():
    admin_client, _admin = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(code="PRJ-EDIT", budget_days=Decimal("10.0000"))
    entry = TimesheetEntryFactory(
        project=project,
        period=date(2026, 10, 27),
        days=Decimal("2.0000"),
        source=TimesheetSource.MANUALE,
        note="Voce errata",
    )

    response = admin_client.patch(
        f"/api/v1/projects/{project.id}/ledger/{entry.id}",
        {"data": "2026-10-28", "giornate": "1.5000", "descrizione": "Voce corretta"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert TimesheetEntry.objects.filter(reverses=entry, days=Decimal("-2.0000")).exists()
    replacement = TimesheetEntry.objects.get(pk=response.json()["id"])
    assert replacement.period.isoformat() == "2026-10-28"
    assert replacement.days == Decimal("1.5000")
    ledger = admin_client.get(f"/api/v1/projects/{project.id}/ledger").json()
    assert [row["descrizione"] for row in ledger["consuntivi"]] == ["Voce corretta"]


def test_admin_elimina_consuntivo_tramite_storno_e_non_admin_riceve_403():
    admin_client, _admin = make_client_for_role(roles.ADMIN)
    manager_client, _manager = make_client_for_role(roles.MANAGER)
    project = ProjectFactory(code="PRJ-DELETE", budget_days=Decimal("10.0000"))
    entry = TimesheetEntryFactory(
        project=project,
        days=Decimal("2.0000"),
        source=TimesheetSource.MANUALE,
    )

    forbidden = manager_client.delete(f"/api/v1/projects/{project.id}/ledger/{entry.id}")
    assert forbidden.status_code == 403
    response = admin_client.delete(f"/api/v1/projects/{project.id}/ledger/{entry.id}")
    assert response.status_code == 204
    assert TimesheetEntry.objects.filter(reverses=entry, days=Decimal("-2.0000")).exists()
    assert admin_client.get(f"/api/v1/projects/{project.id}/ledger").json()["consuntivi"] == []


def test_ledger_progetto_espone_attivita_wallet_figlie_e_rimanente_allocato():
    client, _user = make_client_for_role(roles.MANAGER)
    project = ProjectFactory(code="PRJ-WALLET", budget_days=Decimal("10.0000"))
    allocation = WalletAllocationFactory(
        wallet_year=WalletYearFactory(year=2026),
        source_project=project,
        activity=WalletActivityFactory(code="ACT-FIGLIA"),
        allocated_days=Decimal("3.0000"),
    )
    second_allocation = WalletAllocationFactory(
        wallet_year=allocation.wallet_year,
        source_project=project,
        activity=WalletActivityFactory(code="ACT-FIGLIA-2"),
        allocated_days=Decimal("2.0000"),
    )
    TimesheetEntryFactory(wallet_allocation=allocation, days=Decimal("1.0000"))
    TimesheetEntryFactory(wallet_allocation=second_allocation, days=Decimal("1.0000"))

    ledger = client.get(f"/api/v1/projects/{project.id}/ledger")

    assert ledger.status_code == 200
    assert ledger.json()["wallet"][0]["id"] == str(allocation.id)
    assert ledger.json()["wallet"][0]["allocato"] == "3.0000"
    assert ledger.json()["wallet"][0]["consumato"] == "1.0000"
    assert ledger.json()["wallet"][0]["rimanente"] == "2.0000"
    balances = client.get("/api/v1/projects/balances").json()["results"]
    row = next(item for item in balances if item["id"] == str(project.id))
    assert row["rimanente_allocato_wallet"] == "3.0000"
