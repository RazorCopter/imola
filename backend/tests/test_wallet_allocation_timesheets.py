"""Consuntivi riga per riga su un'allocazione wallet.

Prima esisteva solo la rettifica sintetica del totale consumato: utile come correzione
amministrativa, inservibile per registrare il lavoro giornata per giornata.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core import roles
from projects.models import TimesheetStatus
from tests.factories import (
    PersonFactory,
    ProjectFactory,
    TimesheetEntryFactory,
    WalletActivityFactory,
)
from tests.test_roles_object_permissions import make_client_for_role
from timesheets.models import TimesheetEntry, TimesheetSource
from wallet.models import AllocationStatus, WalletAllocation
from wallet.services import ensure_source_lot

pytestmark = pytest.mark.django_db


def make_allocation(client, days: str = "6.0000", capacity: str = "10.0000"):
    """Progetto chiuso -> lotto -> allocazione creata dall'API come fa l'interfaccia."""
    project = ProjectFactory(
        code="PRJ-WALLET-TS",
        budget_days=Decimal(capacity),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 3, 31),
    )
    ensure_source_lot(project)
    activity = WalletActivityFactory(code="ACT-WALLET-TS")
    assignee = PersonFactory(full_name="Gabriele Cataldo")
    response = client.post(
        "/api/v1/wallet/allocations",
        {
            "year": 2026,
            "assignee": assignee.id,
            "activity": str(activity.id),
            "allocated_days": days,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return project, WalletAllocation.objects.get(pk=response.json()["id"])


def test_consuntivo_erode_le_giornate_riservate_e_le_tranche_fifo():
    client, user = make_client_for_role(roles.ADMIN)
    project, allocation = make_allocation(client)

    response = client.post(
        f"/api/v1/wallet/allocations/{allocation.id}/timesheets",
        {"data": "2026-04-10", "giornate": "2.5000", "descrizione": "Analisi"},
        format="json",
    )

    assert response.status_code == 201, response.data
    payload = response.json()
    assert payload["consumed_days"] == "2.5000"
    assert payload["available_days"] == "3.5000"
    assert payload["consuntivi"][0]["descrizione"] == "Analisi"
    assert payload["consuntivi"][0]["utente_id"] == user.pk

    entry = TimesheetEntry.objects.get(wallet_allocation=allocation)
    assert entry.days == Decimal("2.5000")
    assert entry.source == TimesheetSource.MANUALE
    # Il consumo scala la tranche FIFO, non solo l'allocazione.
    tranche = allocation.funding_tranches.get()
    assert tranche.consumed_days == Decimal("2.5000")
    assert tranche.source_lot.source_project == project


def test_il_consuntivo_non_puo_superare_le_giornate_riservate():
    client, _ = make_client_for_role(roles.ADMIN)
    _, allocation = make_allocation(client, days="4.0000")

    response = client.post(
        f"/api/v1/wallet/allocations/{allocation.id}/timesheets",
        {"data": "2026-04-10", "giornate": "4.5000", "descrizione": "Troppo"},
        format="json",
    )

    assert response.status_code == 400
    assert "giornate" in response.json()
    assert not TimesheetEntry.objects.filter(wallet_allocation=allocation).exists()


def test_dati_mancanti_o_non_validi_vengono_rifiutati():
    client, _ = make_client_for_role(roles.ADMIN)
    _, allocation = make_allocation(client)
    url = f"/api/v1/wallet/allocations/{allocation.id}/timesheets"

    assert (
        client.post(url, {"data": "non-una-data", "giornate": "1"}, format="json").status_code
        == 400
    )
    assert (
        client.post(url, {"data": "2026-04-10", "giornate": "0"}, format="json").status_code == 400
    )
    assert (
        client.post(
            url, {"data": "2026-04-10", "giornate": "1", "descrizione": " "}, format="json"
        ).status_code
        == 400
    )
    assert not TimesheetEntry.objects.filter(wallet_allocation=allocation).exists()


def test_rettifica_e_annullo_passano_sempre_da_uno_storno():
    client, _ = make_client_for_role(roles.ADMIN)
    _, allocation = make_allocation(client)
    created = client.post(
        f"/api/v1/wallet/allocations/{allocation.id}/timesheets",
        {"data": "2026-04-10", "giornate": "2.0000", "descrizione": "Prima stesura"},
        format="json",
    )
    entry_id = created.json()["consuntivi"][0]["id"]

    rectified = client.patch(
        f"/api/v1/wallet/allocations/{allocation.id}/timesheets/{entry_id}",
        {"data": "2026-04-11", "giornate": "3.0000", "descrizione": "Corretto"},
        format="json",
    )
    assert rectified.status_code == 200, rectified.data
    assert rectified.json()["consumed_days"] == "3.0000"
    # Storno piu nuova riga: la riga originale resta nel ledger.
    assert TimesheetEntry.objects.filter(wallet_allocation=allocation).count() == 3
    assert TimesheetEntry.objects.filter(
        wallet_allocation=allocation, source=TimesheetSource.STORNO
    ).exists()

    new_id = rectified.json()["consuntivi"][0]["id"]
    deleted = client.delete(
        f"/api/v1/wallet/allocations/{allocation.id}/timesheets/{new_id}", format="json"
    )
    assert deleted.status_code == 200, deleted.data
    assert deleted.json()["consumed_days"] == "0.0000"
    assert deleted.json()["consuntivi"] == []


def test_chiudere_la_voce_restituisce_al_wallet_le_giornate_non_usate():
    client, _ = make_client_for_role(roles.ADMIN)
    _, allocation = make_allocation(client, days="6.0000")
    client.post(
        f"/api/v1/wallet/allocations/{allocation.id}/timesheets",
        {"data": "2026-04-10", "giornate": "2.0000", "descrizione": "Analisi"},
        format="json",
    )
    allocation.refresh_from_db()

    closed = client.patch(
        f"/api/v1/wallet/allocations/{allocation.id}",
        {"status": AllocationStatus.CHIUSA, "expected_version": allocation.version},
        format="json",
    )

    assert closed.status_code == 200, closed.data
    assert closed.json()["released_days"] == "4.0000"
    allocation.refresh_from_db()
    assert allocation.status == AllocationStatus.CHIUSA
    assert allocation.allocated_days == Decimal("2.0000")

    # Le 4 gg tornano prelevabili dal monte wallet.
    balance = client.get("/api/v1/wallet/2026/balance").json()
    assert balance["totale_allocato"] == "2.0000"
    assert balance["residuo_wallet_non_allocato"] == "8.0000"

    # Su una voce chiusa non si consuntiva piu.
    refused = client.post(
        f"/api/v1/wallet/allocations/{allocation.id}/timesheets",
        {"data": "2026-04-12", "giornate": "1.0000", "descrizione": "Tardivo"},
        format="json",
    )
    assert refused.status_code == 409


def test_il_fornitore_consuntiva_il_referente_no():
    admin, _ = make_client_for_role(roles.ADMIN)
    _, allocation = make_allocation(admin)
    url = f"/api/v1/wallet/allocations/{allocation.id}/timesheets"
    payload = {"data": "2026-04-10", "giornate": "1.0000", "descrizione": "Attivita"}

    referent, _ = make_client_for_role(roles.REFERENT)
    assert referent.post(url, payload, format="json").status_code == 403

    supplier, supplier_user = make_client_for_role(roles.SUPPLIER)
    created = supplier.post(url, payload, format="json")
    assert created.status_code == 201, created.data
    assert TimesheetEntry.objects.get(wallet_allocation=allocation).created_by == supplier_user


def test_admin_intesta_il_consuntivo_wallet_a_un_altro_utente():
    from django.contrib.auth.models import Group

    from tests.factories import UserFactory

    client, admin_user = make_client_for_role(roles.ADMIN)
    _, allocation = make_allocation(client)
    roles.ensure_groups()
    imola = UserFactory(username="imola", first_name="Mario", last_name="Rossi")
    imola.groups.add(Group.objects.get(name=roles.SUPPLIER))

    created = client.post(
        f"/api/v1/wallet/allocations/{allocation.id}/timesheets",
        {
            "data": "2026-04-10",
            "giornate": "1.0000",
            "descrizione": "Svolta da Imola",
            "utente": imola.pk,
        },
        format="json",
    )

    assert created.status_code == 201, created.data
    entry = TimesheetEntry.objects.get(wallet_allocation=allocation)
    assert entry.created_by == imola
    assert entry.updated_by == admin_user


def test_i_consuntivi_restano_legati_alla_loro_allocazione():
    client, _ = make_client_for_role(roles.ADMIN)
    _, allocation = make_allocation(client)
    altra = TimesheetEntryFactory(days=Decimal("1.0000"))

    response = client.patch(
        f"/api/v1/wallet/allocations/{allocation.id}/timesheets/{altra.id}",
        {"giornate": "2.0000"},
        format="json",
    )

    assert response.status_code == 404
