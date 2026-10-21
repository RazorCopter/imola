"""Configurazione condivisa dei test."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings

REPO_DIR = Path(__file__).resolve().parent.parent
SEED_FILE = getattr(
    settings,
    "SEED_FILE",
    Path(os.environ.get("SEED_FILE", "/app/data/seed/seed_imola_2026-10-16.json")),
)
_default_schema = (
    "/seed_schema_v1.json"
    if Path("/seed_schema_v1.json").exists()
    else str(REPO_DIR / "seed_schema_v1.json")
)
SEED_SCHEMA = Path(os.environ.get("SEED_SCHEMA", _default_schema))


def pytest_collection_modifyitems(config, items) -> None:
    """Salta i test marcati `seedfile` quando il seed reale non è presente.

    Il seed contiene dati reali del fornitore e non è versionato (vedi README): i test di
    accettazione del par. 11 girano solo sulle macchine che hanno il file.
    """
    if SEED_FILE.is_file():
        return
    skip = pytest.mark.skip(reason=f"Seed reale assente: {SEED_FILE}")
    for item in items:
        if "seedfile" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def seed_file() -> Path:
    return SEED_FILE


@pytest.fixture
def seed_schema() -> Path:
    return SEED_SCHEMA


@pytest.fixture
def settings_row(db):
    from core.models import AppSettings

    return AppSettings.get_solo()


@pytest.fixture
def admin_user_with_role(db):
    from django.contrib.auth.models import Group, User

    from core import roles

    roles.ensure_groups()
    user = User.objects.create_user("responsabile", password="password-lunga-123")
    user.groups.add(Group.objects.get(name=roles.MANAGER))
    return user


@pytest.fixture
def d():
    """Scorciatoia: d("1.5") -> Decimal con 4 decimali."""

    def _d(value) -> Decimal:
        from domain.money import to_days

        return to_days(value)

    return _d
