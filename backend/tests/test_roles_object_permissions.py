from __future__ import annotations

import io

import pytest
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from rest_framework.test import APIClient

from core import roles
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


def test_admin_puo_modificare_qualsiasi_progetto():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(notes="Iniziale")
    res = client.patch(
        f"/api/v1/projects/{project.id}", {"notes": "Aggiornato da admin"}, format="json"
    )
    assert res.status_code == 200
    assert res.json()["notes"] == "Aggiornato da admin"


def test_responsabile_puo_modificare_qualsiasi_progetto():
    client, _ = make_client_for_role(roles.MANAGER)
    project = ProjectFactory(notes="Iniziale")
    res = client.patch(
        f"/api/v1/projects/{project.id}", {"notes": "Aggiornato da manager"}, format="json"
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
        {"notes": "Note aggiornate dal referente", "planned_end_date": "2026-12-31"},
        format="json",
    )
    assert res_my.status_code == 200
    assert res_my.json()["notes"] == "Note aggiornate dal referente"

    # Tentativo di modifica su progetto altrui -> 403 Forbidden
    res_other = client.patch(
        f"/api/v1/projects/{other_project.id}",
        {"notes": "Tentativo non autorizzato"},
        format="json",
    )
    assert res_other.status_code == 403


def test_fornitore_in_sola_lettura_su_progetti():
    client, _ = make_client_for_role(roles.SUPPLIER)
    project = ProjectFactory(notes="Iniziale")
    assert client.get(f"/api/v1/projects/{project.id}").status_code == 200
    res_patch = client.patch(f"/api/v1/projects/{project.id}", {"notes": "Negato"}, format="json")
    assert res_patch.status_code == 403


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
