"""Parser dell'estratto operativo settimanale in formato xlsx.

Legge i tre fogli `Progetti`, `Wallet` e `Organico_Allargato` e restituisce righe
normalizzate più l'elenco dei problemi, ciascuno con il riferimento di cella in notazione
Excel. Nessuna dipendenza da Django: il modulo è verificabile da solo, senza database.

Scelte vincolate dal formato reale (vedi docs/importazione_plan.md §8):

- le stringhe sono *inline*, il workbook non ha `sharedStrings.xml`: si usa openpyxl, che
  gestisce entrambe le forme, e si legge `cell.value`;
- `data_only=False`, perché le formule di totale non hanno valore in cache e la cache non
  va comunque usata: i totali si ricalcolano sommando le righe importabili;
- la colonna `gg tot` è formattata in contabile a due decimali, quindi il valore mostrato
  non è quello contenuto: `0,38` sta per `0,375`. Si legge sempre il valore grezzo.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, DecimalException, InvalidOperation
from enum import StrEnum
from typing import Any

from openpyxl import load_workbook  # type: ignore[import-untyped]
from openpyxl.cell.cell import Cell  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]
from openpyxl.worksheet.worksheet import Worksheet  # type: ignore[import-untyped]

# Allineato a core.fields.DaysField = Decimal(8, 4). Qui ripetuto per non importare Django.
DAYS_DECIMAL_PLACES = 4
DAYS_QUANTUM = Decimal(1).scaleb(-DAYS_DECIMAL_PLACES)
DAYS_MAX = Decimal("9999.9999")
NOTE_MAX_LENGTH = 300

_SPACES = re.compile(r"\s+")
# Epoca di Excel su Windows: il seriale 1 è il 01/01/1900, con il bug dell'anno bisestile.
_EXCEL_EPOCH = dt.date(1899, 12, 30)


class Level(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class Section(StrEnum):
    """Le tre sezioni applicative alimentate dal workbook."""

    PROGETTI = "PROGETTI"
    WALLET = "WALLET"
    ORGANICO = "ORGANICO"

    @property
    def label(self) -> str:
        return {
            Section.PROGETTI: "Progetti",
            Section.WALLET: "Wallet",
            Section.ORGANICO: "Organico allargato",
        }[self]


def normalize_key(value: Any) -> str:
    """Chiave di confronto per intestazioni e nomi di foglio: senza spazi, accenti, case.

    Togliere tutti gli spazi è ciò che rende `Sotto progetto` e `Sottoprogetto`
    equivalenti, come richiede TEMPLATE.md.
    """
    text = "" if value is None else str(value)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"[\s_]+", "", text).strip().lower()


# Intestazioni attese per sezione. La chiave è normalizzata, il valore è il campo interno.
_COLUMNS: dict[Section, dict[str, str]] = {
    Section.PROGETTI: {
        "progetto": "project",
        "collaboratore": "collaborator",
        "data": "period",
        "note": "note",
        "ggtot": "days",
    },
    Section.WALLET: {
        "progetto": "project",
        "sottoprogetto": "subproject",
        "collaboratore": "collaborator",
        "data": "period",
        "note": "note",
        "ggtot": "days",
    },
    Section.ORGANICO: {
        "sottoprogetto": "subproject",
        "collaboratore": "collaborator",
        "data": "period",
        "note": "note",
        "ggtot": "days",
    },
}

# Nomi di foglio accettati, normalizzati. `Progetto` è alias di `Progetti` (§2.1).
_SHEET_ALIASES: dict[str, Section] = {
    "progetti": Section.PROGETTI,
    "progetto": Section.PROGETTI,
    "wallet": Section.WALLET,
    "organicoallargato": Section.ORGANICO,
}

_REQUIRED_FIELDS = {"collaborator", "period", "note", "days"}

# Come l'intestazione va scritta nell'Excel, per i messaggi rivolti all'utente.
_HEADER_LABELS = {
    "project": "Progetto",
    "subproject": "Sottoprogetto",
    "collaborator": "Collaboratore",
    "period": "Data",
    "note": "Note",
    "days": "gg tot",
}


@dataclass(frozen=True)
class Problem:
    """Un errore o un avviso, ancorato a una cella quando la cella è identificabile."""

    level: Level
    message: str
    sheet: str = ""
    cell: str = ""
    excel_row: int | None = None

    @property
    def location(self) -> str:
        if self.sheet and self.cell:
            return f"{self.sheet}!{self.cell}"
        if self.sheet and self.excel_row:
            return f"{self.sheet}!{self.excel_row}"
        return self.sheet

    def __str__(self) -> str:
        where = self.location
        prefix = f"{self.level.value} {where}" if where else self.level.value
        return f"{prefix}: {self.message}"


@dataclass(frozen=True)
class SourceRow:
    """Riga informativa normalizzata, pronta per la risoluzione delle destinazioni.

    I campi `*_cell` servono alla console: un problema rilevato a valle del parser, per
    esempio una destinazione non agganciata, deve poter indicare la cella esatta.
    """

    section: Section
    sheet: str
    excel_row: int
    period: dt.date
    days: Decimal
    note: str
    collaborator: str
    project: str = ""
    subproject: str = ""
    cells: dict[str, str] = field(default_factory=dict)

    def cell_of(self, field_name: str) -> str:
        return self.cells.get(field_name, "")

    @property
    def destination_label(self) -> str:
        """Come la destinazione si presenta nell'Excel, per l'anteprima."""
        if self.section is Section.PROGETTI:
            return self.project
        if self.section is Section.WALLET:
            return f"{self.project} / {self.subproject}" if self.project else self.subproject
        return self.subproject


@dataclass
class SheetResult:
    """Esito della lettura di un foglio."""

    section: Section
    sheet: str
    rows: list[SourceRow] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    rows_read: int = 0
    rows_empty: int = 0
    rows_formula: int = 0

    @property
    def rows_valid(self) -> int:
        return len(self.rows)

    @property
    def days_total(self) -> Decimal:
        """Somma delle righe importabili. Mai letta dalla cache delle formule (§8.3)."""
        return sum((row.days for row in self.rows), Decimal(0))

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.level is Level.ERROR]

    @property
    def warnings(self) -> list[Problem]:
        return [p for p in self.problems if p.level is Level.WARNING]


@dataclass
class ParsedWorkbook:
    """Risultato completo del parsing, una voce per sezione riconosciuta."""

    sheets: list[SheetResult] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)

    def sheet(self, section: Section) -> SheetResult | None:
        return next((s for s in self.sheets if s.section is section), None)

    @property
    def rows(self) -> list[SourceRow]:
        return [row for sheet in self.sheets for row in sheet.rows]

    @property
    def all_problems(self) -> list[Problem]:
        return [*self.problems, *(p for sheet in self.sheets for p in sheet.problems)]

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.all_problems if p.level is Level.ERROR]

    @property
    def warnings(self) -> list[Problem]:
        return [p for p in self.all_problems if p.level is Level.WARNING]

    @property
    def has_errors(self) -> bool:
        return any(p.level is Level.ERROR for p in self.all_problems)

    @property
    def days_total(self) -> Decimal:
        return sum((sheet.days_total for sheet in self.sheets), Decimal(0))


class WorkbookStructureError(Exception):
    """Il file non è un estratto operativo: manca tutto, non solo qualche dato."""


def parse_days(value: Any) -> tuple[Decimal, str]:
    """Normalizza `gg tot`. Torna (giornate, avviso); solleva ValueError se inutilizzabile.

    Accetta numeri nativi e stringhe con virgola o punto decimale. Il passaggio per `str`
    sul float è voluto: `Decimal(str(0.375))` dà `0.375`, mentre `Decimal(0.375)`
    trascinerebbe la rappresentazione binaria.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("Giornate mancanti.")
    if isinstance(value, bool):
        raise ValueError("Giornate non numeriche.")
    if isinstance(value, Decimal):
        raw = value
    elif isinstance(value, int):
        raw = Decimal(value)
    elif isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("Giornate non finite.")
        raw = Decimal(str(value))
    elif isinstance(value, str):
        text = _SPACES.sub("", value).replace(",", ".")
        try:
            raw = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"Giornate non numeriche: {value!r}.") from exc
    else:
        raise ValueError(f"Giornate non numeriche: {value!r}.")

    if not raw.is_finite():
        raise ValueError("Giornate non finite.")
    if raw <= 0:
        raise ValueError(f"Le giornate devono essere maggiori di zero, trovato {raw}.")
    if raw > DAYS_MAX:
        raise ValueError(f"Giornate fuori scala: {raw} oltre il massimo {DAYS_MAX}.")

    try:
        # Mezzo arrotondato per eccesso: convenzione contabile, non il banker's rounding
        # che Decimal usa per difetto e che darebbe 0,1234 per 0,12345.
        days = raw.quantize(DAYS_QUANTUM, rounding=ROUND_HALF_UP)
    except DecimalException as exc:  # pragma: no cover - coperto dal controllo DAYS_MAX
        raise ValueError(f"Giornate non rappresentabili: {raw}.") from exc
    warning = ""
    if days != raw:
        warning = (
            f"Giornate arrotondate da {raw} a {days}: "
            f"la precisione applicativa è di {DAYS_DECIMAL_PLACES} decimali."
        )
    return days, warning


def parse_period(value: Any) -> dt.date:
    """Normalizza la data. Solleva ValueError: mai ripiegare sulla data odierna (§5.2)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("Data mancante.")
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, bool):
        raise ValueError("Data non valida.")
    if isinstance(value, (int, float, Decimal)):
        # Seriale Excel in una cella senza formato data: openpyxl non lo converte.
        serial = int(value)
        if serial <= 0 or serial > 2_958_465:  # 31/12/9999
            raise ValueError(f"Data non valida: seriale {value!r} fuori intervallo.")
        return _EXCEL_EPOCH + dt.timedelta(days=serial)
    if isinstance(value, str):
        return _parse_date_text(value)
    raise ValueError(f"Data non valida: {value!r}.")


# Costruite a mano invece che con strptime: la data di competenza è naive per natura e
# strptime senza fuso fa scattare la regola DTZ del linter.
_ISO_DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_IT_DATE = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})")


def _parse_date_text(value: str) -> dt.date:
    text = _SPACES.sub("", value)
    if match := _ISO_DATE.fullmatch(text):
        year, month, day = (int(g) for g in match.groups())
    elif match := _IT_DATE.fullmatch(text):
        day, month, raw_year = (int(g) for g in match.groups())
        year = raw_year + 2000 if raw_year < 100 else raw_year
    else:
        raise ValueError(f"Data non leggibile: {value!r}.")
    try:
        return dt.date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"Data inesistente: {value!r}.") from exc


def _is_formula(cell: Cell) -> bool:
    if cell.data_type == "f":
        return True
    return isinstance(cell.value, str) and cell.value.startswith("=")


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _SPACES.sub(" ", str(value)).strip()


def _map_headers(sheet: Worksheet, section: Section) -> tuple[dict[str, int], list[Problem]]:
    """Abbina le colonne per nome, non per posizione. Torna (campo -> indice, problemi)."""
    expected = _COLUMNS[section]
    header_cells: Sequence[Cell] = next(sheet.iter_rows(min_row=1, max_row=1), ())
    mapping: dict[str, int] = {}
    problems: list[Problem] = []
    seen: dict[str, str] = {}
    for cell in header_cells:
        key = normalize_key(cell.value)
        if not key:
            continue
        internal = expected.get(key)
        if internal is None:
            continue
        if internal in seen:
            problems.append(
                Problem(
                    Level.ERROR,
                    f"Colonna '{_clean_text(cell.value)}' duplicata: già vista in "
                    f"{seen[internal]}.",
                    sheet=sheet.title,
                    cell=cell.coordinate,
                    excel_row=1,
                )
            )
            continue
        seen[internal] = cell.coordinate
        mapping[internal] = cell.column  # 1-based

    missing = sorted(_REQUIRED_FIELDS - set(mapping))
    destination = "project" if section is Section.PROGETTI else "subproject"
    if destination not in mapping:
        missing.append(destination)
    if missing:
        problems.append(
            Problem(
                Level.ERROR,
                "Intestazioni mancanti nella prima riga: "
                + ", ".join(sorted(_HEADER_LABELS.get(m, m) for m in missing))
                + ".",
                sheet=sheet.title,
                cell="A1",
                excel_row=1,
            )
        )
    return mapping, problems


def _iter_data_rows(sheet: Worksheet) -> Iterator[tuple[int, dict[int, Cell]]]:
    """Dalla riga 2 in giù. La riga 2 è dati, non un modello di formato (§8.1)."""
    for row in sheet.iter_rows(min_row=2):
        if not row:
            continue
        yield row[0].row, {cell.column: cell for cell in row}


def _is_total_row(cells: dict[int, Cell], mapping: dict[str, int]) -> bool:
    """Riconosce una riga di totale, distinguendola da una riga dati con una formula.

    Criterio: la riga contiene almeno una formula **e** non ha né collaboratore né data.
    Una riga di totale somma giornate e al massimo porta un'etichetta tipo "Totale" nella
    colonna della destinazione; non ha mai un autore o un giorno di competenza.

    Il criterio alternativo — qualunque formula implica riga di totale — nasconderebbe il
    caso del §8.3: una formula in un campo informativo di una riga vera, che deve produrre
    un errore e non essere scartata in silenzio.
    """
    if not any(_is_formula(c) for c in cells.values()):
        return False
    for name in ("collaborator", "period"):
        column = mapping.get(name)
        if column is None:
            continue
        cell = cells.get(column)
        if cell is not None and not _is_blank(cell.value):
            return False
    return True


def _read_sheet(sheet: Worksheet, section: Section) -> SheetResult:
    result = SheetResult(section=section, sheet=sheet.title)
    mapping, header_problems = _map_headers(sheet, section)
    result.problems.extend(header_problems)
    if any(p.level is Level.ERROR for p in header_problems):
        return result

    for excel_row, cells in _iter_data_rows(sheet):
        present = [c for c in cells.values() if not _is_blank(c.value)]
        if not present:
            result.rows_empty += 1
            continue
        if _is_total_row(cells, mapping):
            result.rows_formula += 1
            continue

        result.rows_read += 1
        row, problems = _read_row(sheet.title, section, excel_row, cells, mapping)
        result.problems.extend(problems)
        if row is not None:
            result.rows.append(row)
    return result


def _read_row(
    sheet_title: str,
    section: Section,
    excel_row: int,
    cells: dict[int, Cell],
    mapping: dict[str, int],
) -> tuple[SourceRow | None, list[Problem]]:
    problems: list[Problem] = []
    coords: dict[str, str] = {}
    values: dict[str, Any] = {}
    # Campi il cui valore non è leggibile perché contengono una formula: un solo errore a
    # testa, senza aggiungere "obbligatorio" o "non numerico" sulla stessa cella.
    formula_fields: set[str] = set()
    for name, column in mapping.items():
        cell = cells.get(column)
        if cell is None:
            coords[name] = f"{get_column_letter(column)}{excel_row}"
            values[name] = None
            continue
        coords[name] = cell.coordinate
        if _is_formula(cell):
            formula_fields.add(name)
            problems.append(
                Problem(
                    Level.ERROR,
                    "Formula in un campo informativo, senza valore disponibile: "
                    "sostituirla con il valore.",
                    sheet=sheet_title,
                    cell=cell.coordinate,
                    excel_row=excel_row,
                )
            )
            values[name] = None
            continue
        values[name] = cell.value

    def problem(level: Level, message: str, field_name: str) -> Problem:
        return Problem(
            level,
            message,
            sheet=sheet_title,
            cell=coords.get(field_name, ""),
            excel_row=excel_row,
        )

    period: dt.date | None = None
    if "period" not in formula_fields:
        try:
            period = parse_period(values.get("period"))
        except ValueError as exc:
            problems.append(problem(Level.ERROR, str(exc), "period"))

    days: Decimal | None = None
    if "days" not in formula_fields:
        try:
            days, days_warning = parse_days(values.get("days"))
        except ValueError as exc:
            problems.append(problem(Level.ERROR, str(exc), "days"))
        else:
            if days_warning:
                problems.append(problem(Level.WARNING, days_warning, "days"))

    note = _clean_text(values.get("note"))
    if "note" not in formula_fields:
        if not note:
            problems.append(
                problem(
                    Level.ERROR, "Descrizione obbligatoria, come nell'inserimento manuale.", "note"
                )
            )
        elif len(note) > NOTE_MAX_LENGTH:
            problems.append(
                problem(
                    Level.ERROR,
                    f"Descrizione di {len(note)} caratteri: il massimo è {NOTE_MAX_LENGTH}.",
                    "note",
                )
            )

    collaborator = _clean_text(values.get("collaborator"))
    if "collaborator" not in formula_fields and not collaborator:
        problems.append(problem(Level.ERROR, "Collaboratore mancante.", "collaborator"))

    project = _clean_text(values.get("project"))
    subproject = _clean_text(values.get("subproject"))
    needs_project = section in (Section.PROGETTI, Section.WALLET)
    needs_subproject = section in (Section.WALLET, Section.ORGANICO)
    if needs_project and "project" not in formula_fields and not project:
        problems.append(problem(Level.ERROR, "Progetto mancante.", "project"))
    if needs_subproject and "subproject" not in formula_fields and not subproject:
        problems.append(problem(Level.ERROR, "Sottoprogetto mancante.", "subproject"))

    if any(p.level is Level.ERROR for p in problems):
        return None, problems

    assert period is not None and days is not None  # garantito dai controlli sopra
    row = SourceRow(
        section=section,
        sheet=sheet_title,
        excel_row=excel_row,
        period=period,
        days=days,
        note=note,
        collaborator=collaborator,
        project=project,
        subproject=subproject,
        cells=coords,
    )
    return row, problems


def parse_workbook(source: Any) -> ParsedWorkbook:
    """Legge l'estratto operativo da un percorso o da un file aperto in binario."""
    try:
        workbook = load_workbook(source, data_only=False, read_only=False)
    except Exception as exc:  # openpyxl solleva tipi diversi secondo il danno
        raise WorkbookStructureError(f"File non leggibile come xlsx: {exc}") from exc

    parsed = ParsedWorkbook()
    try:
        seen: dict[Section, str] = {}
        for sheet in workbook.worksheets:
            section = _SHEET_ALIASES.get(normalize_key(sheet.title))
            if section is None:
                parsed.problems.append(
                    Problem(
                        Level.WARNING,
                        f"Foglio '{sheet.title}' ignorato: non previsto dal formato.",
                        sheet=sheet.title,
                    )
                )
                continue
            if section in seen:
                parsed.problems.append(
                    Problem(
                        Level.ERROR,
                        f"Sezione {section.label} presente in due fogli: "
                        f"'{seen[section]}' e '{sheet.title}'.",
                        sheet=sheet.title,
                    )
                )
                continue
            seen[section] = sheet.title
            parsed.sheets.append(_read_sheet(sheet, section))

        if not parsed.sheets:
            raise WorkbookStructureError(
                "Nessuno dei fogli attesi è presente: servono Progetti, Wallet e "
                "Organico_Allargato."
            )
        for section in Section:
            if section not in seen:
                parsed.problems.append(
                    Problem(
                        Level.WARNING,
                        f"Foglio della sezione {section.label} assente: "
                        "nessun consuntivo importato per quella sezione.",
                    )
                )
    finally:
        workbook.close()
    return parsed
