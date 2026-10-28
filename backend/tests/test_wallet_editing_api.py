from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from core import roles
from core.models import AdminAuditEvent
from domain.wallet_balance import wallet_year_balance
from imports.models import ImportKind
from projects.models import ContractType, OfferStatus, TimesheetStatus
from tests.factories import (
    ImportBatchFactory,
    PersonFactory,
    ProjectFactory,
    TimesheetEntryFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)
from tests.test_roles_object_permissions import make_client_for_role
from timesheets.models import TimesheetEntry, TimesheetSource
from wallet.models import WalletAllocation, WalletSourceLot, WalletYear

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


def test_dettaglio_allocazione_leggibile_senza_wallet_edit_ma_patch_vietata():
    client, _ = make_client_for_role(roles.REFERENT)
    alloc = WalletAllocationFactory(allocated_days=Decimal("5.0000"))

    detail = client.get(f"/api/v1/wallet/allocations/{alloc.id}/")
    assert detail.status_code == 200, detail.data
    assert detail.json()["residuo_allocazione"] == "5.0000"
    assert detail.json()["stato_operativo"] == "IN_CORSO"

    mutation = client.patch(
        f"/api/v1/wallet/allocations/{alloc.id}/",
        {"expected_version": alloc.version, "notes": "vietato"},
        format="json",
    )
    assert mutation.status_code == 403, mutation.data


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


def test_chiusura_allocazione_restituisce_il_residuo_al_wallet():
    client, _ = make_client_for_role(roles.ADMIN)
    source_project = ProjectFactory(
        code="IM26-SRC-RELEASE",
        budget_days=Decimal("10.0000"),
        released_to_wallet_days=Decimal("10.0000"),
        declared_residual_year=2026,
    )
    allocation = WalletAllocationFactory(
        source_project=source_project,
        allocated_days=Decimal("5.0000"),
    )
    TimesheetEntryFactory(
        wallet_allocation=allocation,
        days=Decimal("3.0000"),
        period=date(2026, 2, 1),
    )

    before = wallet_year_balance(2026)
    assert before.unallocated_capacity == Decimal("5.0000")

    response = client.patch(
        f"/api/v1/wallet/allocations/{allocation.id}/",
        {
            "expected_version": allocation.version,
            "allocated_days": "5.0000",
            "status": "CHIUSA",
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.json()["allocated_days"] == "3.0000"
    assert response.json()["consumed_days"] == "3.0000"
    assert response.json()["available_days"] == "0.0000"
    assert response.json()["released_days"] == "2.0000"

    allocation.refresh_from_db()
    assert allocation.status == "CHIUSA"
    assert allocation.allocated_days == Decimal("3.0000")
    assert wallet_year_balance(2026).unallocated_capacity == Decimal("7.0000")


def test_allocazione_wallet_si_chiude_quando_raggiunge_le_giornate_allocate():
    allocation = WalletAllocationFactory(allocated_days=Decimal("5.0000"))

    TimesheetEntryFactory(
        wallet_allocation=allocation,
        days=Decimal("3.0000"),
        period=date(2026, 2, 1),
    )
    allocation.refresh_from_db()
    assert allocation.status == "APERTA"

    TimesheetEntryFactory(
        wallet_allocation=allocation,
        days=Decimal("2.0000"),
        period=date(2026, 3, 1),
    )
    allocation.refresh_from_db()
    assert allocation.status == "CHIUSA"


def test_stato_operativo_progetto_wallet_dipende_dalle_quote_aperte():
    client, _ = make_client_for_role(roles.ADMIN)
    closed_source = ProjectFactory(
        code="IM-WALLET-CLOSED",
        released_to_wallet_days=Decimal("5.0000"),
    )
    open_source = ProjectFactory(
        code="IM-WALLET-OPEN",
        released_to_wallet_days=Decimal("5.0000"),
    )
    WalletAllocationFactory(
        source_project=closed_source,
        allocated_days=Decimal("5.0000"),
        status="CHIUSA",
    )
    WalletAllocationFactory(
        source_project=open_source,
        allocated_days=Decimal("5.0000"),
        status="APERTA",
    )

    response = client.get("/api/v1/projects/balances")

    assert response.status_code == 200, response.data
    statuses = {row["codice"]: row["stato_operativo"] for row in response.json()["results"]}
    assert statuses[closed_source.code] == "CHIUSURA_DA_VALIDARE"
    assert statuses[open_source.code] == "WALLET"

    referent, _ = make_client_for_role(roles.REFERENT)
    denied = referent.post(
        f"/api/v1/projects/{closed_source.id}/validate-closure",
        {"expected_version": closed_source.version},
        format="json",
    )
    assert denied.status_code == 403

    supplier, supplier_user = make_client_for_role(roles.SUPPLIER)
    validated = supplier.post(
        f"/api/v1/projects/{closed_source.id}/validate-closure",
        {"expected_version": closed_source.version},
        format="json",
    )
    assert validated.status_code == 200, validated.data
    assert validated.json()["stato_operativo"] == "CHIUSO"

    closed_source.refresh_from_db()
    assert closed_source.timesheet_status == TimesheetStatus.CHIUSO
    assert closed_source.actual_closure_date == timezone.localdate()
    assert AdminAuditEvent.objects.filter(
        action="project.closure.validate",
        target_id=str(closed_source.id),
        actor=supplier_user,
    ).exists()


@pytest.mark.parametrize("role", (roles.ADMIN, roles.SUPPLIER))
def test_rettifica_consuntivi_append_only_storno_e_nuova_emissione(role):
    client, _ = make_client_for_role(role)
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


def test_rettifica_consumato_non_puo_superare_allocato():
    client, _ = make_client_for_role(roles.ADMIN)
    alloc = WalletAllocationFactory(allocated_days=Decimal("5.0000"))

    res = client.patch(
        f"/api/v1/wallet/allocations/{alloc.id}/",
        {
            "expected_version": alloc.version,
            "adjust_consumed_to": "5.5000",
        },
        format="json",
    )

    assert res.status_code == 400, res.data
    assert "non possono superare" in str(res.data)
    assert TimesheetEntry.objects.filter(wallet_allocation=alloc).count() == 0


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


def test_allocation_options_includono_residuo_scadenza_e_validita():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(
        code="OPTIONS-RESIDUAL",
        budget_days=Decimal("12.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 3, 1),
    )
    TimesheetEntryFactory(project=project, days=Decimal("2.0000"))

    response = client.get("/api/v1/wallet/allocation-options/")
    row = next(item for item in response.json()["projects"] if item["id"] == str(project.id))
    assert row["available_days"] == "10.0000"
    assert row["year"] == 2026
    assert row["validity"] in ("VALIDO", "IN_SCADENZA")
    assert row["expires_on"]
    assert row["usable"] is True


def test_create_allocazione_rifiuta_selezione_manuale_origine():
    client, user = make_client_for_role(roles.ADMIN)
    source = ProjectFactory(
        code="CREATE-SOURCE",
        budget_days=Decimal("10.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 2, 1),
    )
    activity = WalletActivityFactory(code="CREATE-ACTIVITY")
    assignee = PersonFactory(full_name="Create Assignee")
    payload = {
        "year": 2026,
        "source_project": str(source.id),
        "activity": str(activity.id),
        "assignee": str(assignee.id),
        "allocated_days": "6.0000",
        "notes": "creata da test",
    }
    response = client.post("/api/v1/allocations", payload, format="json")
    assert response.status_code == 400
    assert "FIFO" in str(response.data)
    assert not AdminAuditEvent.objects.filter(
        actor=user, action="wallet_allocation.create"
    ).exists()


def test_create_allocazione_permission_e_origine_scaduta():
    source = ProjectFactory(
        code="CREATE-EXPIRED",
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2020, 1, 1),
    )
    activity = WalletActivityFactory(code="CREATE-EXPIRED-ACT")
    assignee = PersonFactory()
    payload = {
        "year": 2020,
        "source_project": str(source.id),
        "activity": str(activity.id),
        "assignee": str(assignee.id),
        "allocated_days": "1.0000",
    }
    read_only, _ = make_client_for_role(roles.REFERENT)
    assert read_only.post("/api/v1/allocations", payload, format="json").status_code == 403
    admin, _ = make_client_for_role(roles.ADMIN)
    assert admin.post("/api/v1/allocations", payload, format="json").status_code == 400


def test_delete_allocazione_manual_empty_libera_residuo_e_audit():
    client, user = make_client_for_role(roles.ADMIN)
    source = ProjectFactory(
        code="DELETE-ALLOC-SOURCE",
        budget_days=Decimal("10.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 1, 1),
    )
    allocation = WalletAllocationFactory(source_project=source, allocated_days=Decimal("7.0000"))
    response = client.delete(
        f"/api/v1/wallet/allocations/{allocation.id}/",
        HTTP_IF_MATCH=f'W/"{allocation.id}-{allocation.version}"',
    )
    assert response.status_code == 204, response.data
    assert not WalletAllocation.objects.filter(pk=allocation.id).exists()
    assert AdminAuditEvent.objects.filter(
        action="wallet_allocation.delete", target_id=str(allocation.id), actor=user
    ).exists()
    options = client.get("/api/v1/wallet/allocation-options/").json()
    source_option = next(row for row in options["projects"] if row["id"] == str(source.id))
    assert source_option["available_days"] == "10.0000"


def test_delete_allocazione_permission_versione_import_e_ledger_append_only():
    allocation = WalletAllocationFactory()
    read_only, _ = make_client_for_role(roles.REFERENT)
    assert read_only.delete(f"/api/v1/wallet/allocations/{allocation.id}/").status_code == 403
    admin, _ = make_client_for_role(roles.ADMIN)
    assert admin.delete(f"/api/v1/wallet/allocations/{allocation.id}/").status_code == 428
    assert (
        admin.delete(
            f"/api/v1/wallet/allocations/{allocation.id}/", HTTP_IF_MATCH='W/"stale-0"'
        ).status_code
        == 409
    )

    imported = WalletAllocationFactory(import_batch=ImportBatchFactory(kind=ImportKind.SEED_JSON))
    assert (
        admin.delete(
            f"/api/v1/wallet/allocations/{imported.id}/",
            HTTP_IF_MATCH=f'W/"{imported.id}-{imported.version}"',
        ).status_code
        == 400
    )

    consumed = WalletAllocationFactory()
    original = TimesheetEntryFactory(wallet_allocation=consumed, days=Decimal("2.0000"))
    reversal = original.build_reversal(note="netto zero")
    reversal.save()
    consumed.refresh_from_db()
    response = admin.delete(
        f"/api/v1/wallet/allocations/{consumed.id}/",
        HTTP_IF_MATCH=f'W/"{consumed.id}-{consumed.version}"',
    )
    assert response.status_code == 400
    assert TimesheetEntry.objects.filter(wallet_allocation=consumed).count() == 2


def test_creazione_allocazione_monte_wallet_e_nuova_attivita():
    """Test creazione voce autonoma dal monte wallet e nuova attività creata al volo."""
    client, _ = make_client_for_role(roles.ADMIN)
    year = 2026
    architect = PersonFactory(full_name="Architetto Test")

    # Progetto con residuo di 7 gg per alimentare il monte wallet
    source = ProjectFactory(
        code="PRJ-CLOSED-7GG",
        budget_days=Decimal("10.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(year, 2, 1),
    )
    TimesheetEntryFactory(project=source, days=Decimal("3.0000"))
    wallet_year = WalletYear.objects.create(year=year)
    WalletSourceLot.objects.create(
        wallet_year=wallet_year,
        source_project=source,
        source_year=2026,
        capacity_days=Decimal("7.0000"),
        effective_date=date(year, 2, 1),
        external_ref="LOT-PRJ-CLOSED-7GG",
    )

    # 1. Tentativo di allocare 10 gg dal monte wallet (supera i 7 gg disponibili)
    payload_excess = {
        "year": year,
        "assignee": architect.id,
        "allocated_days": "10.0000",
        "new_activity_title": "ATTIVITA X OVER",
    }
    resp_excess = client.post("/api/v1/wallet/allocations", payload_excess, format="json")
    assert resp_excess.status_code == 400
    assert "allocated_days" in str(resp_excess.data)

    # 2. Creazione valida di 5 gg con creazione al volo di ATTIVITÀ X
    payload_valid = {
        "year": year,
        "assignee": architect.id,
        "allocated_days": "5.0000",
        "activity_title": "ATTIVITA X",
        "notes": "Prelievo generico dal conto wallet",
    }
    resp_valid = client.post("/api/v1/wallet/allocations", payload_valid, format="json")
    assert resp_valid.status_code == 201, resp_valid.data
    data = resp_valid.json()
    assert data["source_project"] is None
    assert data["source_project_code"] == "Monte Wallet FIFO"
    assert data["activity_code"].startswith("ACT-")
    assert data["allocated_days"] == "5.0000"
    assert data["available_source_after"] == "2.0000"

    # Verifica nel database
    allocation = WalletAllocation.objects.get(pk=data["id"])
    assert allocation.source_project is None
    assert allocation.requires_source_attribution is False
    assert allocation.activity.title == "ATTIVITA X"
    assert allocation.activity.kind == "ATTIVITA"

    # Verifica wallet_balance
    bal_resp = client.get(f"/api/v1/wallet/{year}/balance").json()
    assert bal_resp["capacita_totale_origini"] == "7.0000"
    assert bal_resp["totale_allocato"] == "5.0000"
    assert bal_resp["residuo_wallet_non_allocato"] == "2.0000"
    assert bal_resp["disponibile_su_allocazioni"] == "5.0000"

    # Verifica wallet_flow
    flow_resp = client.get(f"/api/v1/wallet/{year}/flow").json()
    row = next(r for r in flow_resp["results"] if r["id"] == str(allocation.id))
    assert row["origine_titolo"] == "Monte Wallet (pool generico)"
    assert row["destinazione_titolo"] == "ATTIVITA X"
    assert row["allocato"] == "5.0000"
    assert row["residuo_allocazione"] == "5.0000"
