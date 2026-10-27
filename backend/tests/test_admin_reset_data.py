from __future__ import annotations

from decimal import Decimal

import pytest

from core import roles
from core.models import AdminAuditEvent
from projects.models import Project
from tests.factories import (
    AnomalyFactory,
    CanoneFactory,
    CanoneSubactivityFactory,
    ImportBatchFactory,
    MilestoneFactory,
    PpmSnapshotFactory,
    PpmSnapshotRowFactory,
    ProjectFactory,
    TimesheetEntryFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)
from tests.test_roles_object_permissions import make_client_for_role
from timesheets.models import TimesheetEntry
from wallet.models import WalletAllocation, WalletFundingTranche, WalletSourceLot

pytestmark = pytest.mark.django_db


def test_admin_get_reset_preview_and_token():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(code="IM26-RESET-PREVIEW")
    TimesheetEntryFactory(project=project, days=Decimal("3.0000"))

    res = client.get("/api/v1/admin/reset-data")
    assert res.status_code == 200, res.data
    data = res.json()
    assert data["confirmation_keyword"] == "ELIMINA"
    assert "token" in data
    assert "preview" in data
    assert data["preview"]["progetti"] >= 1
    assert data["preview"]["consuntivi"] >= 1
    assert data["total_records"] >= 2


def test_ruolo_non_admin_rifiutato_da_reset():
    client, _ = make_client_for_role(roles.MANAGER)
    res = client.get("/api/v1/admin/reset-data")
    assert res.status_code == 403

    res_post = client.post("/api/v1/admin/reset-data", {"confirmation": "ELIMINA"})
    assert res_post.status_code == 403


def test_post_reset_senza_parola_chiave_esatta_restituisce_400():
    client, _ = make_client_for_role(roles.ADMIN)
    res_preview = client.get("/api/v1/admin/reset-data")
    token = res_preview.json()["token"]

    res = client.post(
        "/api/v1/admin/reset-data",
        {"confirmation": "elimina", "token": token},
        format="json",
    )
    assert res.status_code == 400
    assert "ELIMINA" in res.json().get("detail", "")


def test_post_reset_con_token_invalido_restituisce_400():
    client, _ = make_client_for_role(roles.ADMIN)
    res = client.post(
        "/api/v1/admin/reset-data",
        {"confirmation": "ELIMINA", "token": "token-falso-o-manomesso"},
        format="json",
    )
    assert res.status_code == 400


def test_post_reset_esegue_pulizia_completa_e_preserva_utenti():
    client, _ = make_client_for_role(roles.ADMIN)

    # Popola dati operativi
    year = WalletYearFactory(year=2026)
    project = ProjectFactory(code="PRJ-RESET-01")
    MilestoneFactory(project=project)
    TimesheetEntryFactory(project=project, days=Decimal("5.0000"))

    canone = CanoneFactory(project=project)
    CanoneSubactivityFactory(canone=canone)

    activity = WalletActivityFactory(code="ACT-RESET")
    alloc = WalletAllocationFactory(wallet_year=year, activity=activity, source_project=project)
    TimesheetEntryFactory(wallet_allocation=alloc, days=Decimal("2.0000"))

    snap = PpmSnapshotFactory()
    PpmSnapshotRowFactory(snapshot=snap, project=project)
    AnomalyFactory(project=project)
    ImportBatchFactory()

    # Prendi token
    res_preview = client.get("/api/v1/admin/reset-data")
    assert res_preview.status_code == 200
    token = res_preview.json()["token"]

    # Esegui reset
    res = client.post(
        "/api/v1/admin/reset-data",
        {"confirmation": "ELIMINA", "token": token},
        format="json",
    )
    assert res.status_code == 200, res.data
    data = res.json()
    assert data["status"] == "success"
    assert "deleted" in data

    # Verifiche che le tabelle operative siano vuote
    assert Project.objects.count() == 0
    assert TimesheetEntry.objects.count() == 0
    assert WalletAllocation.objects.count() == 0

    # Verifica che l'audit sia stato creato
    assert AdminAuditEvent.objects.filter(action="data.reset").exists()


def test_post_reset_gestisce_storni_e_finanziamenti_wallet_v4():
    client, _ = make_client_for_role(roles.ADMIN)
    year = WalletYearFactory(year=2026)
    project = ProjectFactory(code="PRJ-RESET-V4")
    original = TimesheetEntryFactory(project=project, days=Decimal("5.0000"))
    reversal = original.build_reversal("Storno seed v4")
    reversal.save()
    activity = WalletActivityFactory(code="ACT-RESET-V4")
    allocation = WalletAllocationFactory(
        wallet_year=year,
        activity=activity,
        source_project=project,
    )
    source_lot = WalletSourceLot.objects.create(
        wallet_year=year,
        source_project=project,
        source_year=2026,
        capacity_days=Decimal("5.0000"),
        external_ref="LOT-RESET-V4",
    )
    WalletFundingTranche.objects.create(
        allocation=allocation,
        source_lot=source_lot,
        sequence=1,
        initial_reserved_days=Decimal("1.0000"),
        committed_days=Decimal("1.0000"),
        consumed_days=Decimal("0.0000"),
        external_ref="FUND-RESET-V4",
    )

    preview = client.get("/api/v1/admin/reset-data")
    assert preview.status_code == 200
    assert preview.json()["preview"]["tranche_wallet"] == 1
    assert preview.json()["preview"]["lotti_wallet"] == 1

    response = client.post(
        "/api/v1/admin/reset-data",
        {"confirmation": "ELIMINA", "token": preview.json()["token"]},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.json()["deleted"]["consuntivi"] == 2
    assert response.json()["deleted"]["tranche_wallet"] >= 1
    assert response.json()["deleted"]["lotti_wallet"] >= 1
    assert Project.objects.count() == 0
