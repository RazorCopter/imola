from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from canone.models import Canone, CanoneSubactivity
from core import roles
from core.models import AdminAuditEvent, AppSettings
from tests.factories import (
    PersonFactory,
    ProjectFactory,
    SupplierOrganizationFactory,
    TimesheetEntryFactory,
    UserFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
)

pytestmark = pytest.mark.django_db


def authenticated(role: str = roles.MANAGER):
    user = UserFactory()
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


def test_settings_default_get_patch_permission_validation_and_audit():
    manager, _ = authenticated()
    response = manager.get("/api/v1/settings")
    assert response.status_code == 200
    assert response.json()["costo_giornata_uomo"] == "0.00"
    assert (
        manager.patch(
            "/api/v1/settings",
            {"costo_giornata_uomo": "100.00", "expected_version": response.json()["version"]},
            format="json",
        ).status_code
        == 403
    )

    admin, user = authenticated(roles.ADMIN)
    response = admin.get("/api/v1/settings")
    updated = admin.patch(
        "/api/v1/settings",
        {"costo_giornata_uomo": "123.45", "expected_version": response.json()["version"]},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.json()["costo_giornata_uomo"] == "123.45"
    audit = AdminAuditEvent.objects.get(action="settings.daily_person_cost.update")
    assert audit.actor == user
    assert audit.details == {"old": "0.00", "new": "123.45"}

    invalid = admin.patch(
        "/api/v1/settings",
        {"costo_giornata_uomo": "-1", "expected_version": updated.json()["version"]},
        format="json",
    )
    assert invalid.status_code == 400
    assert AppSettings.get_solo().daily_person_cost == Decimal("123.45")


def test_cost_analysis_all_sources_reversal_missing_relations_and_filters():
    settings = AppSettings.get_solo()
    settings.daily_person_cost = Decimal("100.25")
    settings.save()
    supplier = SupplierOrganizationFactory(code="SUP-COST", name="Fornitore Uno")
    owner = PersonFactory(organization=supplier)
    project = ProjectFactory(code="COST-P", title="Costo progetto", supplier_owner=owner)
    original = TimesheetEntryFactory(project=project, period=date(2026, 1, 1), days="2.0000")
    TimesheetEntryFactory(
        project=project,
        period=date(2026, 1, 1),
        days="-0.5000",
        reverses=original,
        source="STORNO",
    )
    canone = Canone.objects.create(project=project, semester="2026-S1", total_days="10")
    subactivity = CanoneSubactivity.objects.create(canone=canone, title="Canone")
    TimesheetEntryFactory(
        project=None, canone_subactivity=subactivity, period=date(2026, 2, 1), days="1.0000"
    )
    activity = WalletActivityFactory(project=None, supplier_owner=None, code="NO-REL")
    allocation = WalletAllocationFactory(activity=activity)
    TimesheetEntryFactory(
        project=None, wallet_allocation=allocation, period=date(2026, 3, 1), days="0.5000"
    )

    client, _ = authenticated()
    response = client.get("/api/v1/cost-analysis?from=2026-01-01&to=2026-03-31")
    assert response.status_code == 200
    body = response.json()
    assert body["kpi"] == {
        "total_days": "3.0000",
        "total_cost": "300.75",
        "daily_person_cost": "100.25",
    }
    assert {row["source"]: row["days"] for row in body["by_source"]} == {
        "PROJECT": "1.5000",
        "CANONE": "1.0000",
        "WALLET": "0.5000",
    }
    assert any(row["label"] == "Senza progetto" for row in body["by_project"])
    assert any(row["label"] == "Senza fornitore" for row in body["by_supplier"])
    assert client.get("/api/v1/cost-analysis?from=2026-04-01&to=2026-01-01").status_code == 400
    assert APIClient().get("/api/v1/cost-analysis").status_code in (401, 403)
