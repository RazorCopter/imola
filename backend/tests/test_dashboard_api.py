from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from tests.factories import MilestoneFactory, ProjectFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_dashboard_richiede_autenticazione():
    response = APIClient().get("/api/v1/dashboard")

    assert response.status_code in (401, 403)


def test_dashboard_espone_solo_il_mese_corrente_con_un_contratto_stabile():
    project = ProjectFactory(code="DASH-API", title="Dashboard API")
    current = MilestoneFactory(
        project=project, planned_date=date(2026, 10, 10), amount_days="4.2500"
    )
    MilestoneFactory(project=project, planned_date=date(2026, 9, 30))
    MilestoneFactory(project=project, planned_date=date(2026, 11, 1))
    client = APIClient()
    client.force_authenticate(user=UserFactory())

    with patch("api.domain_views.timezone.localdate", return_value=date(2026, 10, 22)):
        response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["generato_il"] == "2026-10-22"
    assert set(body) == {
        "generato_il",
        "progetti_per_stato",
        "wallet",
        "prossime_fatturazioni",
    }
    assert body["wallet"] == {
        "anno": 2026,
        "allocato": "0.0000",
        "consumato": "0.0000",
        "disponibile": "0.0000",
    }
    assert body["prossime_fatturazioni"]["count"] == 1
    assert body["prossime_fatturazioni"]["results"][0] == {
        "id": str(current.id),
        "progetto_id": str(project.id),
        "progetto_codice": "DASH-API",
        "data_pianificata": "2026-10-10",
        "data_fatturazione": "2026-10-10",
        "data_effettiva": None,
        "classificazione": "MESE_CORRENTE",
        "stato": "PIANIFICATA",
        "numero_spostamenti": 0,
        "spostamenti": [],
    }
