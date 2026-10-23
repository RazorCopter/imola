"""R6 — riconciliazione con il PPM.

Il PPM è la fonte di verità dei consuntivi: la riconciliazione confronta il totale interno
(consuntivi diretti + consumi via wallet) con il valore `gg_totali` dell'ultimo snapshot
disponibile per quel progetto. Un delta oltre la tolleranza (default 0,01 gg) è un'anomalia.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Max

from domain.money import ZERO, format_days_it, is_within_tolerance, quantize_days
from domain.residuals import project_balance_qs

DEFAULT_TOLERANCE = Decimal("0.0100")


class ReconciliationStatus:
    """Stato autorevole del confronto esposto da API e GUI."""

    ALLINEATO = "ALLINEATO"
    NON_ALLINEATO = "NON_ALLINEATO"
    PARZIALE = "PARZIALE"
    NON_VERIFICABILE = "NON_VERIFICABILE"


class ReconciliationDataStatus:
    """Disponibilità dei dati necessaria a interpretare KPI e delta."""

    DISPONIBILI = "DISPONIBILI"
    SNAPSHOT_ASSENTE = "SNAPSHOT_ASSENTE"
    NESSUNA_RIGA_CONFRONTABILE = "NESSUNA_RIGA_CONFRONTABILE"


@dataclass
class ReconciliationRow:
    """Vista calcolata `reconciliation` (par. 3.2)."""

    project_code: str
    project_name: str | None
    project_id: object
    internal_days: Decimal
    ppm_days: Decimal | None
    delta: Decimal | None
    within_tolerance: bool | None
    snapshot_id: object | None
    snapshot_extracted_at: object | None
    missing_in_ppm: bool
    suggested_action: str

    @property
    def outcome(self) -> str:
        if self.missing_in_ppm:
            return "ASSENTE_IN_PPM"
        return "OK" if self.within_tolerance else "KO"

    def as_dict(self) -> dict:
        return {
            "codice_progetto": self.project_code,
            "nome_progetto": self.project_name,
            "progetto_id": self.project_id,
            "interno": self.internal_days,
            "ppm": self.ppm_days,
            "delta": self.delta,
            "esito": self.outcome,
            "snapshot_id": self.snapshot_id,
            "snapshot_estratto_il": self.snapshot_extracted_at,
            "azione_suggerita": self.suggested_action,
        }

    @property
    def explanation(self) -> str:
        if self.ppm_days is None:
            return "Nessuna riga PPM per questo progetto nell'ultimo estratto."
        return (
            f"Delta = {format_days_it(self.internal_days)} (interno) "
            f"- {format_days_it(self.ppm_days)} (PPM) = {format_days_it(self.delta or ZERO)}"
        )


def latest_rows_by_project(kinds: tuple[str, ...] | None = None) -> dict:
    """Ultima riga PPM per ciascun progetto, fra gli snapshot dei tipi indicati."""
    from ppm.models import PpmSnapshotRow

    rows = PpmSnapshotRow.objects.filter(project__isnull=False).select_related("snapshot")
    if kinds:
        rows = rows.filter(snapshot__kind__in=kinds)
    latest: dict[object, PpmSnapshotRow] = {}
    for row in rows.order_by("snapshot__extracted_at"):
        latest[row.project_id] = row  # l'ultimo vince, essendo ordinato per data
    return latest


def reconcile(
    *, tolerance: Decimal | None = None, kinds: tuple[str, ...] | None = None
) -> list[ReconciliationRow]:
    """Confronta ogni progetto con l'ultimo dato PPM disponibile."""
    tolerance = tolerance if tolerance is not None else DEFAULT_TOLERANCE
    latest = latest_rows_by_project(kinds)

    result: list[ReconciliationRow] = []
    for project in project_balance_qs().order_by("code"):
        internal = quantize_days(project.total_consumed_days)
        row = latest.get(project.id)
        if row is None or row.total_days is None:
            result.append(
                ReconciliationRow(
                    project_code=project.code,
                    project_name=project.title or None,
                    project_id=project.id,
                    internal_days=internal,
                    ppm_days=None,
                    delta=None,
                    within_tolerance=None,
                    snapshot_id=None,
                    snapshot_extracted_at=None,
                    missing_in_ppm=True,
                    suggested_action=(
                        "Verificare con Imola: il progetto non compare nell'estratto PPM."
                        if internal > 0
                        else "Nessun consuntivo interno: nulla da riconciliare."
                    ),
                )
            )
            continue

        ppm_days = quantize_days(row.total_days)
        delta = quantize_days(internal - ppm_days)
        ok = is_within_tolerance(delta, tolerance)
        result.append(
            ReconciliationRow(
                project_code=project.code,
                project_name=project.title or None,
                project_id=project.id,
                internal_days=internal,
                ppm_days=ppm_days,
                delta=delta,
                within_tolerance=ok,
                snapshot_id=row.snapshot_id,
                snapshot_extracted_at=row.snapshot.extracted_at,
                missing_in_ppm=False,
                suggested_action=(
                    ""
                    if ok
                    else (
                        "Allineare i consuntivi importando l'estratto PPM aggiornato: "
                        f"differenza di {format_days_it(abs(delta))}."
                    )
                ),
            )
        )
    return result


def latest_snapshot(kind: str | None = None):
    """Ultimo snapshot importato, per tipo."""
    from ppm.models import PpmSnapshot

    qs = PpmSnapshot.objects.all()
    if kind:
        qs = qs.filter(kind=kind)
    return qs.order_by("-extracted_at").first()


def reconciliation_summary(
    tolerance: Decimal | None = None, *, rows: list[ReconciliationRow] | None = None
) -> dict:
    """Riepilogo con stato esplicito; KPI non valorizzati se il confronto è impossibile."""
    snapshot = latest_snapshot()
    all_rows = rows if rows is not None else reconcile(tolerance=tolerance)
    # Le righe senza dato PPM e senza consuntivo interno non costituiscono un confronto utile.
    rows = [row for row in all_rows if row.internal_days or row.ppm_days is not None]
    comparable = [row for row in rows if row.delta is not None]
    deltas = [row.delta for row in comparable if row.delta is not None]
    ok_count = sum(1 for row in comparable if row.outcome == "OK")
    ko_count = sum(1 for row in comparable if row.outcome == "KO")
    missing_count = sum(1 for row in rows if row.missing_in_ppm)

    if snapshot is None:
        status = ReconciliationStatus.NON_VERIFICABILE
        data_status = ReconciliationDataStatus.SNAPSHOT_ASSENTE
    elif not comparable:
        status = ReconciliationStatus.NON_VERIFICABILE
        data_status = ReconciliationDataStatus.NESSUNA_RIGA_CONFRONTABILE
    elif missing_count:
        status = ReconciliationStatus.PARZIALE
        data_status = ReconciliationDataStatus.DISPONIBILI
    elif ko_count:
        status = ReconciliationStatus.NON_ALLINEATO
        data_status = ReconciliationDataStatus.DISPONIBILI
    else:
        status = ReconciliationStatus.ALLINEATO
        data_status = ReconciliationDataStatus.DISPONIBILI

    # Il denominatore comprende solo confronti realmente eseguiti. In assenza di questi il KPI
    # resta nullo: zero per cento suggerirebbe erroneamente un confronto avvenuto.
    aligned_pct = (
        quantize_days(Decimal(ok_count) / Decimal(len(comparable)) * 100) if comparable else None
    )
    return {
        "stato": status,
        "stato_dati": data_status,
        "snapshot_id": snapshot.id if snapshot else None,
        "snapshot_estratto_il": snapshot.extracted_at if snapshot else None,
        "righe": len(rows),
        "righe_confrontabili": len(comparable),
        "ok": ok_count,
        "ko": ko_count,
        "assenti_in_ppm": missing_count,
        "delta_totale": quantize_days(sum(deltas, ZERO)) if deltas else None,
        "delta_massimo": max((abs(delta) for delta in deltas), default=None),
        "percentuale_allineati": aligned_pct,
    }


def unmatched_ppm_rows(snapshot_id=None):
    """Righe PPM senza progetto associato: finiscono nella coda di revisione."""
    from ppm.models import PpmSnapshotRow

    rows = PpmSnapshotRow.objects.filter(project__isnull=True, canone_subactivity__isnull=True)
    if snapshot_id is not None:
        return rows.filter(snapshot_id=snapshot_id)
    newest = PpmSnapshotRow.objects.aggregate(latest=Max("snapshot__extracted_at"))["latest"]
    if newest is None:
        return rows.none()
    return rows.filter(snapshot__extracted_at=newest)
