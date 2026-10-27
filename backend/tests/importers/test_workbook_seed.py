from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from canone.models import Canone, CanoneSubactivity
from directory.models import Person
from domain.wallet_balance import wallet_year_balance
from importers.batch import apply_seed, dry_run_seed, schema_paths
from importers.rollback import rollback_seed_batch
from importers.schema import SeedValidationError, detect_schema_version, validate_seed_auto
from imports.models import (
    ImportBatch,
    ImportKind,
    WorkbookDatasetSnapshot,
    WorkbookSheetSnapshot,
)
from projects.models import Project
from tests.factories import UserFactory
from timesheets.models import TimesheetEntry
from wallet.models import (
    WalletActivity,
    WalletAllocation,
    WalletFundingTranche,
    WalletSourceLot,
    WalletYear,
)


def _find_seed_file(filename: str) -> Path:
    candidates = (
        Path(__file__).parents[3] / "data" / "seed" / filename,
        Path(__file__).parents[2] / "data" / "seed" / filename,
        Path("/app/data/seed") / filename,
    )
    for path in candidates:
        if path.is_file():
            return path
    pytest.skip(f"Seed {filename} non presente nei percorsi: {candidates}")


@pytest.fixture
def workbook_seed_path() -> Path:
    return _find_seed_file("seed_imola_full_2026-10-09.json")


@pytest.fixture
def workbook_payload(workbook_seed_path: Path) -> tuple[dict, str]:
    text = workbook_seed_path.read_text(encoding="utf-8")
    return validate_seed_auto(text, schema_paths()), text


@pytest.fixture
def workbook_v3_seed_path() -> Path:
    return _find_seed_file("seed_imola_v3_2026-10-09.json")


@pytest.fixture
def workbook_v3_payload(workbook_v3_seed_path: Path) -> tuple[dict, str]:
    text = workbook_v3_seed_path.read_text(encoding="utf-8")
    return validate_seed_auto(text, schema_paths()), text


@pytest.fixture
def workbook_v4_seed_path() -> Path:
    return _find_seed_file("seed_imola_v4_2026-10-09.json")


@pytest.fixture
def workbook_v4_payload(workbook_v4_seed_path: Path) -> tuple[dict, str]:
    text = workbook_v4_seed_path.read_text(encoding="utf-8")
    return validate_seed_auto(text, schema_paths()), text


def test_rileva_versione_e_rifiuta_versioni_sconosciute():
    assert detect_schema_version('{"meta":{"schema_version":"2.0.0"}}') == "2.0.0"
    assert detect_schema_version('{"meta":{"schema_version":"3.0.0"}}') == "3.0.0"
    assert detect_schema_version('{"meta":{"schema_version":"4.0.0"}}') == "4.0.0"
    with pytest.raises(SeedValidationError, match="schema supportata"):
        detect_schema_version(json.dumps({"meta": {"schema_version": "9.9.9"}}))


def test_rifiuta_workbook_con_conteggi_interni_incoerenti(workbook_payload):
    payload, _text = workbook_payload
    tampered = deepcopy(payload)
    tampered["datasets"][0]["row_count"] += 1

    with pytest.raises(ValueError, match="row_count"):
        dry_run_seed(tampered, source_filename="workbook.json")


@pytest.mark.django_db
def test_dry_run_v2_verifica_copertura_senza_persistenza(workbook_payload):
    payload, _text = workbook_payload

    result = dry_run_seed(payload, source_filename="workbook.json")

    assert result.report.schema_version == "2.0.0"
    assert result.report.totals["copertura"] == "integrale"
    assert result.report.totals["fogli"] == 10
    assert result.report.totals["dataset"] == 10
    assert result.report.totals["righe_dataset"] == 424
    assert ImportBatch.objects.count() == 0
    assert WorkbookSheetSnapshot.objects.count() == 0
    assert WorkbookDatasetSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_apply_v2_persiste_tutti_i_fogli_dataset_e_righe(workbook_payload):
    payload, text = workbook_payload

    result = apply_seed(
        payload,
        source_filename="workbook.json",
        content_hash="a" * 64,
    )

    assert result.batch is not None
    assert result.batch.kind == ImportKind.WORKBOOK_JSON
    assert result.batch.report["totali_calcolati"]["copertura"] == "integrale"
    assert WorkbookSheetSnapshot.objects.filter(batch=result.batch).count() == 10
    datasets = WorkbookDatasetSnapshot.objects.filter(batch=result.batch)
    assert datasets.count() == 10
    assert sum(dataset.row_count for dataset in datasets) == 424
    assert Project.objects.count() == 142
    assert Person.objects.count() == 21
    assert Canone.objects.count() == 2
    assert CanoneSubactivity.objects.count() == 52
    assert WalletActivity.objects.count() == 20
    assert WalletAllocation.objects.count() == 22
    assert WalletYear.objects.count() == 1
    assert TimesheetEntry.objects.count() == 189
    wallet_balance = wallet_year_balance(2026)
    assert wallet_balance.total_source_capacity == Decimal("130.8600")
    assert wallet_balance.allocated_days == Decimal("115.8900")
    assert wallet_balance.unallocated_capacity == Decimal("14.9700")
    assert len(text) > 1_000_000


@pytest.mark.django_db
def test_api_espone_elenco_e_contenuto_dataset(workbook_payload):
    payload, _text = workbook_payload
    batch = apply_seed(
        payload,
        source_filename="workbook.json",
        content_hash="b" * 64,
    ).batch
    assert batch is not None
    client = APIClient()
    client.force_authenticate(UserFactory(is_staff=True, is_superuser=True))

    response = client.get(f"/api/v1/admin/imports/{batch.id}/datasets")

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 10
    project_dataset = next(
        dataset for dataset in body["results"] if dataset["dataset_id"] == "Progetti::Tabella3967"
    )
    detail = client.get(f"/api/v1/admin/imports/{batch.id}/datasets/{project_dataset['id']}")
    assert detail.status_code == 200
    assert detail.json()["row_count"] == 144
    assert len(detail.json()["rows"]) == 144


@pytest.mark.django_db
def test_rebuild_v2_rende_disponibili_le_api_operative(workbook_payload):
    payload, _text = workbook_payload
    apply_seed(payload, source_filename="workbook.json", content_hash="c" * 64)
    client = APIClient()
    client.force_authenticate(UserFactory(is_staff=True, is_superuser=True))

    for endpoint in (
        "/api/v1/dashboard",
        "/api/v1/projects",
        "/api/v1/wallet/2026/balance",
        "/api/v1/wallet/2026/flow",
        "/api/v1/canoni",
        "/api/v1/review-queue",
        "/api/v1/reconciliation/latest",
        "/api/v1/cost-analysis",
    ):
        response = client.get(endpoint)
        assert response.status_code == 200, (endpoint, response.content)

    projects = client.get("/api/v1/projects").json()
    assert projects["count"] == 142


@pytest.mark.django_db(transaction=True)
def test_rollback_v2_rimuove_staging_e_dati_operativi(workbook_payload):
    payload, _text = workbook_payload
    batch = apply_seed(payload, source_filename="workbook.json", content_hash="d" * 64).batch
    assert batch is not None

    result = rollback_seed_batch(str(batch.id))

    assert result.deleted["progetti"] == 142
    assert result.deleted["fogli_workbook"] == 10
    assert result.deleted["dataset_workbook"] == 10
    assert Project.objects.count() == 0
    assert TimesheetEntry.objects.count() == 0
    assert WorkbookSheetSnapshot.objects.count() == 0
    assert WorkbookDatasetSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_dry_run_v3_valida_e_simula_senza_persistenza(workbook_v3_payload):
    payload, _text = workbook_v3_payload

    result = dry_run_seed(payload, source_filename="seed_imola_v3_2026-10-09.json")

    assert result.report.schema_version == "3.0.0"
    assert result.report.totals["copertura"] == "integrale"
    assert result.report.totals["fogli"] == 10
    assert result.report.totals["dataset"] == 10
    assert result.report.totals["proiezione_applicativa"]["wallet_allocations"] == 15
    assert ImportBatch.objects.count() == 0
    assert WorkbookSheetSnapshot.objects.count() == 0
    assert WorkbookDatasetSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_apply_v3_persiste_wallet_v3_e_tutti_i_dati(workbook_v3_payload):
    payload, _text = workbook_v3_payload

    result = apply_seed(
        payload,
        source_filename="seed_imola_v3_2026-10-09.json",
        content_hash="e" * 64,
    )

    assert result.batch is not None
    assert result.batch.kind == ImportKind.WORKBOOK_JSON
    assert result.batch.status == "APPLIED"
    assert Project.objects.count() == 142
    assert Person.objects.count() == 21
    assert Canone.objects.count() == 2
    assert WalletYear.objects.filter(year=2026).exists()
    assert WalletActivity.objects.count() == 15
    assert WalletSourceLot.objects.count() == 11
    assert WalletAllocation.objects.count() == 15
    assert WalletFundingTranche.objects.count() == 17
    fifo_use = WalletAllocation.objects.get(activity__code="RM-300229")
    assert list(
        fifo_use.funding_tranches.order_by("sequence").values_list(
            "source_lot__source_year", "committed_days", "consumed_days"
        )
    ) == [
        (2025, Decimal("7.0000"), Decimal("7.0000")),
        (2026, Decimal("8.0000"), Decimal("5.6300")),
    ]
    balance = wallet_year_balance(2026)
    assert balance.total_source_capacity == Decimal("123.3000")
    assert balance.allocated_days == Decimal("108.3300")
    assert balance.unallocated_capacity == Decimal("14.9700")


@pytest.mark.django_db
def test_apply_v4_ripartisce_i_consuntivi_sui_mesi_excel(workbook_v4_payload):
    payload, _text = workbook_v4_payload

    result = apply_seed(
        payload,
        source_filename="seed_imola_v4_2026-10-09.json",
        content_hash="4" * 64,
    )

    assert result.batch is not None
    assert result.batch.status == "APPLIED"
    monthly_rows = payload["application"]["monthly_timesheets"]
    assert len(monthly_rows) == 206
    sample_code = monthly_rows[0]["codice_progetto"]
    expected = sum(row["giornate"] for row in monthly_rows if row["codice_progetto"] == sample_code)
    entries = TimesheetEntry.objects.filter(
        project__code=sample_code,
        source="SEED_INIZIALE",
        reversals__isnull=True,
    )
    assert entries.values("period").distinct().count() > 1
    assert sum((entry.days for entry in entries), Decimal("0")) == expected


@pytest.mark.django_db
def test_upgrade_v3_v4_storna_il_totale_senza_raddoppiare(workbook_v3_payload, workbook_v4_payload):
    v3_payload, _v3_text = workbook_v3_payload
    v4_payload, _v4_text = workbook_v4_payload
    apply_seed(v3_payload, source_filename="v3.json", content_hash="3" * 64)

    sample = v4_payload["application"]["monthly_timesheets"][0]
    code = sample["codice_progetto"]
    expected = sum(
        row["giornate"]
        for row in v4_payload["application"]["monthly_timesheets"]
        if row["codice_progetto"] == code
    )
    apply_seed(v4_payload, source_filename="v4.json", content_hash="4" * 64)

    entries = TimesheetEntry.objects.filter(project__code=code)
    assert entries.filter(source="STORNO").exists()
    assert sum((entry.days for entry in entries), Decimal("0")) == expected


@pytest.mark.django_db
def test_api_admin_imports_seed_v3_dry_run_e_apply(workbook_v3_seed_path):
    from io import BytesIO

    client = APIClient()
    client.force_authenticate(UserFactory(is_staff=True, is_superuser=True))

    raw = workbook_v3_seed_path.read_bytes()
    file_obj = BytesIO(raw)
    file_obj.name = "seed_imola_v3_2026-10-09.json"

    # Dry-run
    res_dry = client.post(
        "/api/v1/admin/imports/seed",
        {"file": file_obj, "apply": "false"},
        format="multipart",
    )
    assert res_dry.status_code == 200, res_dry.json()
    dry_data = res_dry.json()
    assert dry_data["mode"] == "dry-run"
    assert dry_data["report"]["schema_version"] == "3.0.0"
    confirmation_hash = dry_data["confirmation_hash"]

    # Apply
    file_obj.seek(0)
    res_apply = client.post(
        "/api/v1/admin/imports/seed",
        {"file": file_obj, "apply": "true", "confirmation_hash": confirmation_hash},
        format="multipart",
    )
    assert res_apply.status_code == 200, res_apply.json()
    apply_data = res_apply.json()
    assert apply_data["mode"] == "apply"
    assert apply_data["batch_id"] is not None
