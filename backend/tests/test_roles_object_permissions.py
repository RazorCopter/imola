from __future__ import annotations

import io

import pytest
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from rest_framework.test import APIClient

from core import capabilities, roles
from tests.factories import (
    PersonFactory,
    ProjectFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def make_client_for_role(role_name: str | None, email: str = "") -> tuple[APIClient, User]:
    roles.ensure_groups()
    user = UserFactory(email=email)
    if role_name == roles.ADMIN:
        user.is_superuser = True
        user.save()
    elif role_name:
        user.groups.add(Group.objects.get(name=role_name))
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.parametrize("role_name", roles.ALL_ROLES)
def test_tutti_i_ruoli_possono_consultare_le_pagine_api(role_name):
    client, _ = make_client_for_role(role_name)
    ProjectFactory()

    for path in (
        "/api/v1/projects/balances",
        "/api/v1/wallet/2026/balance",
        "/api/v1/reconciliation/latest",
        "/api/v1/anomalies",
        "/api/v1/review-queue",
    ):
        assert client.get(path).status_code == 200, path


@pytest.mark.parametrize("role_name", (roles.REFERENT,))
def test_ruoli_read_only_non_possono_eseguire_mutation_ledger(role_name):
    client, _ = make_client_for_role(role_name)
    project = ProjectFactory(notes="Iniziale")

    create_response = client.post(
        "/api/v1/projects",
        {"code": "VIETATO", "title": "Non creato", "contract_type": "AQL"},
        format="json",
    )
    review_response = client.post(
        f"/api/v1/projects/{project.id}/confirm-review",
        {"timesheet_status": "CHIUSO", "actual_closure_date": "2026-06-30"},
        format="json",
    )

    assert create_response.status_code == 403
    assert review_response.status_code == 403


def test_fornitore_puo_creare_progetti_ma_non_modificare_ledger_registrato():
    client, _ = make_client_for_role(roles.SUPPLIER)
    project = ProjectFactory(notes="Iniziale")

    create_response = client.post(
        "/api/v1/projects",
        {
            "code": "SUPPLIER-NEW",
            "title": "Creato",
            "contract_type": "AQL",
            "budget_days": "0.0000",
        },
        format="json",
    )
    review_response = client.post(
        f"/api/v1/projects/{project.id}/confirm-review",
        {"timesheet_status": "CHIUSO", "actual_closure_date": "2026-06-30"},
        format="json",
    )

    assert create_response.status_code == 201
    assert review_response.status_code == 403


def test_default_capability_fornitore_esclude_ledger_e_applicazione_import():
    client, user = make_client_for_role(roles.SUPPLIER)

    assert capabilities.CREATE_PROJECTS in capabilities.capabilities_for(user)
    assert capabilities.CREATE_TIMESHEETS in capabilities.capabilities_for(user)
    assert capabilities.ADJUST_ACCOUNTING not in capabilities.capabilities_for(user)
    assert capabilities.APPLY_IMPORTS not in capabilities.capabilities_for(user)
    assert client.get("/api/v1/auth/session").json()["capabilities"] == sorted(
        capabilities.ROLE_DEFAULTS[roles.SUPPLIER]
    )


def test_project_balances_espone_permission_object_level_per_referente():
    owner = PersonFactory(full_name="Marco Rossi", email="marco.rossi@example.com")
    own_project = ProjectFactory(code="IM-PERM-OWN", client_owner=owner)
    other_project = ProjectFactory(code="IM-PERM-OTHER", client_owner=None)
    client, _ = make_client_for_role(roles.REFERENT, email="marco.rossi@example.com")

    response = client.get("/api/v1/projects/balances")

    assert response.status_code == 200
    permissions_by_id = {
        str(row["id"]): row["permissions"]["annotate"] for row in response.json()["results"]
    }
    assert permissions_by_id[str(own_project.id)] is True
    assert permissions_by_id[str(other_project.id)] is False


def test_admin_puo_modificare_qualsiasi_progetto():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(notes="Iniziale")
    res = client.patch(
        f"/api/v1/projects/{project.id}",
        {"notes": "Aggiornato da admin", "expected_version": 1},
        format="json",
    )
    assert res.status_code == 200
    assert res.json()["notes"] == "Aggiornato da admin"


def test_responsabile_puo_modificare_qualsiasi_progetto():
    client, _ = make_client_for_role(roles.MANAGER)
    project = ProjectFactory(notes="Iniziale")
    res = client.patch(
        f"/api/v1/projects/{project.id}",
        {"notes": "Aggiornato da manager", "expected_version": 1},
        format="json",
    )
    assert res.status_code == 200
    assert res.json()["notes"] == "Aggiornato da manager"


def test_referente_puo_modificare_solo_i_propri_progetti():
    owner = PersonFactory(full_name="Marco Rossi", email="marco.rossi@example.com")
    other_owner = PersonFactory(full_name="Luigi Verdi", email="luigi.verdi@example.com")
    my_project = ProjectFactory(client_owner=owner, notes="Iniziale mio")
    other_project = ProjectFactory(client_owner=other_owner, notes="Iniziale altro")

    client, _ = make_client_for_role(roles.REFERENT, email="marco.rossi@example.com")

    # Modifica del proprio progetto
    res_my = client.patch(
        f"/api/v1/projects/{my_project.id}",
        {
            "notes": "Note aggiornate dal referente",
            "planned_end_date": "2026-12-31",
            "expected_version": 1,
        },
        format="json",
    )
    assert res_my.status_code == 200
    assert res_my.json()["notes"] == "Note aggiornate dal referente"

    # Tentativo di modifica su progetto altrui -> 403 Forbidden
    res_other = client.patch(
        f"/api/v1/projects/{other_project.id}",
        {"notes": "Tentativo non autorizzato", "expected_version": 1},
        format="json",
    )
    assert res_other.status_code == 403


def test_patch_progetto_risponde_409_su_versione_cambiata():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(notes="Iniziale")
    project.notes = "Modifica concorrente"
    project.save()

    response = client.patch(
        f"/api/v1/projects/{project.id}",
        {"notes": "Sovrascrittura", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "risorsa-obsoleta"
    project.refresh_from_db()
    assert project.notes == "Modifica concorrente"


def test_fornitore_in_sola_lettura_su_progetti():
    client, _ = make_client_for_role(roles.SUPPLIER)
    project = ProjectFactory(notes="Iniziale")
    assert client.get(f"/api/v1/projects/{project.id}").status_code == 200
    res_patch = client.patch(f"/api/v1/projects/{project.id}", {"notes": "Negato"}, format="json")
    assert res_patch.status_code == 403


def test_referente_non_puo_caricare_ppm():
    client, _ = make_client_for_role(roles.REFERENT)
    uploaded = SimpleUploadedFile("ppm.xlsx", b"contenuto", content_type="application/octet-stream")

    response = client.post("/api/v1/imports/ppm", {"file": uploaded}, format="multipart")

    assert response.status_code == 403


def test_fornitore_upload_ppm_resta_in_dry_run_anche_se_richiede_apply():
    client, _ = make_client_for_role(roles.SUPPLIER)
    project = ProjectFactory(code="IM-PPM-PERM", budget_days=20)
    wb = Workbook()
    ws = wb.active
    ws.append(["Progetti Test"])
    ws.append(["Estratto il 16/10/2026 alle 11:05:18"])
    ws.append([])
    ws.append(["Progetto", "gg tot"])
    ws.append([project.code, 15])
    ws.append(["Totale", 15])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    uploaded = SimpleUploadedFile(
        "ppm_test.xlsx",
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response = client.post(
        "/api/v1/imports/ppm", {"file": uploaded, "apply": "true"}, format="multipart"
    )

    assert response.status_code == 200
    assert response.json()["entry_create"] == 0
    assert response.json()["batch_id"] is None


def test_audit_history_endpoint_restituisce_modifiche():
    client, _ = make_client_for_role(roles.MANAGER)
    project = ProjectFactory(notes="Versione 1")
    project.notes = "Versione 2"
    project.save()

    response = client.get(f"/api/v1/audit/project/{project.id}")
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) >= 2
    assert any("notes: Versione 1 -> Versione 2" in m for r in results for m in r["modifiche"])


def test_fornitore_gestisce_operativita_senza_privilegi_amministrativi():
    client, user = make_client_for_role(roles.SUPPLIER)
    effective = capabilities.capabilities_for(user)
    assert {
        capabilities.CREATE_PROJECTS,
        capabilities.CREATE_TIMESHEETS,
        capabilities.EDIT_TIMESHEETS,
        capabilities.MANAGE_CANONE,
        capabilities.EDIT_WALLET,
    } <= effective
    assert not (effective & capabilities.RESERVED_CAPABILITIES)
    for path in ("/api/v1/admin/users", "/api/v1/admin/roles/capabilities"):
        assert client.get(path).status_code == 403
    assert (
        client.patch(
            "/api/v1/settings", {"costo_giornata_uomo": "999.00"}, format="json"
        ).status_code
        == 403
    )


def test_fornitore_rettifica_consuntivo_manuale_di_un_altro_utente():
    from tests.factories import TimesheetEntryFactory

    client, _ = make_client_for_role(roles.SUPPLIER)
    project = ProjectFactory(budget_days="10.0000")
    entry = TimesheetEntryFactory(
        project=project, days="2.0000", source="MANUALE", created_by=UserFactory()
    )
    response = client.patch(
        f"/api/v1/projects/{project.id}/ledger/{entry.id}",
        {"giornate": "1.0000", "descrizione": "Rettifica fornitore"},
        format="json",
    )
    assert response.status_code == 200, response.data
    assert entry.reversals.count() == 1
