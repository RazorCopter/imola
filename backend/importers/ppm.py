"""Parser e applicazione append-only degli estratti PPM Excel/PDF."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook  # type: ignore[import-untyped]

from anomalies.runner import run_checks
from domain.money import ZERO, quantize_days, to_days
from imports.models import ImportBatch, ImportIssue, ImportIssueLevel, ImportKind, ImportStatus
from ppm.models import PpmSnapshot, PpmSnapshotRow, SnapshotKind, normalize_project_code
from projects.models import Project
from timesheets.models import TimesheetEntry, TimesheetSource, month_start

EXTRACTED_RE = re.compile(
    r"Estratto\s+il\s+(\d{2})/(\d{2})/(\d{4})\s+alle\s+(\d{2}):(\d{2}):(\d{2})",
    re.IGNORECASE,
)


class PpmParseError(ValueError):
    pass


@dataclass
class ParsedRow:
    code: str
    total_days: Decimal
    project: Project | None = None


@dataclass
class ParsedPpm:
    source_filename: str
    extracted_at: datetime
    rows: list[ParsedRow]
    totals: dict[str, Decimal] = field(default_factory=dict)
    balanced: bool = False
    header_row: int = 0


@dataclass
class PpmReport:
    source_filename: str
    extracted_at: str
    recognized: int
    unmatched: int
    totals: dict[str, str]
    balanced: bool
    entries_created: int
    rows: list[dict]
    batch_id: str | None = None

    def as_dict(self) -> dict:
        return {
            "file": self.source_filename,
            "data_estrazione": self.extracted_at,
            "righe_riconosciute": self.recognized,
            "righe_non_riconosciute": self.unmatched,
            "totali": self.totals,
            "quadratura_ok": self.balanced,
            "entry_create": self.entries_created,
            "righe": self.rows,
            "batch_id": self.batch_id,
        }


def _extract_datetime(values: list[object]) -> datetime:
    text = " ".join(str(value) for value in values if value is not None)
    match = EXTRACTED_RE.search(text)
    if not match:
        raise PpmParseError(
            "Data di estrazione non trovata. Formato atteso: "
            "'Estratto il DD/MM/YYYY alle HH:MM:SS'."
        )
    day, month, year, hour, minute, second = map(int, match.groups())
    return datetime(
        year,
        month,
        day,
        hour,
        minute,
        second,
        tzinfo=timezone.get_current_timezone(),
    )


def _header_indexes(
    row: tuple[object, ...],
) -> tuple[int, int, int | None, int | None] | None:
    normalized = [str(value or "").strip().lower() for value in row]
    project_idx = next((i for i, value in enumerate(normalized) if "progetto" in value), None)
    total_idx = next(
        (
            i
            for i, value in enumerate(normalized)
            if value.replace(".", " ") in {"gg tot", "gg totale", "gg totali"}
            or ("gg" in value and "tot" in value)
        ),
        None,
    )
    if project_idx is None or total_idx is None:
        return None
    planned_idx = next(
        (i for i, value in enumerate(normalized) if "previst" in value),
        None,
    )
    residual_idx = next(
        (i for i, value in enumerate(normalized) if "residu" in value),
        None,
    )
    return project_idx, total_idx, planned_idx, residual_idx


def parse_ppm_xlsx(path: str | Path) -> ParsedPpm:
    source = Path(path)
    workbook = load_workbook(source, data_only=True, read_only=True)
    sheet = workbook.active
    preview = list(sheet.iter_rows(min_row=1, max_row=15, values_only=True))
    extracted_at = _extract_datetime([cell for row in preview for cell in row])
    header_row = 0
    indexes: tuple[int, int, int | None, int | None] | None = None
    for number, row in enumerate(preview, start=1):
        indexes = _header_indexes(row)
        if indexes:
            header_row = number
            break
    if indexes is None:
        raise PpmParseError(
            "Header non trovato nelle prime 15 righe: servono 'Progetto' e 'gg tot'."
        )
    project_idx, total_idx, planned_idx, residual_idx = indexes
    parsed: list[ParsedRow] = []
    declared_total: Decimal | None = None
    declared_planned: Decimal | None = None
    declared_residual: Decimal | None = None
    sum_planned = ZERO
    sum_residual = ZERO
    for values in sheet.iter_rows(min_row=header_row + 1, values_only=True):
        code_raw = values[project_idx] if project_idx < len(values) else None
        total_raw = values[total_idx] if total_idx < len(values) else None
        planned_raw = (
            values[planned_idx] if planned_idx is not None and planned_idx < len(values) else None
        )
        residual_raw = (
            values[residual_idx]
            if residual_idx is not None and residual_idx < len(values)
            else None
        )
        if code_raw in (None, "") and total_raw in (None, ""):
            continue
        code = str(code_raw or "").strip()
        if "totale" in code.lower() or code.lower() in {"totali", "total"}:
            if total_raw not in (None, ""):
                declared_total = to_days(total_raw)
            if planned_raw not in (None, ""):
                declared_planned = to_days(planned_raw)
            if residual_raw not in (None, ""):
                declared_residual = to_days(residual_raw)
            continue
        if total_raw in (None, ""):
            continue
        total_days = to_days(total_raw)
        parsed.append(ParsedRow(code=code, total_days=total_days))
        if planned_raw not in (None, ""):
            sum_planned += to_days(planned_raw)
        if residual_raw not in (None, ""):
            sum_residual += to_days(residual_raw)
    # In modalita read-only openpyxl mantiene aperto il file finche il workbook
    # non viene chiuso esplicitamente; su Windows cio impedisce la rimozione
    # del file temporaneo usato dall'endpoint di upload.
    workbook.close()
    if not parsed:
        raise PpmParseError("Nessuna riga dati trovata nell'estratto PPM.")
    sum_rows = quantize_days(sum((row.total_days for row in parsed), ZERO))
    sum_planned = quantize_days(sum_planned)
    sum_residual = quantize_days(sum_residual)
    balanced_total = declared_total is None or abs(sum_rows - declared_total) <= Decimal("0.0100")
    balanced_planned = declared_planned is None or abs(sum_planned - declared_planned) <= Decimal(
        "0.0100"
    )
    balanced_residual = declared_residual is None or abs(
        sum_residual - declared_residual
    ) <= Decimal("0.0100")
    balanced = balanced_total and balanced_planned and balanced_residual
    totals: dict[str, Decimal] = {"gg_totali": declared_total or sum_rows, "somma_righe": sum_rows}
    if declared_planned is not None or sum_planned > ZERO:
        totals["gg_previsti"] = declared_planned or sum_planned
        totals["somma_previsti"] = sum_planned
    if declared_residual is not None or sum_residual != ZERO:
        totals["gg_residui"] = declared_residual or sum_residual
        totals["somma_residui"] = sum_residual
    return ParsedPpm(
        source_filename=source.name,
        extracted_at=extracted_at,
        rows=parsed,
        totals=totals,
        balanced=balanced,
        header_row=header_row,
    )


def parse_ppm_pdf(path: str | Path) -> ParsedPpm:
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:
        raise PpmParseError(f"Impossibile estrarre il PDF PPM: {exc}") from exc
    if not text.strip():
        raise PpmParseError(
            "Impossibile estrarre il PDF PPM: il documento non contiene testo leggibile."
        )
    raise PpmParseError(
        "PDF PPM estratto, ma la struttura tabellare non è riconoscibile: usare l'Excel originale."
    )


def _match_projects(parsed: ParsedPpm) -> None:
    projects = list(Project.objects.all())
    exact = {project.code: project for project in projects}
    normalized = {normalize_project_code(project.code): project for project in projects}
    for row in parsed.rows:
        row.project = exact.get(row.code) or normalized.get(normalize_project_code(row.code))


def dry_run_ppm(path: str | Path) -> PpmReport:
    parsed = parse_ppm_pdf(path) if str(path).lower().endswith(".pdf") else parse_ppm_xlsx(path)
    _match_projects(parsed)
    rows: list[dict] = []
    recognized = 0
    for row in parsed.rows:
        internal = ZERO
        if row.project is not None:
            recognized += 1
            from domain.residuals import project_balance_qs

            project_bal = project_balance_qs().filter(pk=row.project.pk).first()
            internal = quantize_days(project_bal.total_consumed_days) if project_bal else ZERO
        delta = quantize_days(row.total_days - internal)
        rows.append(
            {
                "codice": row.code,
                "riconosciuta": row.project is not None,
                "progetto": row.project.code if row.project else None,
                "ppm": str(row.total_days),
                "interno": str(internal),
                "delta": str(delta),
            }
        )
    return PpmReport(
        source_filename=parsed.source_filename,
        extracted_at=parsed.extracted_at.isoformat(),
        recognized=recognized,
        unmatched=len(parsed.rows) - recognized,
        totals={key: str(value) for key, value in parsed.totals.items()},
        balanced=parsed.balanced,
        entries_created=0,
        rows=rows,
    )


@transaction.atomic
def apply_ppm(path: str | Path, *, user=None) -> PpmReport:
    source = Path(path)
    raw = source.read_bytes()
    existing = ImportBatch.objects.filter(
        kind__in=(ImportKind.PPM_XLSX, ImportKind.PPM_PDF),
        status=ImportStatus.APPLIED,
        content_hash=hashlib.sha256(raw).hexdigest(),
    ).first()
    if existing:
        report = existing.report.copy()
        report["entry_create"] = 0
        return PpmReport(
            source_filename=report["file"],
            extracted_at=report["data_estrazione"],
            recognized=report["righe_riconosciute"],
            unmatched=report["righe_non_riconosciute"],
            totals=report["totali"],
            balanced=report["quadratura_ok"],
            entries_created=0,
            rows=report["righe"],
            batch_id=str(existing.id),
        )
    dry = dry_run_ppm(source)
    parsed = parse_ppm_pdf(source) if source.suffix.lower() == ".pdf" else parse_ppm_xlsx(source)
    _match_projects(parsed)
    kind = ImportKind.PPM_PDF if source.suffix.lower() == ".pdf" else ImportKind.PPM_XLSX
    batch = ImportBatch.objects.create(
        kind=kind,
        status=ImportStatus.APPLIED,
        source_filename=source.name,
        content_hash=hashlib.sha256(raw).hexdigest(),
        applied_by=user,
        applied_at=timezone.now(),
    )
    snapshot = PpmSnapshot.objects.create(
        kind=SnapshotKind.PPM_WALLET,
        title=source.stem,
        extracted_at=parsed.extracted_at,
        source_filename=source.name,
        row_count=len(parsed.rows),
        totals={key: str(value) for key, value in parsed.totals.items()},
        balanced=parsed.balanced,
        import_batch=batch,
    )
    entries = 0
    for row in parsed.rows:
        PpmSnapshotRow.objects.create(
            snapshot=snapshot,
            project_code=row.code,
            project=row.project,
            total_days=row.total_days,
            import_batch=batch,
        )
        if row.project is None:
            ImportIssue.objects.create(
                batch=batch,
                level=ImportIssueLevel.WARNING,
                entity="ppm_row",
                key=row.code,
                message="Riga non riconosciuta: associare a un progetto esistente o crearne uno.",
            )
            continue
        from domain.residuals import project_balance_qs

        project_bal = project_balance_qs().filter(pk=row.project.pk).first()
        internal = quantize_days(project_bal.total_consumed_days) if project_bal else ZERO
        delta = quantize_days(row.total_days - internal)
        if abs(delta) <= Decimal("0.0100"):
            continue
        entry = TimesheetEntry.objects.create(
            project=row.project,
            period=month_start(parsed.extracted_at.date()),
            days=delta,
            source=TimesheetSource.PPM_IMPORT if delta > ZERO else TimesheetSource.STORNO,
            ppm_snapshot=snapshot,
            note=f"Import PPM {source.name}; delta da {internal} a {row.total_days}",
            import_batch=batch,
        )
        entry.full_clean()
        entries += 1
    dry.entries_created = entries
    dry.batch_id = str(batch.id)
    batch.report = dry.as_dict()
    batch.save(update_fields=["report", "updated_at"])
    run_checks()
    return dry


@transaction.atomic
def rollback_ppm(batch_id) -> dict:
    batch = ImportBatch.objects.select_for_update().get(pk=batch_id)
    if batch.kind not in (ImportKind.PPM_XLSX, ImportKind.PPM_PDF):
        raise ValueError("Il rollback append-only è disponibile solo per batch PPM.")
    if batch.status != ImportStatus.APPLIED:
        raise ValueError("Il batch PPM non è applicato.")
    created = 0
    for entry in TimesheetEntry.objects.filter(import_batch=batch).order_by("created_at"):
        TimesheetEntry.objects.create(
            project=entry.project,
            canone_subactivity=entry.canone_subactivity,
            wallet_allocation=entry.wallet_allocation,
            period=entry.period,
            days=quantize_days(-entry.days),
            source=TimesheetSource.STORNO,
            reverses=entry,
            note=f"Rollback append-only batch PPM {batch.id}",
        )
        created += 1
    batch.status = ImportStatus.ROLLED_BACK
    batch.save(update_fields=["status", "updated_at"])
    run_checks()
    return {"batch_id": str(batch.id), "storni_creati": created}
