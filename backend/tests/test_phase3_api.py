from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from canone.models import Canone
from tests.factories import ProjectFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_canone_index_espone_solo_identificativi_e_testi_non_calcolati():
    project = ProjectFactory(code="IM-UI", title="Canone UI")
    canone = Canone.objects.create(project=project, semester="2026-S2", total_days="100")
    client = APIClient()
    client.force_authenticate(user=UserFactory())

    response = client.get("/api/v1/canoni")

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "id": str(canone.id),
                "semestre": "2026-S2",
                "progetto_codice": "IM-UI",
                "progetto_titolo": "Canone UI",
            }
        ],
        "count": 1,
    }


def test_canone_index_richiede_autenticazione():
    response = APIClient().get("/api/v1/canoni")

    assert response.status_code == 401
    assert response.json()["code"] == "session_expired"
