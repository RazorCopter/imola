from __future__ import annotations

from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from canone.models import Canone, CanonePeriodicity, CanoneSubactivity
from core import capabilities, roles
from core.models import AdminAuditEvent, RoleCapabilityOverride
from tests.factories import CanoneFactory, ProjectFactory, TimesheetEntryFactory, UserFactory

pytestmark = pytest.mark.django_db


def client_for(role: str | None = None):
    user = UserFactory()
    if role:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_migrazione_canone_manage_usa_ruoli_canonici_e_preserva_override_esistenti():
    migration = import_module("core.migrations.0003_canone_manage_capability")
    RoleCapabilityOverride.objects.all().delete()
    existing = RoleCapabilityOverride.objects.create(
        role=roles.REFERENT,
        capability=capabilities.EXPORT_DATA,
        enabled=False,
    )

    migration.add_canone_manage(apps, None)

    assert set(
        RoleCapabilityOverride.objects.filter(
            capability=capabilities.MANAGE_CANONE,
            enabled=True,
        ).values_list("role", flat=True)
    ) == {roles.ADMIN, roles.MANAGER}
    existing.refresh_from_db()
    assert existing.enabled is False


def test_lista_aggregata_filtri_e_dettaglio():
    canone = CanoneFactory(semester="2026-S2", total_days=Decimal("10"))
    sub = CanoneSubactivity.objects.create(
        canone=canone, title="Analisi", office="EA", reserved_days=Decimal("5")
    )
    TimesheetEntryFactory(canone_subactivity=sub, days=Decimal("3"))

    response = client_for().get(
        "/api/v1/canoni?management=1&semester=2026-S2&state=IN_CORSO&search=Analisi"
    )
    assert response.status_code == 200
    # La ricerca riguarda i dati identificativi del canone, non il titolo sotto-attività.
    assert response.json()["count"] == 0
    response = client_for().get(f"/api/v1/canoni/{canone.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"]["consuntivato"] == "3.0000"
    assert body["subactivities"][0]["consuntivato"] == "3.0000"
    assert body["reserved_days"] == "5.0000"
    assert body["available_days"] == "5.0000"


def test_crud_lock_permission_audit_e_delete_sicura():
    project = ProjectFactory(code="CAN-CRUD")
    manager = client_for(roles.MANAGER)
    created = manager.post(
        "/api/v1/canoni",
        {"project_id": str(project.id), "semester": "2027-S1", "total_days": "20"},
        format="json",
    )
    assert created.status_code == 201
    canone_id = created.json()["id"]
    assert AdminAuditEvent.objects.filter(action="canone.create", target_id=canone_id).exists()

    assert client_for().patch(f"/api/v1/canoni/{canone_id}", {}, format="json").status_code == 403
    assert (
        manager.patch(
            f"/api/v1/canoni/{canone_id}", {"total_days": "21"}, format="json"
        ).status_code
        == 428
    )
    updated = manager.patch(
        f"/api/v1/canoni/{canone_id}",
        {"total_days": "21", "expected_version": created.json()["version"]},
        format="json",
    )
    assert updated.status_code == 200
    stale = manager.patch(
        f"/api/v1/canoni/{canone_id}",
        {"total_days": "22", "expected_version": created.json()["version"]},
        format="json",
    )
    assert stale.status_code == 409

    sub = manager.post(
        f"/api/v1/canoni/{canone_id}/subactivities",
        {"title": "Sottoattività manuale", "office": "SA", "reserved_days": "5"},
        format="json",
    )
    assert sub.status_code == 201
    row = sub.json()["subactivities"][0]
    TimesheetEntryFactory(canone_subactivity_id=row["id"], days=Decimal("1"))
    blocked = manager.delete(
        f"/api/v1/canoni/{canone_id}/subactivities/{row['id']}",
        {"expected_version": row["version"]},
        format="json",
    )
    assert blocked.status_code == 400
    assert blocked.json()["code"] == "canone-delete-bloccata"
    assert Canone.objects.filter(pk=canone_id).exists()


def test_canone_trimestrale_e_riserva_attivita_non_superano_il_monte():
    project = ProjectFactory(code="CAN-Q")
    manager = client_for(roles.MANAGER)
    created = manager.post(
        "/api/v1/canoni",
        {
            "project_id": str(project.id),
            "semester": "2027-Q2",
            "periodicity": CanonePeriodicity.QUARTERLY,
            "total_days": "20",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.json()["start_date"] == "2027-04-01"
    assert created.json()["end_date"] == "2027-06-30"
    canone_id = created.json()["id"]
    first = manager.post(
        f"/api/v1/canoni/{canone_id}/subactivities",
        {"title": "Disegno enterprise", "office": "EA", "reserved_days": "12"},
        format="json",
    )
    assert first.status_code == 201, first.data
    overflow = manager.post(
        f"/api/v1/canoni/{canone_id}/subactivities",
        {"title": "Disegno solution", "office": "SA", "reserved_days": "9"},
        format="json",
    )
    assert overflow.status_code == 400
    assert "reserved_days" in str(overflow.data)
