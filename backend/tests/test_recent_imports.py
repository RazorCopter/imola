"""Evidenza 24h dei progetti toccati dall'estratto operativo Excel."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core import roles
from domain.recent_imports import is_recent_import
from imports.models import ImportKind, ImportStatus
from tests.factories import (
    ImportBatchFactory,
    ProjectFactory,
    TimesheetEntryFactory,
    WalletAllocationFactory,
)
from tests.test_roles_object_permissions import make_client_for_role
from timesheets.models import TimesheetSource

pytestmark = pytest.mark.django_db


def _batch(
    *, hours_ago: float, status: str = ImportStatus.APPLIED, kind=ImportKind.OPERATIONAL_XLSX
):
    return ImportBatchFactory(
        kind=kind,
        status=status,
        applied_at=timezone.now() - timedelta(hours=hours_ago),
        source_filename="estratto.xlsx",
    )


def _imported_entry(batch, **target):
    return TimesheetEntryFactory(source=TimesheetSource.EXCEL_IMPORT, import_batch=batch, **target)


def _balances(client, query: str = ""):
    response = client.get(f"/api/v1/projects/balances{query}")
    assert response.status_code == 200
    return {row["codice"]: row for row in response.json()["results"]}


def test_progetti_toccati_da_import_recente_sono_evidenziati_e_filtrabili():
    client, _user = make_client_for_role(roles.ADMIN)
    recent = _batch(hours_ago=2)
    old = _batch(hours_ago=30)

    direct = ProjectFactory(code="PRJ-DIRETTO")
    _imported_entry(recent, project=direct)

    via_wallet = ProjectFactory(code="PRJ-WALLET", budget_days=Decimal("10.0000"))
    allocation = WalletAllocationFactory(source_project=via_wallet)
    _imported_entry(recent, wallet_allocation=allocation)

    stale = ProjectFactory(code="PRJ-VECCHIO")
    _imported_entry(old, project=stale)

    manual = ProjectFactory(code="PRJ-MANUALE")
    TimesheetEntryFactory(project=manual, source=TimesheetSource.MANUALE)

    rows = _balances(client)
    assert rows["PRJ-DIRETTO"]["nuovo_inserimento"] is True
    assert rows["PRJ-DIRETTO"]["ultimo_import"] is not None
    assert rows["PRJ-WALLET"]["nuovo_inserimento"] is True
    assert rows["PRJ-VECCHIO"]["nuovo_inserimento"] is False
    assert rows["PRJ-VECCHIO"]["ultimo_import"] is not None
    assert rows["PRJ-MANUALE"]["nuovo_inserimento"] is False
    assert rows["PRJ-MANUALE"]["ultimo_import"] is None

    filtered = _balances(client, "?nuovi=1")
    assert set(filtered) == {"PRJ-DIRETTO", "PRJ-WALLET"}


def test_batch_annullati_altri_tipi_e_consuntivi_stornati_non_contano():
    client, _user = make_client_for_role(roles.ADMIN)

    rolled_back = ProjectFactory(code="PRJ-ANNULLATO")
    _imported_entry(_batch(hours_ago=1, status=ImportStatus.ROLLED_BACK), project=rolled_back)

    other_kind = ProjectFactory(code="PRJ-SEED")
    _imported_entry(_batch(hours_ago=1, kind=ImportKind.SEED_JSON), project=other_kind)

    reversed_project = ProjectFactory(code="PRJ-STORNATO")
    entry = _imported_entry(_batch(hours_ago=1), project=reversed_project)
    TimesheetEntryFactory(
        project=reversed_project,
        source=TimesheetSource.STORNO,
        days=-entry.days,
        reverses=entry,
    )

    rows = _balances(client)
    for code in ("PRJ-ANNULLATO", "PRJ-SEED", "PRJ-STORNATO"):
        assert rows[code]["nuovo_inserimento"] is False, code
    assert _balances(client, "?nuovi=1") == {}


def test_is_recent_import_finestra_24_ore():
    now = timezone.now()
    assert is_recent_import(None, now) is False
    assert is_recent_import(now - timedelta(hours=23, minutes=59), now) is True
    assert is_recent_import(now - timedelta(hours=24, minutes=1), now) is False
