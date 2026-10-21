"""Test per la coda di revisione progetti (D-03).

Verifica:
1. Selezione di progetti CHIUSO senza data e DA_VERIFICARE.
2. Esclusione di progetti regolari (ATTIVO con affidabilità CERTO, CHIUSO con data).
3. Precompilazione della data di chiusura proposta da data_fine_prevista.
4. Calcolo scadenza potenziale e avviso entro 90 giorni.
5. Ordinamento per scadenza potenziale crescente.
6. Endpoint API GET /api/v1/projects/review-queue.
7. Conteggio esatto di 12 progetti (3 CHIUSO senza data + 9 DA_VERIFICARE) sul seed reale.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from rest_framework.test import APIClient

from core import roles
from domain.residuals import review_queue_projects
from imports.models import ImportKind, ImportStatus
from projects.models import TimesheetStatus
from tests.factories import ImportBatchFactory, ProjectFactory

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-review-123"


@pytest.fixture
def api_client() -> APIClient:
    roles.ensure_groups()
    user = User.objects.create_user("revisore", password=PASSWORD)
    user.groups.add(Group.objects.get(name=roles.MANAGER))
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_review_queue_selezione_e_precompilazione():
    seed_batch = ImportBatchFactory(
        kind=ImportKind.SEED_JSON,
        status=ImportStatus.APPLIED,
    )
    # 1. CHIUSO senza data di chiusura (con data_fine_prevista)
    p_chiuso = ProjectFactory(
        code="PRJ-CHIUSO-SENZA-DATA",
        start_date=date(2025, 1, 1),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=None,
        planned_end_date=date(2025, 6, 30),
        import_batch=seed_batch,
        budget_days=Decimal("10.0000"),
    )
    # 2. DA_VERIFICARE
    p_da_verificare = ProjectFactory(
        code="PRJ-DA-VERIFICARE",
        start_date=date(2026, 1, 1),
        timesheet_status=TimesheetStatus.DA_VERIFICARE,
        planned_end_date=date(2026, 11, 15),
        budget_days=Decimal("20.0000"),
    )
    # 3. Progetto regolare (non deve apparire)
    ProjectFactory(
        code="PRJ-REGOLARE-ATTIVO",
        start_date=date(2026, 1, 1),
        timesheet_status=TimesheetStatus.ATTIVO,
        budget_days=Decimal("15.0000"),
    )
    # 4. Progetto CHIUSO con data (non deve apparire)
    ProjectFactory(
        code="PRJ-CHIUSO-CON-DATA",
        start_date=date(2025, 1, 1),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2025, 12, 31),
        budget_days=Decimal("5.0000"),
    )

    items = review_queue_projects(as_of=date(2026, 10, 16))
    codes = [x["codice"] for x in items]

    assert codes == ["PRJ-CHIUSO-SENZA-DATA", "PRJ-DA-VERIFICARE"]

    item_chiuso = next(x for x in items if x["codice"] == p_chiuso.code)
    assert item_chiuso["tipo_revisione"] == "CHIUSO_SENZA_DATA"
    assert item_chiuso["data_chiusura_proposta"] == date(2025, 6, 30)
    # Scadenza potenziale per chiusura a metà 2025: fine 2026 (2026-12-31)
    assert item_chiuso["scadenza_potenziale"] == date(2026, 12, 31)
    # Dal 2026-10-16 al 2026-12-31 ci sono 76 giorni (<= 90gg) -> deve esserci avviso_scadenza
    assert item_chiuso["avviso_scadenza"] is not None
    assert "utilizzabili fino al 31/12/2026" in item_chiuso["avviso_scadenza"]

    item_dv = next(x for x in items if x["codice"] == p_da_verificare.code)
    assert item_dv["tipo_revisione"] == "DA_VERIFICARE"
    assert item_dv["data_chiusura_proposta"] == date(2026, 11, 15)
    # Per fine 2026-11-15, la scadenza potenziale è fine 2027 (2027-12-31)
    assert item_dv["scadenza_potenziale"] == date(2027, 12, 31)
    # Dal 2026-10-16 a fine 2027 sono > 90gg -> nessun avviso di scadenza imminente
    assert item_dv["avviso_scadenza"] is None


def test_review_queue_ordinamento_scadenza_crescente():
    seed_batch = ImportBatchFactory(
        kind=ImportKind.SEED_JSON,
        status=ImportStatus.APPLIED,
    )
    # Progetto A: chiusura proposta nel 2024 -> scadenza potenziale fine 2025
    ProjectFactory(
        code="PRJ-SCADE-PRIMA",
        start_date=date(2024, 1, 1),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=None,
        planned_end_date=date(2024, 5, 10),
        import_batch=seed_batch,
        budget_days=Decimal("10.0000"),
    )
    # Progetto B: chiusura proposta nel 2026 -> scadenza potenziale fine 2027
    ProjectFactory(
        code="PRJ-SCADE-DOPO",
        start_date=date(2026, 1, 1),
        timesheet_status=TimesheetStatus.DA_VERIFICARE,
        planned_end_date=date(2026, 5, 10),
        budget_days=Decimal("10.0000"),
    )
    # Progetto C: chiusura proposta nel 2025 -> scadenza potenziale fine 2026
    ProjectFactory(
        code="PRJ-SCADE-MEZZO",
        start_date=date(2025, 1, 1),
        timesheet_status=TimesheetStatus.DA_VERIFICARE,
        planned_end_date=date(2025, 5, 10),
        budget_days=Decimal("10.0000"),
    )

    items = review_queue_projects(as_of=date(2026, 10, 16))
    ordered_codes = [x["codice"] for x in items]
    assert ordered_codes == ["PRJ-SCADE-PRIMA", "PRJ-SCADE-MEZZO", "PRJ-SCADE-DOPO"]


def test_api_review_queue_endpoint(api_client: APIClient):
    seed_batch = ImportBatchFactory(
        kind=ImportKind.SEED_JSON,
        status=ImportStatus.APPLIED,
    )
    ProjectFactory(
        code="PRJ-API-1",
        start_date=date(2025, 1, 1),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=None,
        planned_end_date=date(2025, 10, 1),
        import_batch=seed_batch,
        budget_days=Decimal("5.0000"),
    )
    ProjectFactory(
        code="PRJ-API-2",
        start_date=date(2026, 1, 1),
        timesheet_status=TimesheetStatus.DA_VERIFICARE,
        planned_end_date=date(2026, 3, 1),
        budget_days=Decimal("8.0000"),
    )

    response = api_client.get("/api/v1/projects/review-queue?as_of=2026-10-16")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["chiuso_senza_data_count"] == 1
    assert data["da_verificare_count"] == 1
    assert len(data["results"]) == 2
    assert data["results"][0]["codice"] == "PRJ-API-1"


@pytest.mark.seedfile
def test_review_queue_sul_seed_reale():
    """Accettazione sul seed reale: identità, date, ordinamento e warning della coda."""
    seed_file = Path(settings.BASE_DIR).parent / "data" / "seed" / "seed_imola_2026-10-16.json"
    if not seed_file.is_file():
        pytest.skip(f"File seed non presente in {seed_file}")

    stdout = StringIO()
    call_command("import_seed", str(seed_file), "--apply", stdout=stdout)

    as_of = date(2026, 10, 16)
    queue = review_queue_projects(as_of=as_of)

    chiuso_senza_data = [x for x in queue if x["tipo_revisione"] == "CHIUSO_SENZA_DATA"]
    da_verificare = [x for x in queue if x["tipo_revisione"] == "DA_VERIFICARE"]

    expected_2025 = [
        "IM24517-3313-BMED-ARCH-SOLUTION-DESIGN-CONSULENZA-AMMINISTRATO",
        "IM25026-3313-BMED-ARCH-SOLUTION-DESIGN-INTEGRAZIONE-SCHEDA-FONDO",
        "IM25075-3313-BMED-ARCH-SOLUTION-DESIGN-APP-FB-WAVE-2",
        "IM25151-3313-BMED-ARCH-ICT-ASSET-LIFECYCLE-OBSOLESCENZA",
        "IM25188-3313-BMED-ARCH-INTEGR-NOTIFICHE-PUSH-APP-MED-ALERT-SEC",
        "IM25206-3313-BMED-ARCH-DATABRICKS-SUPERAMENTO-CRMA-DATALAB",
        "IM25236-3313-BMED-ARCH-RAFFORZAMENTO-DATA-QUALITY-TECNICA",
        "IM25255-3313-BMED-ARCH-ADEGUA-OSI-ORIGINATION-MONIT-CRED-ORD",
        "IM25270-3313-BMED-ARCH-SOLUTION-DESIGN-AGILE-CREDIT",
    ]
    expected_closed = [
        "IM26034-3313-BMED-ARCH-SOLUTION-DESIGN-MIGRAZIONE-VIYA",
        "IM26047-3313-BMED-ARCH-SOLUTION-DESIGN-MARKET-RISK-W2",
        "IM26075-3313-BMED-ARCH-MIGRAZIONE-COMP-ARCH-OSB14",
    ]

    assert [x["codice"] for x in queue] == expected_2025 + expected_closed
    assert [x["codice"] for x in da_verificare] == expected_2025
    assert [x["codice"] for x in chiuso_senza_data] == expected_closed
    assert len(queue) == 12

    for item in da_verificare:
        assert item["data_chiusura_proposta"].year == 2025
        assert item["scadenza_potenziale"] == date(2026, 12, 31)
        assert item["in_scadenza_entro_90gg"] is True
        assert item["avviso_scadenza"].endswith("utilizzabili fino al 31/12/2026.")

    expected_closed_dates = {
        expected_closed[0]: date(2026, 6, 30),
        expected_closed[1]: date(2026, 7, 31),
        expected_closed[2]: date(2026, 3, 31),
    }
    for item in chiuso_senza_data:
        assert item["data_chiusura_proposta"] == expected_closed_dates[item["codice"]]
        assert item["scadenza_potenziale"] == date(2027, 12, 31)
        assert item["in_scadenza_entro_90gg"] is False
        assert item["avviso_scadenza"] is None
