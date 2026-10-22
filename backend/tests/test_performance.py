from __future__ import annotations

import time

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from core import roles
from tests.factories import ProjectFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_lista_500_progetti_sotto_300_ms():
    roles.ensure_groups()
    user = UserFactory()
    user.groups.add(Group.objects.get(name=roles.MANAGER))
    ProjectFactory.create_batch(500)
    client = APIClient()
    client.force_authenticate(user=user)

    start = time.perf_counter()
    response = client.get("/api/v1/projects")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert response.status_code == 200
    assert response.json()["count"] == 500
    print(f"PROJECT_LIST_500_MS={elapsed_ms:.2f}")
    assert elapsed_ms < 300
