from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from canone.models import Canone
from core import roles
from projects.models import Project
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


def test_responsabile_puo_creare_un_progetto_dal_wizard():
    roles.ensure_groups()
    user = UserFactory()
    user.groups.add(Group.objects.get(name=roles.MANAGER))
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/projects",
        {
            "code": "IM-NEW",
            "title": "Progetto creato dal wizard",
            "contract_type": "AQL",
            "budget_days": "12.5000",
            "start_date": "2026-10-01",
            "planned_end_date": "2026-12-31",
        },
        format="json",
    )

    assert response.status_code == 201
    project = Project.objects.get(code="IM-NEW")
    assert str(project.budget_days) == "12.5000"
    assert response.json()["version"] == 1


def test_fornitore_non_puo_creare_un_progetto():
    roles.ensure_groups()
    user = UserFactory()
    user.groups.add(Group.objects.get(name=roles.SUPPLIER))
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/projects",
        {"code": "NO", "title": "Negato", "contract_type": "AQL", "budget_days": "1"},
        format="json",
    )

    assert response.status_code == 403


def test_command_search_trova_progetti():
    project = ProjectFactory(code="IM-SEARCH", title="Ricerca palette")
    client = APIClient()
    client.force_authenticate(user=UserFactory())

    response = client.get("/api/v1/search", {"q": "SEARCH"})

    assert response.status_code == 200
    assert response.json()["results"][0] == {
        "tipo": "progetto",
        "id": str(project.id),
        "codice": "IM-SEARCH",
        "titolo": "Ricerca palette",
        "url": f"/progetti/{project.id}",
    }


def test_command_search_non_esegue_query_con_un_solo_carattere():
    client = APIClient()
    client.force_authenticate(user=UserFactory())

    response = client.get("/api/v1/search", {"q": "I"})

    assert response.status_code == 200
    assert response.json() == {"results": []}
