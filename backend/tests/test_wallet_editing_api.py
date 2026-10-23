from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core import roles
from projects.models import ContractType, OfferStatus, TimesheetStatus
from tests.factories import (
    PersonFactory,
    ProjectFactory,
    TimesheetEntryFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)
from tests.test_roles_object_permissions import make_client_for_role
from timesheets.models import TimesheetEntry, TimesheetSource

pytestmark = pytest.mark.django_db


def test_admin_patch_allocazione_wallet():
    client, _ = make_client_for_role(roles.ADMIN)
    year = WalletYearFactory(year=2026)
    architect1 = PersonFactory(full_name="Architetto Uno")
    architect2 = PersonFactory(full_name="Architetto Due")
    activity = WalletActivityFactory(code="ACT-EDIT-1", title="Attività Wallet Test")

    # Progetto chiuso con residuo spendibile
    source_project = ProjectFactory(
        code="IM26-SRC-1",
        budget_days=Decimal("20.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 1, 15),
        contract_type=ContractType.AQL,
        offer_status=OfferStatus.ACCETTATA,
    )
    # Consuntivo diretto di 5 gg -> residuo spendibile 15 gg
    TimesheetEntryFactory(project=source_project, days=Decimal("5.0000"), period=date(2026, 1, 1))

    alloc = WalletAllocationFactory(
        wallet_year=year,
        source_project=source_project,
        activity=activity,
        assignee=architect1,
        allocated_days=Decimal("8.0000"),
        notes="Note iniziali",
    )

    payload = {
        "expected_version": alloc.version,
        "days_allocated": "12.0000",
        "assignee": str(architect2.id),
        "notes": "Note aggiornate via PATCH",
    }

    res = client.patch(f"/api/v1/wallet/allocations/{alloc.id}/", payload, format="json")
    assert res.status_code == 200, res.data
    data = res.json()
    assert data["allocated_days"] == "12.0000"
    assert data["assignee"] == str(architect2.id)
    assert data["architetto"] == architect2.full_name
    assert data["notes"] == "Note aggiornate via PATCH"
    assert data["version"] == 2
    assert "ETag" in res.headers

    alloc.refresh_from_db()
    assert alloc.allocated_days == Decimal("12.0000")
    assert alloc.assignee == architect2
    assert alloc.notes == "Note aggiornate via PATCH"


def test_patch_allocazione_senza_versione_restituisce_428():
    client, _ = make_client_for_role(roles.ADMIN)
    alloc = WalletAllocationFactory(allocated_days=Decimal("5.0000"))

    res = client.patch(
        f"/api/v1/wallet/allocations/{alloc.id}/",
        {"allocated_days": "6.0000"},
        format="json",
    )
    assert res.status_code == 428, res.data


def test_patch_allocazione_versione_obsoleta_restituisce_409():
    client, _ = make_client_for_role(roles.ADMIN)
    alloc = WalletAllocationFactory(allocated_days=Decimal("5.0000"))

    res = client.patch(
        f"/api/v1/wallet/allocations/{alloc.id}/",
        {"expected_version": 999, "allocated_days": "6.0000"},
        format="json",
    )
    assert res.status_code == 409, res.data
    assert res.json().get("code") == "risorsa-obsoleta"


def test_patch_allocazione_superamento_residuo_restituisce_400_insufficient_residual():
    client, _ = make_client_for_role(roles.ADMIN)
    source_project = ProjectFactory(
        code="IM26-SRC-CAP",
        budget_days=Decimal("10.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 1, 15),
    )
    TimesheetEntryFactory(project=source_project, days=Decimal("6.0000"), period=date(2026, 1, 1))
    # Residuo spendibile: 4 gg

    alloc = WalletAllocationFactory(
        source_project=source_project,
        allocated_days=Decimal("2.0000"),
    )

    # Tentiamo di portare l'allocazione a 6 gg (supera i 4 gg disponibili)
    res = client.patch(
        f"/api/v1/wallet/allocations/{alloc.id}/",
        {"expected_version": alloc.version, "allocated_days": "6.0000"},
        format="json",
    )
    assert res.status_code == 400, res.data
    assert res.json().get("code") == "residuo-insufficiente"


def test_patch_allocazione_inferiore_a_consuntivato_restituisce_400():
    client, _ = make_client_for_role(roles.ADMIN)
    source_project = ProjectFactory(
        code="IM26-SRC-CAP",
        budget_days=Decimal("20.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 1, 15),
        contract_type=ContractType.AQL,
        offer_status=OfferStatus.ACCETTATA,
    )
    alloc = WalletAllocationFactory(
        source_project=source_project,
        allocated_days=Decimal("10.0000"),
    )
    TimesheetEntryFactory(wallet_allocation=alloc, days=Decimal("6.0000"), period=date(2026, 2, 1))

    # Tentativo di ridurre a 4 gg senza rettificare i consuntivi
    res = client.patch(
        f"/api/v1/wallet/allocations/{alloc.id}/",
        {"expected_version": alloc.version, "allocated_days": "4.0000"},
        format="json",
    )
    assert res.status_code == 400, res.data
    body = res.json()
    has_field_err = any(err.get("campo") == "allocated_days" for err in body.get("errors", []))
    assert has_field_err or "inferiori a quelle" in str(body)


def test_rettifica_consuntivi_append_only_storno_e_nuova_emissione():
    client, _ = make_client_for_role(roles.ADMIN)
    alloc = WalletAllocationFactory(allocated_days=Decimal("10.0000"))
    entry = TimesheetEntryFactory(
        wallet_allocation=alloc,
        days=Decimal("5.0000"),
        period=date(2026, 2, 1),
        source=TimesheetSource.MANUALE,
        note="Consuntivo iniziale",
    )
    original_id = entry.id

    payload = {
        "expected_version": alloc.version,
        "adjust_timesheet": {
            "reversal_entry_id": str(original_id),
            "new_days": "3.5000",
            "new_period": "2026-02-01",
            "new_note": "Rettifica a 3.5 gg",
        },
        "reversal_note": "Storno per errata imputazione",
    }

    res = client.patch(f"/api/v1/wallet/allocations/{alloc.id}/", payload, format="json")
    assert res.status_code == 200, res.data
    data = res.json()
    assert data["consumed_days"] == "3.5000"
    assert data["available_days"] == "6.5000"

    # Verifichiamo la regola append-only nel database:
    # 1. La riga originale esiste ancora e non è stata toccata
    original_entry = TimesheetEntry.objects.get(pk=original_id)
    assert original_entry.days == Decimal("5.0000")

    # 2. Esiste una riga di storno con source STORNO e reverses = original
    reversal = TimesheetEntry.objects.get(reverses=original_entry)
    assert reversal.days == Decimal("-5.0000")
    assert reversal.source == TimesheetSource.STORNO
    assert reversal.note == "Storno per errata imputazione"

    # 3. Esiste la nuova registrazione con 3.5 gg
    new_entry = TimesheetEntry.objects.exclude(pk__in=[original_id, reversal.id]).get(
        wallet_allocation=alloc
    )
    assert new_entry.days == Decimal("3.5000")
    assert new_entry.source == TimesheetSource.MANUALE
    assert new_entry.note == "Rettifica a 3.5 gg"


def test_rettifica_consuntivi_richiede_capability_accounting_adjust():
    # Referente BMED non ha la capability accounting.adjust
    client, _ = make_client_for_role(roles.REFERENT)
    alloc = WalletAllocationFactory(allocated_days=Decimal("10.0000"))
    entry = TimesheetEntryFactory(
        wallet_allocation=alloc, days=Decimal("5.0000"), period=date(2026, 2, 1)
    )

    payload = {
        "expected_version": alloc.version,
        "adjust_timesheet": {
            "reversal_entry_id": str(entry.id),
            "new_days": "2.0000",
        },
    }

    res = client.patch(f"/api/v1/wallet/allocations/{alloc.id}/", payload, format="json")
    assert res.status_code == 403, res.data


def test_allocation_options_view_include_architects():
    client, _ = make_client_for_role(roles.ADMIN)
    PersonFactory(full_name="Architetto Selezione")

    res = client.get("/api/v1/wallet/allocation-options/")
    assert res.status_code == 200, res.data
    data = res.json()
    assert "assignees" in data
    assert "architects" in data
    names = [row["name"] for row in data["architects"]]
    assert "Architetto Selezione" in names
