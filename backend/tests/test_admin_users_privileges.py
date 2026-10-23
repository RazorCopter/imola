from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, User
from rest_framework.test import APIClient

from core import capabilities, roles
from core.models import AdminAuditEvent
from projects.models import Project
from tests.factories import ProjectFactory

pytestmark = pytest.mark.django_db


def admin_client() -> tuple[APIClient, User]:
    user = User.objects.create_superuser(
        username="admin-test", email="admin@example.test", password="Admin-test-123!"
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


def create_payload(**overrides):
    payload = {
        "username": "nuovo-utente",
        "first_name": "Nome",
        "last_name": "Cognome",
        "email": "utente@example.test",
        "password": "Password-test-123!",
        "roles": [roles.SUPPLIER],
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def test_crud_password_non_esposta_e_audit_senza_password():
    client, _ = admin_client()
    response = client.post("/api/v1/admin/users", create_payload(), format="json")
    assert response.status_code == 201
    assert "password" not in response.data
    user_id = response.data["id"]

    listing = client.get("/api/v1/admin/users")
    assert listing.status_code == 200
    row = next(item for item in listing.data["results"] if item["id"] == user_id)
    assert row["first_name"] == "Nome"
    assert "password" not in row

    updated = client.patch(
        f"/api/v1/admin/users/{user_id}",
        {"email": "modificata@example.test", "roles": [roles.REFERENT]},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["roles"] == [roles.REFERENT]

    password = client.post(
        f"/api/v1/admin/users/{user_id}/password",
        {"password": "Password-nuova-456!"},
        format="json",
    )
    assert password.status_code == 200
    assert "password" not in password.data
    assert User.objects.get(pk=user_id).check_password("Password-nuova-456!")
    assert "password" not in str(list(AdminAuditEvent.objects.values("details"))).lower()

    deleted = client.delete(f"/api/v1/admin/users/{user_id}")
    assert deleted.status_code == 204
    assert not User.objects.filter(pk=user_id).exists()


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (create_payload(username="admin-test"), "username"),
        (create_payload(email="non-valida"), "email"),
    ],
)
def test_creazione_rifiuta_username_duplicato_ed_email_non_valida(payload, field):
    client, _ = admin_client()
    response = client.post("/api/v1/admin/users", payload, format="json")
    assert response.status_code == 400
    assert any(error["campo"] == field for error in response.data["errors"])


def test_rbac_users_manage_server_side():
    roles.ensure_groups()
    user = User.objects.create_user("fornitore-test", password="Password-test-123!")
    user.groups.add(Group.objects.get(name=roles.SUPPLIER))
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.post("/api/v1/admin/users", create_payload(), format="json").status_code == 403


def test_self_disable_delete_e_ultimo_admin_sono_vietati():
    client, admin = admin_client()
    assert (
        client.patch(
            f"/api/v1/admin/users/{admin.pk}", {"is_active": False}, format="json"
        ).status_code
        == 409
    )
    assert client.delete(f"/api/v1/admin/users/{admin.pk}").status_code == 409
    assert (
        client.patch(f"/api/v1/admin/users/{admin.pk}", {"roles": []}, format="json").status_code
        == 200
    )
    assert admin.is_superuser  # Il superuser resta Admin anche senza gruppo.


def test_ultimo_admin_di_gruppo_non_puo_perdere_privilegi():
    roles.ensure_groups()
    admin = User.objects.create_user("admin-gruppo", password="Password-test-123!")
    admin.groups.add(Group.objects.get(name=roles.ADMIN))
    client = APIClient()
    client.force_authenticate(user=admin)
    response = client.patch(
        f"/api/v1/admin/users/{admin.pk}", {"roles": [roles.MANAGER]}, format="json"
    )
    assert response.status_code == 409


def test_eliminazione_con_riferimenti_propone_disattivazione():
    client, _ = admin_client()
    response = client.post("/api/v1/admin/users", create_payload(), format="json")
    user = User.objects.get(pk=response.data["id"])
    project: Project = ProjectFactory(created_by=user)
    assert project.created_by_id == user.pk
    deleted = client.delete(f"/api/v1/admin/users/{user.pk}")
    assert deleted.status_code == 409
    assert "disattiv" in deleted.data["detail"].lower()


def test_override_immediato_sessione_e_permission_e_riservate():
    client, _ = admin_client()
    roles.ensure_groups()
    supplier = User.objects.create_user("supplier-override", password="Password-test-123!")
    supplier.groups.add(Group.objects.get(name=roles.SUPPLIER))
    supplier_client = APIClient()
    supplier_client.force_authenticate(user=supplier)

    denied = supplier_client.post("/api/v1/projects", {}, format="json")
    assert denied.status_code != 403  # default Fornitore: projects.create

    changed = client.put(
        "/api/v1/admin/roles/capabilities",
        {"role": roles.SUPPLIER, "capabilities": [capabilities.EXPORT_DATA]},
        format="json",
    )
    assert changed.status_code == 200
    assert supplier_client.post("/api/v1/projects", {}, format="json").status_code == 403
    session = supplier_client.get("/api/v1/auth/session")
    assert capabilities.CREATE_PROJECTS not in session.data["capabilities"]

    reserved = client.put(
        "/api/v1/admin/roles/capabilities",
        {"role": roles.SUPPLIER, "capabilities": [capabilities.MANAGE_USERS]},
        format="json",
    )
    assert reserved.status_code == 400
    admin_change = client.put(
        "/api/v1/admin/roles/capabilities",
        {"role": roles.ADMIN, "capabilities": []},
        format="json",
    )
    assert admin_change.status_code == 409
