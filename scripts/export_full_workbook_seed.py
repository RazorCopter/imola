"""Esporta un workbook Excel in un seed JSON lossless e verificabile."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils import get_column_letter, range_boundaries
from workbook_application_projection import build_application_projection

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path.home() / "Downloads" / "2026S1-OrgAllargatoProgetti-Situazione.xlsx"
DEFAULT_OUTPUT = ROOT / "data" / "seed" / "seed_imola_v3_2026-10-09.json"
DEFAULT_SCHEMA = ROOT / "seed_workbook_schema_v3.json"


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if hasattr(value, "text"):
        return str(value.text)
    return str(value)


def formula_text(cell: Cell) -> str | None:
    if cell.data_type != "f":
        return None
    value = cell.value
    if hasattr(value, "text"):
        return str(value.text)
    return str(value)


def clean_key(label: Any, index: int) -> str:
    text = str(label).strip() if label not in (None, "") else f"colonna_{index}"
    text = re.sub(r"[^0-9A-Za-zÀ-ÿ]+", "_", text).strip("_").lower()
    return text or f"colonna_{index}"


def unique_keys(labels: list[Any]) -> list[str]:
    keys: list[str] = []
    seen: dict[str, int] = {}
    for index, label in enumerate(labels, start=1):
        base = clean_key(label, index)
        seen[base] = seen.get(base, 0) + 1
        keys.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return keys


def cell_payload(formula_cell: Cell, value_cell: Cell) -> dict[str, Any]:
    formula = formula_text(formula_cell)
    value = value_cell.value if formula is not None else formula_cell.value
    payload: dict[str, Any] = {
        "ref": formula_cell.coordinate,
        "value": json_value(value),
        "data_type": formula_cell.data_type,
        "number_format": formula_cell.number_format,
    }
    if formula is not None:
        payload["formula"] = formula
    if formula_cell.comment is not None:
        payload["comment"] = {
            "author": formula_cell.comment.author,
            "text": formula_cell.comment.text,
        }
    if formula_cell.hyperlink is not None:
        payload["hyperlink"] = formula_cell.hyperlink.target or formula_cell.hyperlink.location
    return payload


def table_payload(formula_sheet: Any, value_sheet: Any, table: Any) -> dict[str, Any]:
    min_col, min_row, max_col, max_row = range_boundaries(table.ref)
    labels = [value_sheet.cell(min_row, col).value for col in range(min_col, max_col + 1)]
    keys = unique_keys(labels)
    columns = [
        {
            "key": key,
            "label": json_value(label),
            "excel_column": get_column_letter(col),
        }
        for key, label, col in zip(keys, labels, range(min_col, max_col + 1), strict=True)
    ]
    rows: list[dict[str, Any]] = []
    for row_number in range(min_row + 1, max_row + 1):
        values: dict[str, Any] = {}
        formulas: dict[str, str] = {}
        for key, col in zip(keys, range(min_col, max_col + 1), strict=True):
            formula_cell = formula_sheet.cell(row_number, col)
            value_cell = value_sheet.cell(row_number, col)
            formula = formula_text(formula_cell)
            values[key] = json_value(value_cell.value if formula is not None else formula_cell.value)
            if formula is not None:
                formulas[key] = formula
        row: dict[str, Any] = {"source_row": row_number, "values": values}
        if formulas:
            row["formulas"] = formulas
        rows.append(row)
    return {
        "name": table.name,
        "display_name": table.displayName,
        "range": table.ref,
        "header_row": min_row,
        "columns": columns,
        "rows": rows,
        "totals_row_shown": bool(table.totalsRowShown),
    }


def validation_payload(validation: Any) -> dict[str, Any]:
    return {
        "ranges": str(validation.sqref),
        "type": validation.type,
        "operator": validation.operator,
        "formula1": json_value(validation.formula1),
        "formula2": json_value(validation.formula2),
        "allow_blank": validation.allowBlank,
    }


def sheet_payload(formula_sheet: Any, value_sheet: Any) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    for row in formula_sheet.iter_rows():
        for formula_cell in row:
            value_cell = value_sheet[formula_cell.coordinate]
            if (
                formula_cell.value is not None
                or value_cell.value is not None
                or formula_cell.comment is not None
                or formula_cell.hyperlink is not None
            ):
                cells.append(cell_payload(formula_cell, value_cell))

    tables = [
        table_payload(formula_sheet, value_sheet, formula_sheet.tables[name])
        for name in formula_sheet.tables
    ]
    validations = []
    if formula_sheet.data_validations is not None:
        validations = [
            validation_payload(validation)
            for validation in formula_sheet.data_validations.dataValidation
        ]
    return {
        "name": formula_sheet.title,
        "state": formula_sheet.sheet_state,
        "dimensions": formula_sheet.calculate_dimension(),
        "max_row": formula_sheet.max_row,
        "max_column": formula_sheet.max_column,
        "freeze_panes": str(formula_sheet.freeze_panes) if formula_sheet.freeze_panes else None,
        "auto_filter": formula_sheet.auto_filter.ref,
        "merged_ranges": [str(item) for item in formula_sheet.merged_cells.ranges],
        "data_validations": validations,
        "tables": tables,
        "cells": cells,
    }


def defined_names_payload(workbook: Any) -> list[dict[str, Any]]:
    result = []
    for item in workbook.defined_names.values():
        result.append(
            {
                "name": item.name,
                "definition": item.attr_text,
                "hidden": bool(item.hidden),
                "local_sheet_id": item.localSheetId,
            }
        )
    return result


def range_dataset(
    sheet: dict[str, Any],
    *,
    dataset_id: str,
    data_range: str,
    header_row: int,
    first_data_row: int,
    last_data_row: int,
) -> dict[str, Any]:
    min_col, _, max_col, _ = range_boundaries(data_range)
    cells = {cell["ref"]: cell for cell in sheet["cells"]}
    labels = [
        cells.get(f"{get_column_letter(col)}{header_row}", {}).get("value")
        for col in range(min_col, max_col + 1)
    ]
    keys = unique_keys(labels)
    columns = [
        {
            "key": key,
            "label": label,
            "excel_column": get_column_letter(col),
        }
        for key, label, col in zip(keys, labels, range(min_col, max_col + 1), strict=True)
    ]
    rows = []
    for row_number in range(first_data_row, last_data_row + 1):
        values: dict[str, Any] = {}
        formulas: dict[str, str] = {}
        for key, col in zip(keys, range(min_col, max_col + 1), strict=True):
            cell = cells.get(f"{get_column_letter(col)}{row_number}")
            values[key] = None if cell is None else cell["value"]
            if cell is not None and "formula" in cell:
                formulas[key] = cell["formula"]
        row: dict[str, Any] = {"source_row": row_number, "values": values}
        if formulas:
            row["formulas"] = formulas
        rows.append(row)
    return {
        "id": dataset_id,
        "sheet": sheet["name"],
        "range": data_range,
        "header_row": header_row,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "column_count": len(columns),
    }


def datasets_payload(sheets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for sheet in sheets:
        for table in sheet["tables"]:
            result.append(
                {
                    "id": f"{sheet['name']}::{table['name']}",
                    "sheet": sheet["name"],
                    "table": table["name"],
                    "range": table["range"],
                    "row_count": len(table["rows"]),
                    "column_count": len(table["columns"]),
                    "columns": table["columns"],
                    "rows": table["rows"],
                }
            )
    sheets_by_name = {sheet["name"]: sheet for sheet in sheets}
    for sheet_name, data_range, header_row, first_row, last_row in (
        ("OA-attività S1", "A4:B33", 4, 5, 33),
        ("OA-attività S2", "A4:F27", 4, 5, 27),
        ("Capacity Mensile", "A3:AK91", 3, 4, 91),
    ):
        result.append(
            range_dataset(
                sheets_by_name[sheet_name],
                dataset_id=f"{sheet_name}::intervallo_principale",
                data_range=data_range,
                header_row=header_row,
                first_data_row=first_row,
                last_data_row=last_row,
            )
        )
    return result


def build_seed(source: Path) -> dict[str, Any]:
    formula_workbook = load_workbook(source, data_only=False, read_only=False)
    value_workbook = load_workbook(source, data_only=True, read_only=False)
    sheets = [
        sheet_payload(formula_sheet, value_workbook[formula_sheet.title])
        for formula_sheet in formula_workbook.worksheets
    ]
    source_bytes = source.read_bytes()
    source_stat = source.stat()
    nonempty_cells = sum(len(sheet["cells"]) for sheet in sheets)
    formula_cells = sum(
        1 for sheet in sheets for cell in sheet["cells"] if "formula" in cell
    )
    table_rows = sum(
        len(table["rows"]) for sheet in sheets for table in sheet["tables"]
    )
    seed = {
        "$schema": "./seed_workbook_schema_v3.json",
        "meta": {
            "schema_version": "3.0.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "scope": "FULL_WORKBOOK",
            "source": {
                "filename": source.name,
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "size_bytes": len(source_bytes),
                "last_modified": datetime.fromtimestamp(
                    source_stat.st_mtime, tz=UTC
                ).isoformat(),
            },
            "workbook_reference_date": "2026-10-09",
            "notes": [
                "Estratto esclusivamente dal workbook indicato in meta.source.",
                "Nessun valore è stato integrato da fonti secondarie.",
                "Le formule sono conservate insieme al valore calcolato memorizzato nel file Excel.",
            ],
        },
        "workbook": {
            "sheet_order": formula_workbook.sheetnames,
            "defined_names": defined_names_payload(formula_workbook),
            "sheets": sheets,
        },
        "datasets": datasets_payload(sheets),
        "audit": {
            "sheet_count": len(sheets),
            "table_count": sum(len(sheet["tables"]) for sheet in sheets),
            "nonempty_or_annotated_cell_count": nonempty_cells,
            "formula_cell_count": formula_cells,
            "table_data_row_count_including_blank_rows": table_rows,
        },
    }
    seed["application"] = build_application_projection(seed)
    return seed


def validate_seed(seed: dict[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    problems = sorted(validator.iter_errors(seed), key=lambda item: list(item.path))
    if problems:
        details = "\n".join(
            f"- {'/'.join(str(part) for part in problem.path)}: {problem.message}"
            for problem in problems
        )
        raise ValueError(f"Seed non conforme allo schema:\n{details}")
    v1_schema = json.loads((ROOT / "seed_schema_v1.json").read_text(encoding="utf-8"))
    v1_problems = sorted(
        Draft202012Validator(v1_schema).iter_errors(seed["application"]["seed_v1"]),
        key=lambda item: list(item.path),
    )
    if v1_problems:
        details = "\n".join(
            f"- application/seed_v1/{'/'.join(str(part) for part in problem.path)}: "
            f"{problem.message}"
            for problem in v1_problems
        )
        raise ValueError(f"Proiezione applicativa non conforme:\n{details}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    schema = args.schema.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not schema.is_file():
        raise FileNotFoundError(schema)

    seed = build_seed(source)
    validate_seed(seed, schema)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(seed, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), **seed["audit"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
