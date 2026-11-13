"""Validazione e applicazione del batch dell'estratto operativo settimanale.

Due operazioni distinte, come da docs/importazione_plan.md §11:

- `preview` legge il file, risolve le destinazioni, salva lo staging e il report, e **non**
  crea consuntivi;
- `apply` usa il batch già validato, ricontrolla tutto sotto lock e scrive i movimenti.

L'applicazione è atomica sull'intero workbook: un errore non lascia aggiornamenti parziali.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from canone.models import CanoneSubactivity
from importers.operational_excel import (
    Level,
    ParsedWorkbook,
    Problem,
    Section,
    parse_workbook,
)
from importers.operational_mapping import (
    SECTION_TO_ROW_SECTION,
    SUGGESTION_THRESHOLD,
    Resolution,
    Resolver,
    find_overlaps,
)
from imports.models import (
    ImportBatch,
    ImportIssue,
    ImportIssueLevel,
    ImportKind,
    ImportRowSection,
    ImportRowStatus,
    ImportStatus,
    MappingKind,
    OperationalImportRow,
)
from projects.models import Project, TimesheetStatus
from timesheets.models import TimesheetEntry, TimesheetSource
from wallet.models import AllocationStatus, WalletAllocation

ZERO = Decimal("0.0000")
LOW_RESIDUAL_THRESHOLD = Decimal("0.5")


class ApplyError(Exception):
    """L'applicazione non può procedere. Il messaggio è rivolto all'utente."""


@dataclass
class SectionSummary:
    section: ImportRowSection
    rows_read: int = 0
    rows_ready: int = 0
    rows_to_map: int = 0
    rows_error: int = 0
    total_rows_excluded: int = 0
    days: Decimal = ZERO

    def as_dict(self) -> dict[str, Any]:
        return {
            "sezione": self.section.value,
            "etichetta": self.section.label,
            "righe_lette": self.rows_read,
            "righe_importabili": self.rows_ready,
            "righe_da_associare": self.rows_to_map,
            "righe_in_errore": self.rows_error,
            "righe_di_totale_escluse": self.total_rows_excluded,
            "giornate": str(self.days),
        }


@dataclass
class PreviewResult:
    """Quanto serve alla pagina per mostrare anteprima, console e stato della conferma."""

    batch: ImportBatch
    problems: list[Problem] = field(default_factory=list)
    summaries: list[SectionSummary] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    created_collaborators: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.level is Level.ERROR]

    @property
    def warnings(self) -> list[Problem]:
        return [p for p in self.problems if p.level is Level.WARNING]

    @property
    def can_apply(self) -> bool:
        return not self.errors and self.batch.can_apply

    def as_report(self) -> dict[str, Any]:
        return {
            "tipo": ImportKind.OPERATIONAL_XLSX.value,
            "file": self.batch.source_filename,
            "impronta": self.batch.content_hash,
            "sezioni": [s.as_dict() for s in self.summaries],
            "totale_righe": sum(s.rows_ready for s in self.summaries),
            "totale_giornate": str(sum((s.days for s in self.summaries), ZERO)),
            "problemi": [
                {
                    "livello": p.level.value,
                    "foglio": p.sheet,
                    "cella": p.cell,
                    "riga": p.excel_row,
                    "messaggio": p.message,
                }
                for p in self.problems
            ],
            "collaboratori_censiti": self.created_collaborators,
            # Le associazioni mancanti stanno nel report, non solo nella risposta della
            # preview: riaprendo un batch dallo storico la pagina deve poterle ancora
            # proporre senza ricaricare il file.
            "da_associare": self.candidates,
            "confermabile": self.can_apply,
        }


def content_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def content_fingerprint(parsed: ParsedWorkbook) -> str:
    """Impronta del contenuto normalizzato, indipendente da ordine e formattazione.

    Include foglio, destinazione e numero di occorrenze delle righe, come chiede il §9.2:
    serve a riconoscere lo stesso estratto ripresentato con le righe in ordine diverso,
    che l'hash del file da solo non vedrebbe.
    """
    counter: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    for row in parsed.rows:
        counter[
            (
                row.section.value,
                row.destination_label.casefold(),
                row.collaborator.casefold(),
                row.period.isoformat(),
                str(row.days),
            )
        ] += 1
    digest = hashlib.sha256()
    for key in sorted(counter):
        digest.update("|".join((*key, str(counter[key]))).encode())
        digest.update(b"\n")
    return digest.hexdigest()


# --------------------------------------------------------------------------- preview


@transaction.atomic
def preview(
    *,
    upload,
    filename: str,
    user: User,
    batch: ImportBatch | None = None,
) -> PreviewResult:
    """Analizza il file e salva lo staging. Non crea consuntivi."""
    payload = upload.read() if hasattr(upload, "read") else bytes(upload)
    digest = content_hash(payload)

    if batch is None:
        batch = ImportBatch.objects.create(
            kind=ImportKind.OPERATIONAL_XLSX,
            status=ImportStatus.DRY_RUN,
            source_filename=filename[:255],
            content_hash=digest,
            created_by=user,
            updated_by=user,
        )
        # Il file resta allegato al batch: confermare un'associazione in Riconciliazione
        # obbliga a rifare l'analisi, e chiedere di ricaricare lo stesso file sarebbe
        # un passaggio a vuoto. Serve anche a rendere il batch ispezionabile a posteriori.
        batch.file.save(Path(filename).name, ContentFile(payload), save=True)
    else:
        batch.operational_rows.all().delete()
        batch.issues.all().delete()

    parsed = parse_workbook(BytesIO(payload))
    problems = list(parsed.all_problems)

    resolver = Resolver()
    resolutions = resolver.resolve_all(parsed.rows)
    for resolution in resolutions:
        problems.extend(resolution.problems)

    problems.extend(_overlap_problems(resolutions))
    problems.extend(_capacity_problems(resolutions))

    _store_rows(batch, resolutions)

    result = PreviewResult(
        batch=batch,
        problems=problems,
        summaries=_summaries(parsed, resolutions),
        candidates=_candidates(resolutions),
        created_collaborators=sorted(
            {u.get_full_name() or u.username for u in resolver.created_users}
        ),
    )
    _persist_issues(batch, problems)
    batch.report = result.as_report()
    batch.report["impronta_contenuto"] = content_fingerprint(parsed)
    batch.updated_by = user
    batch.save(update_fields=["report", "updated_by", "updated_at", "version"])
    return result


def _store_rows(batch: ImportBatch, resolutions: list[Resolution]) -> None:
    rows = []
    for resolution in resolutions:
        row = resolution.row
        if resolution.is_ready:
            status = ImportRowStatus.PRONTA
        elif resolution.errors and not resolution.needs_mapping:
            status = ImportRowStatus.ERRORE
        else:
            status = ImportRowStatus.DA_ASSOCIARE
        rows.append(
            OperationalImportRow(
                batch=batch,
                section=SECTION_TO_ROW_SECTION[row.section],
                sheet=row.sheet,
                excel_row=row.excel_row,
                cells=row.cells,
                project_raw=row.project[:400],
                subproject_raw=row.subproject[:400],
                collaborator_raw=row.collaborator[:200],
                period=row.period,
                days=row.days,
                note=row.note[:300],
                project=resolution.project,
                wallet_allocation=resolution.wallet_allocation,
                canone_subactivity=resolution.canone_subactivity,
                author=resolution.author,
                status=status,
                detail="\n".join(p.message for p in resolution.problems),
                created_by=batch.created_by,
                updated_by=batch.updated_by,
            )
        )
    OperationalImportRow.objects.bulk_create(rows)


def _persist_issues(batch: ImportBatch, problems: list[Problem]) -> None:
    ImportIssue.objects.bulk_create(
        [
            ImportIssue(
                batch=batch,
                level=(
                    ImportIssueLevel.ERROR
                    if problem.level is Level.ERROR
                    else ImportIssueLevel.WARNING
                ),
                entity=problem.sheet[:100],
                key=(problem.cell or str(problem.excel_row or ""))[:255],
                message=problem.message,
            )
            for problem in problems
        ]
    )


def _summaries(parsed: ParsedWorkbook, resolutions: list[Resolution]) -> list[SectionSummary]:
    by_section: dict[ImportRowSection, SectionSummary] = {
        SECTION_TO_ROW_SECTION[section]: SectionSummary(SECTION_TO_ROW_SECTION[section])
        for section in Section
    }
    for sheet in parsed.sheets:
        summary = by_section[SECTION_TO_ROW_SECTION[sheet.section]]
        summary.rows_read = sheet.rows_read
        summary.total_rows_excluded = sheet.rows_formula
    for resolution in resolutions:
        summary = by_section[SECTION_TO_ROW_SECTION[resolution.row.section]]
        if resolution.is_ready:
            summary.rows_ready += 1
            summary.days += resolution.row.days
        elif resolution.errors and not resolution.needs_mapping:
            summary.rows_error += 1
        else:
            summary.rows_to_map += 1
    return list(by_section.values())


def _candidates(resolutions: list[Resolution]) -> list[dict[str, Any]]:
    """Le associazioni che la pagina deve far completare, una per valore non agganciato.

    Raggruppate per (tipo, valore, contesto): lo stesso codice ripetuto su cinque righe è
    una sola decisione per l'utente, e una volta confermata vale anche per le settimane
    dopo. Il contesto viaggia con il gruppo perché è parte della chiave del registro
    (`ImportMapping`): senza anno o semestre l'associazione non verrebbe più ritrovata.
    """
    field_to_kind = {
        "project": MappingKind.PROGETTO,
        "wallet_allocation": MappingKind.WALLET_ALLOCATION,
        "canone_subactivity": MappingKind.CANONE_SUBACTIVITY,
        "author": MappingKind.COLLABORATORE,
    }
    grouped: dict[tuple[str, str, int | None, str], dict[str, Any]] = {}
    for resolution in resolutions:
        row = resolution.row
        for field_name, candidates in resolution.candidates.items():
            kind = field_to_kind.get(field_name)
            if kind is None:
                continue
            raw = {
                "project": row.project,
                "wallet_allocation": row.subproject,
                "canone_subactivity": row.subproject,
                "author": row.collaborator,
            }.get(field_name, "")
            year = None if field_name == "author" else resolution.context_year
            semester = "" if field_name == "author" else resolution.context_semester
            key = (kind.value, raw, year, semester)
            group = grouped.get(key)
            if group is None:
                best = candidates[0].score if candidates else 0.0
                group = grouped[key] = {
                    "chiave": "|".join((kind.value, raw, str(year or ""), semester)),
                    "tipo": kind.value,
                    "tipo_etichetta": kind.label,
                    "sezione": SECTION_TO_ROW_SECTION[row.section].value,
                    "valore": raw,
                    "anno": year,
                    "semestre": semester,
                    "righe": [],
                    "suggerito": (
                        candidates[0].id if candidates and best >= SUGGESTION_THRESHOLD else None
                    ),
                    "candidati": [
                        {
                            "id": c.id,
                            "etichetta": c.label,
                            "dettaglio": c.detail,
                            "somiglianza": c.score,
                        }
                        for c in candidates
                    ],
                }
            group["righe"].append(f"{row.sheet}!{row.excel_row}")
    return sorted(grouped.values(), key=lambda g: (g["tipo"], g["valore"]))


def _overlap_problems(resolutions: list[Resolution]) -> list[Problem]:
    problems: list[Problem] = []
    overlaps = find_overlaps(resolutions)
    for resolution in resolutions:
        row = resolution.row
        found = overlaps.get((row.sheet, row.excel_row))
        if not found:
            continue
        incoming = (
            resolution.author.get_full_name() or resolution.author.username
            if resolution.author
            else row.collaborator
        )
        for overlap in found:
            problems.append(
                Problem(
                    Level.WARNING,
                    overlap.describe(incoming),
                    sheet=row.sheet,
                    cell=row.cell_of("days"),
                    excel_row=row.excel_row,
                )
            )
    return problems


# ------------------------------------------------------------------------- capienze


@dataclass
class _Capacity:
    """Capienza di una destinazione, con il cumulato del batch già sommato."""

    label: str
    limit: Decimal
    consumed: Decimal
    incoming: Decimal = ZERO

    @property
    def residual_before(self) -> Decimal:
        return self.limit - self.consumed

    @property
    def residual_after(self) -> Decimal:
        return self.limit - self.consumed - self.incoming

    @property
    def exceeded(self) -> bool:
        return self.residual_after < ZERO


def _capacity_problems(resolutions: list[Resolution]) -> list[Problem]:
    """Capienze calcolate sul cumulato del batch, non riga per riga (§10).

    Riga per riga sei movimenti da 1,5 gg passerebbero singolarmente e sfonderebbero il
    budget insieme; lo stesso foglio porta più righe sulla medesima destinazione.
    """
    problems: list[Problem] = []
    projects: dict[Any, _Capacity] = {}
    allocations: dict[Any, _Capacity] = {}
    subactivities: dict[Any, _Capacity] = {}
    rows_by_target: dict[tuple[str, Any], list[Resolution]] = defaultdict(list)

    for resolution in resolutions:
        if resolution.errors and not resolution.needs_mapping:
            continue
        if (project := resolution.project) is not None:
            capacity = projects.setdefault(project.pk, _project_capacity(project))
            capacity.incoming += resolution.row.days
            rows_by_target[("project", project.pk)].append(resolution)
        elif (allocation := resolution.wallet_allocation) is not None:
            capacity = allocations.setdefault(allocation.pk, _allocation_capacity(allocation))
            capacity.incoming += resolution.row.days
            rows_by_target[("allocation", allocation.pk)].append(resolution)
        elif (subactivity := resolution.canone_subactivity) is not None:
            capacity = subactivities.setdefault(subactivity.pk, _subactivity_capacity(subactivity))
            capacity.incoming += resolution.row.days
            rows_by_target[("subactivity", subactivity.pk)].append(resolution)
            problems.extend(_window_problems(resolution, subactivity))

    for kind, bucket in (
        ("project", projects),
        ("allocation", allocations),
        ("subactivity", subactivities),
    ):
        for target_id, capacity in bucket.items():
            group = rows_by_target[(kind, target_id)]
            anchor = group[0].row if group else None
            if capacity.exceeded:
                problems.append(
                    Problem(
                        Level.ERROR,
                        f"Capienza superata \u2014 {capacity.label}: il batch porta "
                        f"{capacity.incoming} gg ma il "
                        f"residuo è {capacity.residual_before} gg "
                        f"({capacity.limit} disponibili, {capacity.consumed} già usate).",
                        sheet=anchor.sheet if anchor else "",
                        cell=anchor.cell_of("days") if anchor else "",
                        excel_row=anchor.excel_row if anchor else None,
                    )
                )
            elif ZERO <= capacity.residual_after < LOW_RESIDUAL_THRESHOLD:
                problems.append(
                    Problem(
                        Level.WARNING,
                        f"{capacity.label}: dopo l'applicazione resta "
                        f"{capacity.residual_after} gg di residuo.",
                        sheet=anchor.sheet if anchor else "",
                        cell=anchor.cell_of("days") if anchor else "",
                        excel_row=anchor.excel_row if anchor else None,
                    )
                )
    return problems


def _project_capacity(project: Project) -> _Capacity:
    consumed = (
        TimesheetEntry.objects.filter(project=project).aggregate(total=Sum("days"))["total"] or ZERO
    )
    allocated = project.wallet_allocations.aggregate(total=Sum("allocated_days"))["total"] or ZERO
    return _Capacity(
        label=f"Progetto {project.code}",
        limit=project.budget_days,
        consumed=consumed + allocated,
    )


def _allocation_capacity(allocation: WalletAllocation) -> _Capacity:
    consumed = allocation.timesheet_entries.aggregate(total=Sum("days"))["total"] or ZERO
    return _Capacity(
        label=f"Allocazione {allocation.activity.title}",
        limit=allocation.allocated_days,
        consumed=consumed,
    )


def _subactivity_capacity(subactivity: CanoneSubactivity) -> _Capacity:
    consumed = subactivity.timesheet_entries.aggregate(total=Sum("days"))["total"] or ZERO
    return _Capacity(
        label=f"Attività {subactivity.title}",
        limit=subactivity.reserved_days,
        consumed=consumed,
    )


def _window_problems(resolution: Resolution, subactivity: CanoneSubactivity) -> list[Problem]:
    """Finestra temporale dell'attività del canone: vincolo che solo questa sezione ha."""
    period = resolution.row.period
    start, end = subactivity.start_date, subactivity.end_date
    if (start and period < start) or (end and period > end):
        ammesso = " - ".join(d.strftime("%d/%m/%Y") for d in (start, end) if d is not None)
        return [
            Problem(
                Level.ERROR,
                f"Data fuori dal periodo dell'attività '{subactivity.title}' "
                f"(ammesso: {ammesso or 'non dichiarato'}).",
                sheet=resolution.row.sheet,
                cell=resolution.row.cell_of("period"),
                excel_row=resolution.row.excel_row,
            )
        ]
    return []


# ----------------------------------------------------------------------------- apply


@transaction.atomic
def apply_batch(*, batch_id: Any, user: User) -> ImportBatch:
    """Scrive i consuntivi del batch. Atomica: un errore non lascia nulla a metà."""
    batch = (
        ImportBatch.objects.select_for_update()
        .filter(pk=batch_id, kind=ImportKind.OPERATIONAL_XLSX)
        .first()
    )
    if batch is None:
        raise ApplyError("Batch non trovato.")
    if batch.status == ImportStatus.APPLIED:
        raise ApplyError("Questo batch è già stato applicato: ricaricare il file per ripetere.")
    if not batch.can_apply:
        raise ApplyError(f"Batch in stato {batch.get_status_display()}: non applicabile.")

    duplicate = (
        ImportBatch.objects.filter(
            kind=ImportKind.OPERATIONAL_XLSX,
            status=ImportStatus.APPLIED,
            content_hash=batch.content_hash,
        )
        .exclude(pk=batch.pk)
        .first()
    )
    if duplicate is not None:
        raise ApplyError(
            f"Lo stesso file è già stato applicato il "
            f"{timezone.localtime(duplicate.applied_at):%d/%m/%Y %H:%M}."
            if duplicate.applied_at
            else "Lo stesso file è già stato applicato."
        )

    # `of=("self",)` è obbligatorio, non un'ottimizzazione: le tre destinazioni sono FK
    # nullable, quindi `select_related` genera LEFT OUTER JOIN e PostgreSQL rifiuta
    # "FOR UPDATE cannot be applied to the nullable side of an outer join". Si blocca
    # soltanto la tabella delle righe, che è l'unica che serve bloccare qui.
    rows = list(
        batch.operational_rows.select_for_update(of=("self",))
        .select_related("project", "wallet_allocation", "canone_subactivity", "author")
        .all()
    )
    if not rows:
        raise ApplyError("Nessuna riga da importare: rieseguire l'analisi del file.")
    blocked = [row for row in rows if row.status != ImportRowStatus.PRONTA]
    if blocked:
        raise ApplyError(
            f"{len(blocked)} righe non sono pronte: completare le associazioni o "
            "correggere il file."
        )

    _recheck_targets(rows)
    created = _create_entries(batch, rows, user)
    _sync_wallet(rows)

    batch.status = ImportStatus.APPLIED
    batch.applied_by = user
    batch.applied_at = timezone.now()
    batch.updated_by = user
    batch.report = {
        **(batch.report or {}),
        "applicato": {
            "movimenti": len(created),
            "giornate": str(sum((entry.days for entry in created), ZERO)),
            "operatore": user.get_full_name() or user.username,
            "istante": batch.applied_at.isoformat(),
        },
    }
    batch.save(
        update_fields=[
            "status",
            "applied_by",
            "applied_at",
            "report",
            "updated_by",
            "updated_at",
            "version",
        ]
    )
    return batch


def _recheck_targets(rows: list[OperationalImportRow]) -> None:
    """Ricontrolla sotto lock stato delle destinazioni e capienze cumulative."""
    projects: dict[Any, Decimal] = defaultdict(lambda: ZERO)
    allocations: dict[Any, Decimal] = defaultdict(lambda: ZERO)
    subactivities: dict[Any, Decimal] = defaultdict(lambda: ZERO)

    for row in rows:
        if row.project_id:
            projects[row.project_id] += row.days
        elif row.wallet_allocation_id:
            allocations[row.wallet_allocation_id] += row.days
        elif row.canone_subactivity_id:
            subactivities[row.canone_subactivity_id] += row.days
        else:
            raise ApplyError(f"Riga {row.sheet}!{row.excel_row} senza destinazione risolta.")
        if row.author_id is None:
            raise ApplyError(f"Riga {row.sheet}!{row.excel_row} senza autore risolto.")

    for project in Project.objects.select_for_update().filter(pk__in=projects):
        if project.timesheet_status == TimesheetStatus.CHIUSO:
            raise ApplyError(f"Progetto {project.code} chiuso: non accetta consuntivi diretti.")
        capacity = _project_capacity(project)
        capacity.incoming = projects[project.pk]
        if capacity.exceeded:
            raise ApplyError(
                f"{capacity.label}: {capacity.incoming} gg da importare oltre il residuo "
                f"di {capacity.residual_before} gg."
            )

    for allocation in (
        WalletAllocation.objects.select_for_update(of=("self",))
        .select_related("activity")
        .filter(pk__in=allocations)
    ):
        if allocation.status == AllocationStatus.CHIUSA:
            raise ApplyError(
                f"Allocazione {allocation.activity.title} chiusa: riaprirla per consuntivare."
            )
        capacity = _allocation_capacity(allocation)
        capacity.incoming = allocations[allocation.pk]
        if capacity.exceeded:
            raise ApplyError(
                f"{capacity.label}: {capacity.incoming} gg da importare oltre il residuo "
                f"di {capacity.residual_before} gg."
            )

    for subactivity in CanoneSubactivity.objects.select_for_update().filter(pk__in=subactivities):
        capacity = _subactivity_capacity(subactivity)
        capacity.incoming = subactivities[subactivity.pk]
        if capacity.exceeded:
            raise ApplyError(
                f"{capacity.label}: {capacity.incoming} gg da importare oltre il residuo "
                f"di {capacity.residual_before} gg."
            )
        for row in rows:
            if row.canone_subactivity_id != subactivity.pk:
                continue
            start, end = subactivity.start_date, subactivity.end_date
            if (start and row.period < start) or (end and row.period > end):
                raise ApplyError(
                    f"Riga {row.sheet}!{row.excel_row}: data fuori dal periodo "
                    f"dell'attività {subactivity.title}."
                )


def _create_entries(
    batch: ImportBatch, rows: list[OperationalImportRow], user: User
) -> list[TimesheetEntry]:
    created: list[TimesheetEntry] = []
    for row in rows:
        entry = TimesheetEntry(
            project=row.project,
            wallet_allocation=row.wallet_allocation,
            canone_subactivity=row.canone_subactivity,
            period=row.period,
            days=row.days,
            source=TimesheetSource.EXCEL_IMPORT,
            note=row.note,
            created_by=row.author,
            updated_by=user,
            import_batch=batch,
        )
        entry.full_clean(exclude=["import_batch"])
        entry.save()
        row.entry = entry
        created.append(entry)
    OperationalImportRow.objects.bulk_update(rows, ["entry"])
    return created


def _sync_wallet(rows: list[OperationalImportRow]) -> None:
    from wallet.services import sync_allocation_funding

    allocation_ids = {row.wallet_allocation_id for row in rows if row.wallet_allocation_id}
    for allocation in WalletAllocation.objects.filter(pk__in=allocation_ids):
        sync_allocation_funding(allocation)
