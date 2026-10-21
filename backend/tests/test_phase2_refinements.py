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


def test_release_to_wallet_richiede_motivazione_e_non_supera_residuo(manager_client):
    project = ProjectFactory(
        budget_days=Decimal("12.0000"),
        timesheet_status=TimesheetStatus.ATTIVO,
    )
    url = f"/api/v1/projects/{project.pk}/release-to-wallet"

    missing_reason = manager_client.post(url, {"giornate": "2.0000"}, format="json")
    assert missing_reason.status_code == 400
    assert "motivazione" in missing_reason.json()

    too_many = manager_client.post(
        url, {"giornate": "12.0001", "motivazione": "Richiesta BMED"}, format="json"
    )
    assert too_many.status_code == 400

    response = manager_client.post(
        url, {"giornate": "10.0000", "motivazione": "Richiesta BMED"}, format="json"
    )
    assert response.status_code == 200
    project.refresh_from_db()
    assert project.released_to_wallet_days == Decimal("10.0000")
    history = project.history.latest()
    assert history.released_to_wallet_days == Decimal("10.0000")
    assert history.history_change_reason == "Richiesta BMED"


def test_release_to_wallet_rifiuta_progetto_non_attivo(manager_client):
    project = ProjectFactory(timesheet_status=TimesheetStatus.NON_AVVIATO)
    response = manager_client.post(
        f"/api/v1/projects/{project.pk}/release-to-wallet",
        {"giornate": "1.0000", "motivazione": "Non ammesso"},
        format="json",
    )
    assert response.status_code == 400


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
