from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from rest_framework.test import APIClient

from anomalies.models import Anomaly, AnomalyStatus, Scope, Severity
from core import roles
from projects.models import TimesheetStatus
from tests.factories import ProjectFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager_client() -> APIClient:
    roles.ensure_groups()
    user = User.objects.create_user("manager-rifiniture", password="password-lunga-123")
    user.groups.add(Group.objects.get(name=roles.MANAGER))
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_release_to_wallet_legacy_e_disabilitato_senza_modificare_il_progetto(manager_client):
    project = ProjectFactory(
        budget_days=Decimal("12.0000"),
        timesheet_status=TimesheetStatus.ATTIVO,
    )

    response = manager_client.post(
        f"/api/v1/projects/{project.pk}/release-to-wallet",
        {"giornate": "10.0000", "motivazione": "Richiesta BMED"},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PROJECT_WALLET_RELEASE_DEPRECATED"
    project.refresh_from_db()
    assert project.released_to_wallet_days == Decimal("0.0000")


def test_anomaly_external_ref_visibile_in_api(manager_client):
    Anomaly.objects.create(
        external_ref="AN-001",
        rule_code="SEED_MANUALE",
        severity=Severity.MEDIA,
        scope=Scope.PROGETTO,
        description="Anomalia seed",
        status=AnomalyStatus.APERTA,
        fingerprint="a" * 64,
    )

    response = manager_client.get("/api/v1/anomalies")

    assert response.status_code == 200
    assert response.json()["results"][0]["external_ref"] == "AN-001"
