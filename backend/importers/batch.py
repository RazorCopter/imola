"""Orchestrazione transazionale degli import seed JSON."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from importers.report import ImportReport
from importers.schema import load_schema, validate_seed
from importers.seed_json import import_foundation
from imports.models import (
    ImportBatch,
    ImportIssue,
    ImportIssueLevel,
    ImportKind,
    ImportStatus,
)


class ImportConflictError(RuntimeError):
    """L'applicazione richiesta confligge con un batch già applicato."""


class ImportExecutionError(RuntimeError):
    """Il cuore importer ha fallito; il batch FAILED è stato conservato."""

    def __init__(self, message: str, *, batch: ImportBatch) -> None:
        super().__init__(message)
        self.batch = batch


class _DryRunRollback(Exception):
    """Sentinella interna usata per annullare tutte le scritture della simulazione."""


@dataclass(frozen=True)
class ImportResult:
    report: ImportReport
    batch: ImportBatch | None = None


def default_schema_path() -> Path:
    return Path(settings.BASE_DIR).parent / "seed_schema_v1.json"


def read_seed_file(path: str | Path) -> tuple[Path, str, str]:
    source = Path(path)
    raw = source.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Il file non è UTF-8 valido: {exc}") from exc
    return source, text, hashlib.sha256(raw).hexdigest()


def _make_report(payload: dict[str, Any], source_filename: str, *, dry_run: bool) -> ImportReport:
    meta = payload["meta"]
    return ImportReport(
        kind=ImportKind.SEED_JSON,
        source_filename=source_filename,
        schema_version=meta["schema_version"],
        reference_date=meta.get("data_riferimento_dati"),
        dry_run=dry_run,
    )


def _persist_issues(batch: ImportBatch, report: ImportReport) -> None:
    issues = [
        ImportIssue(batch=batch, level=ImportIssueLevel.WARNING, message=message)
        for message in report.warnings
    ]
    for entity_name, entity in report.entities.items():
        issues.extend(
            ImportIssue(
                batch=batch,
                level=ImportIssueLevel.WARNING,
                entity=entity_name,
                key=str(item.get("chiave", "")),
                message=str(item.get("motivo", "")),
            )
            for item in entity.skipped
        )
        issues.extend(
            ImportIssue(
                batch=batch,
                level=ImportIssueLevel.ERROR,
                entity=entity_name,
                key=str(item.get("chiave", "")),
                message=str(item.get("motivo", item)),
            )
            for item in entity.errors
        )
    issues.extend(
        ImportIssue(batch=batch, level=ImportIssueLevel.ERROR, message=message)
        for message in report.errors
    )
    ImportIssue.objects.bulk_create(issues)


def dry_run_seed(payload: dict[str, Any], *, source_filename: str) -> ImportResult:
    """Esegue il vero importer e forza il rollback, incluso il batch temporaneo."""

    report = _make_report(payload, source_filename, dry_run=True)
    try:
        with transaction.atomic():
            batch = ImportBatch.objects.create(
                kind=ImportKind.SEED_JSON,
                status=ImportStatus.DRY_RUN,
                source_filename=source_filename,
            )
            import_foundation(payload, batch=batch, report=report)
            raise _DryRunRollback
    except _DryRunRollback:
        return ImportResult(report=report)


def apply_seed(payload: dict[str, Any], *, source_filename: str, content_hash: str) -> ImportResult:
    """Applica il seed in una transazione e conserva un batch FAILED se questa fallisce."""

    in_progress = ImportBatch.objects.filter(
        kind=ImportKind.SEED_JSON,
        status=ImportStatus.DRY_RUN,
        content_hash=content_hash,
    ).first()
    if in_progress is not None:
        raise ImportConflictError(
            f"Contenuto già in applicazione nel batch {in_progress.pk} "
            f"({in_progress.source_filename})."
        )

    report = _make_report(payload, source_filename, dry_run=False)
    try:
        with transaction.atomic():
            batch = ImportBatch.objects.create(
                kind=ImportKind.SEED_JSON,
                status=ImportStatus.DRY_RUN,
                source_filename=source_filename,
                content_hash=content_hash,
            )
            import_foundation(payload, batch=batch, report=report)
            if not report.ok:
                raise RuntimeError("Il report contiene errori; applicazione annullata.")
            batch.status = ImportStatus.APPLIED
            batch.applied_at = timezone.now()
            batch.report = report.as_dict()
            batch.save(update_fields=["status", "applied_at", "report", "updated_at"])
            _persist_issues(batch, report)
        return ImportResult(report=report, batch=batch)
    except Exception as exc:
        report.fail(str(exc))
        failed_report = report.as_dict()
        batch = ImportBatch.objects.create(
            kind=ImportKind.SEED_JSON,
            status=ImportStatus.FAILED,
            source_filename=source_filename,
            content_hash=content_hash,
            report=failed_report,
            error=str(exc),
        )
        _persist_issues(batch, report)
        raise ImportExecutionError(str(exc), batch=batch) from exc


def orchestrate_seed(
    path: str | Path,
    *,
    dry_run: bool,
    schema_path: str | Path | None = None,
) -> ImportResult:
    source, text, content_hash = read_seed_file(path)
    schema = load_schema(schema_path or default_schema_path())
    payload = validate_seed(text, schema)
    if dry_run:
        return dry_run_seed(payload, source_filename=source.name)
    return apply_seed(payload, source_filename=source.name, content_hash=content_hash)
