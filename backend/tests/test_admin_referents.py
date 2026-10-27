from __future__ import annotations

import pytest

from core import roles
from directory.models import OrganizationKind, Person
from tests.factories import ProjectFactory
from tests.test_roles_object_permissions import make_client_for_role

pytestmark = pytest.mark.django_db


def test_admin_gestisce_referenti_bmed_e_imola_senza_perdere_lo_storico():
    client, _admin = make_client_for_role(roles.ADMIN)
    created = client.post(
        "/api/v1/admin/referents",
        {
            "full_name": "Mario Bianchi",
            "email": "mario.bianchi@example.com",
            "organization_kind": OrganizationKind.CLIENT,
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    person = Person.objects.get(pk=created.json()["id"])
    project = ProjectFactory(client_owner=person)

    updated = client.patch(
        f"/api/v1/admin/referents/{person.id}",
        {"full_name": "Mario Bianchi Senior"},
        format="json",
    )
    assert updated.status_code == 200, updated.data
    assert updated.json()["project_count"] == 1

    deactivated = client.delete(f"/api/v1/admin/referents/{person.id}")
    assert deactivated.status_code == 200
    person.refresh_from_db()
    project.refresh_from_db()
    assert person.is_active is False
    assert project.client_owner == person
    options = client.get("/api/v1/projects/options").json()
    assert str(person.id) not in {str(row["id"]) for row in options["people"]}

    reactivated = client.patch(
        f"/api/v1/admin/referents/{person.id}", {"is_active": True}, format="json"
    )
    assert reactivated.status_code == 200
    listing = client.get("/api/v1/admin/referents")
    assert listing.status_code == 200
    assert listing.json()["results"][0]["full_name"] == "Mario Bianchi Senior"


def test_referenti_richiedono_permesso_gestione_utenti_e_nome_univoco():
    admin, _ = make_client_for_role(roles.ADMIN)
    payload = {
        "full_name": "Giulia Verdi",
        "organization_kind": OrganizationKind.SUPPLIER,
    }
    assert admin.post("/api/v1/admin/referents", payload, format="json").status_code == 201
    duplicate = admin.post("/api/v1/admin/referents", payload, format="json")
    assert duplicate.status_code == 400

    referent, _ = make_client_for_role(roles.REFERENT)
    assert referent.get("/api/v1/admin/referents").status_code == 403
    assert referent.post("/api/v1/admin/referents", payload, format="json").status_code == 403
