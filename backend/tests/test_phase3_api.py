from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from canone.models import Canone, CanoneSubactivity
from core import roles
from projects.models import Project
from tests.factories import ProjectFactory, TimesheetEntryFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_canone_index_espone_default_dell_ultimo_semestre_movimentato_per_data():
    older_project = ProjectFactory(code="IM-OLD", title="Organico precedente")
    older = Canone.objects.create(project=older_project, semester="2026-S1", total_days="100")
    older_subactivity = CanoneSubactivity.objects.create(canone=older, title="Attività precedente")
    TimesheetEntryFactory(
        canone_subactivity=older_subactivity,
        period=date(2026, 6, 1),
        days=Decimal("1.0000"),
    )
    recent_project = ProjectFactory(code="IM-UI", title="Organico UI")
    recent = Canone.objects.create(project=recent_project, semester="2026-S2", total_days="100")
    recent_subactivity = CanoneSubactivity.objects.create(canone=recent, title="Attività recente")
    TimesheetEntryFactory(
        canone_subactivity=recent_subactivity,
        period=date(2026, 5, 1),
        days=Decimal("1.0000"),
    )
    client = APIClient()
    client.force_authenticate(user=UserFactory())

    response = client.get("/api/v1/canoni")

    assert response.status_code == 200
    body = response.json()
    assert body["default_canone_id"] == str(older.id)
    assert body["count"] == 2
    assert body["results"] == [
        {
            "id": str(recent.id),
            "semestre": "2026-S2",
            "progetto_codice": "IM-UI",
            "progetto_titolo": "Organico UI",
            "ultimo_movimento": "2026-05-01",
        },
        {
            "id": str(older.id),
            "semestre": "2026-S1",
            "progetto_codice": "IM-OLD",
            "progetto_titolo": "Organico precedente",
            "ultimo_movimento": "2026-06-01",
        },
    ]


def test_canone_index_senza_movimenti_usa_il_periodo_piu_recente():
    older = Canone.objects.create(
        project=ProjectFactory(code="IM-S1"), semester="2026-S1", total_days="100"
    )
    recent = Canone.objects.create(
        project=ProjectFactory(code="IM-S2"), semester="2026-S2", total_days="100"
    )
    client = APIClient()
    client.force_authenticate(user=UserFactory())

    body = client.get("/api/v1/canoni").json()

    assert body["default_canone_id"] == str(recent.id)
    assert (
        next(row for row in body["results"] if row["id"] == str(older.id))["ultimo_movimento"]
        is None
    )


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
