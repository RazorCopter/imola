"""Report di un import: cosa è stato creato, aggiornato, lasciato stare o scartato.

Lo stesso oggetto serve al dry-run e all'applicazione: è la prova che le due strade fanno
le stesse cose, perché il codice che le produce è uno solo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


def _jsonable(value: Any) -> Any:
    """I report finiscono in un JSONField: i Decimal diventano stringhe, non float."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@dataclass
class EntityReport:
    """Esito per un tipo di entità."""

    entity: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    created_keys: list[str] = field(default_factory=list)
    updated_rows: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def touched(self) -> int:
        return self.created + self.updated + self.unchanged

    def as_dict(self) -> dict[str, Any]:
        return {
            "creati": self.created,
            "aggiornati": self.updated,
            "invariati": self.unchanged,
            "scartati": len(self.skipped),
            "errori": len(self.errors),
            "totale_considerati": self.touched + len(self.skipped) + len(self.errors),
            "chiavi_create": self.created_keys[:200],
            "dettaglio_aggiornati": _jsonable(self.updated_rows[:200]),
            "dettaglio_scartati": _jsonable(self.skipped[:200]),
            "dettaglio_errori": _jsonable(self.errors[:200]),
        }


@dataclass
class ImportReport:
    kind: str
    source_filename: str = ""
    schema_version: str = ""
    reference_date: Any = None
    dry_run: bool = True
    entities: dict[str, EntityReport] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)

    def entity(self, name: str) -> EntityReport:
        return self.entities.setdefault(name, EntityReport(entity=name))

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def fail(self, message: str) -> None:
        self.errors.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors and all(not entity.errors for entity in self.entities.values())

    @property
    def created_total(self) -> int:
        return sum(entity.created for entity in self.entities.values())

    @property
    def updated_total(self) -> int:
        return sum(entity.updated for entity in self.entities.values())

    def counts(self) -> dict[str, int]:
        """Conteggi per entità, la tabella che si guarda al checkpoint."""
        return {name: entity.created for name, entity in self.entities.items()}

    def as_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.kind,
            "file": self.source_filename,
            "schema_version": self.schema_version,
            "data_riferimento_dati": _jsonable(self.reference_date),
            "simulazione": self.dry_run,
            "esito": "ok" if self.ok else "errori",
            "riepilogo": {
                "creati": self.created_total,
                "aggiornati": self.updated_total,
                "invariati": sum(e.unchanged for e in self.entities.values()),
                "scartati": sum(len(e.skipped) for e in self.entities.values()),
                "errori": len(self.errors) + sum(len(e.errors) for e in self.entities.values()),
            },
            "entita": {name: entity.as_dict() for name, entity in self.entities.items()},
            "avvisi": self.warnings,
            "errori_globali": self.errors,
            "totali_calcolati": _jsonable(self.totals),
        }

    def render_text(self) -> str:
        """Versione leggibile a terminale, usata da manage.py import_seed."""
        lines = [
            f"Import {self.kind} - {'SIMULAZIONE' if self.dry_run else 'APPLICATO'}",
            f"File: {self.source_filename or '-'}",
            f"Schema: {self.schema_version}   Dati al: {_jsonable(self.reference_date)}",
            "",
            f"{'Entità':<28}{'creati':>8}{'aggiorn.':>10}{'invar.':>8}{'scart.':>8}{'err.':>6}",
            "-" * 68,
        ]
        for name, entity in self.entities.items():
            lines.append(
                f"{name:<28}{entity.created:>8}{entity.updated:>10}"
                f"{entity.unchanged:>8}{len(entity.skipped):>8}{len(entity.errors):>6}"
            )
        lines.append("-" * 68)
        lines.append(
            f"{'TOTALE':<28}{self.created_total:>8}{self.updated_total:>10}"
            f"{sum(e.unchanged for e in self.entities.values()):>8}"
            f"{sum(len(e.skipped) for e in self.entities.values()):>8}"
            f"{sum(len(e.errors) for e in self.entities.values()):>6}"
        )

        if self.totals:
            lines += ["", "Totali calcolati dal file:"]
            for key, value in self.totals.items():
                lines.append(f"  - {key}: {_jsonable(value)}")

        for title, items in (("Scartati", self._all_skipped()), ("Avvisi", self.warnings)):
            if items:
                lines += ["", f"{title} ({len(items)}):"]
                lines += [f"  - {item}" for item in items[:40]]
                if len(items) > 40:
                    lines.append(f"  ... e altri {len(items) - 40}")

        if not self.ok:
            lines += ["", "ERRORI:"]
            lines += [f"  - {error}" for error in self.errors]
            for name, entity in self.entities.items():
                for error in entity.errors:
                    lines.append(f"  - [{name}] {error}")

        return "\n".join(lines)

    def _all_skipped(self) -> list[str]:
        rows: list[str] = []
        for name, entity in self.entities.items():
            for skipped in entity.skipped:
                rows.append(f"[{name}] {skipped.get('chiave', '?')}: {skipped.get('motivo', '')}")
        return rows
