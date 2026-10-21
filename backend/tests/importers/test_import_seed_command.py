"""Test del management command e dell'orchestratore seed JSON."""

from __future__ import annotations

import hashlib
import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command

from directory.models import Organization
from importers.batch import ImportExecutionError, apply_seed
from importers.report import ImportReport
from imports.models import ImportBatch, ImportIssue, ImportStatus

pytestmark = pytest.mark.django_db


def valid_payload() -> dict:
    return {
        "meta": {
            "schema_version": "1.0.0",
            "generato_il": "2026-10-20",
            "data_riferimento_dati": "2026-10-16",
        },
        "configurazione": {
            "fornitore": {"codice": "IMOLA", "ragione_sociale": "Imola Informatica"},
            "cliente": {"codice": "BMED", "ragione_sociale": "Banca Mediolanum"},
            "ore_per_giornata": 8,
            "granularita_ppm_gg": 0.0625,
            "tolleranza_riconciliazione_gg": 0.01,
            "regola_scadenza_residui": {
                "si_applica_a": "PROGETTI_CON_CONSUNTIVAZIONE_CHIUSA",
                "anno_base": "ANNO_DATA_CHIUSURA_CONSUNTIVAZIONE",
                "anni_validita_dopo_chiusura": 1,
                "fatturazione_influisce": False,
            },
        },
        "persone": [],
        "progetti": [],
        "canoni": [],
        "wallet": {"anno": 2026, "attivita": [], "allocazioni": []},
        "snapshot_ppm": [],
        "anomalie_aperte": [],
    }


def write_seed(tmp_path: Path, payload: dict | None = None, *, text: str | None = None) -> Path:
    path = tmp_path / "seed.json"
    path.write_text(
        text if text is not None else json.dumps(payload or valid_payload()), encoding="utf-8"
    )
    return path


def test_dry_run_produce_report_senza_persistenza(tmp_path: Path):
    path = write_seed(tmp_path)
    stdout = StringIO()

    call_command("import_seed", str(path), "--dry-run", stdout=stdout)

    assert "SIMULAZIONE" in stdout.getvalue()
    assert "nessun dato persistito" in stdout.getvalue()
    assert ImportBatch.objects.count() == 0
    assert ImportIssue.objects.count() == 0
    assert Organization.objects.count() == 0


def test_apply_persiste_batch_hash_report_e_dati(tmp_path: Path):
    path = write_seed(tmp_path)
    stdout = StringIO()

    call_command("import_seed", str(path), "--apply", stdout=stdout)

    batch = ImportBatch.objects.get()
    assert batch.status == ImportStatus.APPLIED
    assert batch.content_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert batch.report["esito"] == "ok"
    assert batch.report["simulazione"] is False
    assert batch.applied_at is not None
    assert Organization.objects.count() == 2
    assert "Batch applicato" in stdout.getvalue()


def test_reimport_identico_e_idempotente_crea_nuovo_batch(tmp_path: Path):
    path = write_seed(tmp_path)
    call_command("import_seed", str(path), "--apply")

    stdout = StringIO()
    call_command("import_seed", str(path), "--apply", "--json", stdout=stdout)

    assert ImportBatch.objects.filter(status=ImportStatus.APPLIED).count() == 2
    latest = ImportBatch.objects.order_by("-created_at").first()
    assert latest is not None
    assert latest.report["riepilogo"]["creati"] == 0
    assert latest.report["riepilogo"]["aggiornati"] == 0
    assert Organization.objects.count() == 2
    assert '"esito": "ok"' in stdout.getvalue()


def test_schema_invalido_non_scrive_nulla(tmp_path: Path):
    payload = valid_payload()
    payload["meta"]["schema_version"] = "9.0.0"
    path = write_seed(tmp_path, payload)

    with pytest.raises(CommandError, match="non rispetta"):
        call_command("import_seed", str(path), "--apply")

    assert ImportBatch.objects.count() == 0
    assert Organization.objects.count() == 0


def test_eccezione_importer_annulla_dati_e_conserva_batch_failed(tmp_path: Path):
    path = write_seed(tmp_path)
    with patch("importers.batch.import_foundation") as importer:
        importer.side_effect = RuntimeError("guasto controllato")
        with pytest.raises(CommandError, match="guasto controllato"):
            call_command("import_seed", str(path), "--apply")

    batch = ImportBatch.objects.get()
    assert batch.status == ImportStatus.FAILED
    assert batch.error == "guasto controllato"
    assert batch.report["esito"] == "errori"
    assert batch.issues.filter(level="ERROR", message="guasto controllato").exists()
    assert Organization.objects.count() == 0


def test_atomic_rollback_rimuove_anche_scritture_prima_delleccezione():
    payload = valid_payload()

    def partially_write(*args, **kwargs):
        Organization.objects.create(code="TEMP", name="Temporanea")
        raise RuntimeError("boom")

    with patch("importers.batch.import_foundation", side_effect=partially_write):
        with pytest.raises(ImportExecutionError):
            apply_seed(payload, source_filename="seed.json", content_hash="a" * 64)

    assert not Organization.objects.filter(code="TEMP").exists()
    assert ImportBatch.objects.filter(status=ImportStatus.FAILED).count() == 1


@pytest.mark.parametrize(
    ("filename", "content", "match"),
    [
        ("missing.json", None, "File non trovato"),
        ("broken.json", "{non-json", "JSON non valido"),
    ],
)
def test_file_mancante_e_json_errato(
    tmp_path: Path, filename: str, content: str | None, match: str
):
    path = tmp_path / filename
    if content is not None:
        path.write_text(content, encoding="utf-8")

    with pytest.raises(CommandError, match=match):
        call_command("import_seed", str(path), "--dry-run")

    assert ImportBatch.objects.count() == 0


def test_conflitto_batch_in_corso_stesso_hash(tmp_path: Path):
    path = write_seed(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    ImportBatch.objects.create(
        kind="SEED_JSON",
        status=ImportStatus.DRY_RUN,
        source_filename=path.name,
        content_hash=digest,
    )

    with pytest.raises(CommandError, match="Conflitto di import"):
        call_command("import_seed", str(path), "--apply")


def test_apply_persiste_avvisi_e_scarti_come_issue():
    payload = valid_payload()

    def report_issues(payload, *, batch, report: ImportReport):
        report.warn("avviso globale")
        report.entity("demo").skipped.append({"chiave": "X", "motivo": "scartato"})

    with patch("importers.batch.import_foundation", side_effect=report_issues):
        result = apply_seed(payload, source_filename="seed.json", content_hash="b" * 64)

    assert result.batch is not None
    assert list(result.batch.issues.values_list("level", "entity", "key", "message")) == [
        ("WARNING", "", "", "avviso globale"),
        ("WARNING", "demo", "X", "scartato"),
    ]
