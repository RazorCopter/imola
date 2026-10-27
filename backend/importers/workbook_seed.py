"""Import lossless del seed workbook v2 in un'area di staging interrogabile."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from importers.report import ImportReport
from imports.models import ImportBatch, WorkbookDatasetSnapshot, WorkbookSheetSnapshot


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value


def validate_workbook_integrity(payload: dict[str, Any]) -> None:
    workbook = payload["workbook"]
    sheets = workbook["sheets"]
    datasets = payload["datasets"]
    audit = payload["audit"]
    problems: list[str] = []
    sheet_names = [sheet["name"] for sheet in sheets]
    if workbook["sheet_order"] != sheet_names:
        problems.append("sheet_order non coincide con l'ordine dei fogli")

    table_count = sum(len(sheet["tables"]) for sheet in sheets)
    cell_count = sum(len(sheet["cells"]) for sheet in sheets)
    formula_count = sum(1 for sheet in sheets for cell in sheet["cells"] if "formula" in cell)
    table_row_count = sum(len(table["rows"]) for sheet in sheets for table in sheet["tables"])
    expected = {
        "sheet_count": len(sheets),
        "table_count": table_count,
        "nonempty_or_annotated_cell_count": cell_count,
        "formula_cell_count": formula_count,
        "table_data_row_count_including_blank_rows": table_row_count,
    }
    for key, actual in expected.items():
        if audit[key] != actual:
            problems.append(f"audit.{key}={audit[key]} ma il contenuto contiene {actual}")

    seen_ids: set[str] = set()
    for dataset in datasets:
        dataset_id = dataset["id"]
        if dataset_id in seen_ids:
            problems.append(f"dataset duplicato: {dataset_id}")
        seen_ids.add(dataset_id)
        keys = [column["key"] for column in dataset["columns"]]
        if dataset["row_count"] != len(dataset["rows"]):
            problems.append(f"{dataset_id}: row_count non coincide con le righe")
        if dataset["column_count"] != len(keys):
            problems.append(f"{dataset_id}: column_count non coincide con le colonne")
        for row in dataset["rows"]:
            if set(row["values"]) != set(keys):
                problems.append(
                    f"{dataset_id} riga {row['source_row']}: valori non allineati alle colonne"
                )
                break
    application = payload["application"]
    projected = application["seed_v1"]
    coverage = application["coverage"]
    schema_version = payload.get("meta", {}).get("schema_version")
    is_v3 = schema_version == "3.0.0"
    wallet_allocations_count = (
        len(application.get("wallet_v3", {}).get("utilizzi", []))
        if is_v3
        else len(projected["wallet"]["allocazioni"])
    )
    application_counts = {
        "projects": len(projected["progetti"]),
        "people": len(projected["persone"]),
        "canoni": len(projected["canoni"]),
        "wallet_activities": len(projected["wallet"]["attivita"]),
        "wallet_allocations": wallet_allocations_count,
    }
    for key, actual in application_counts.items():
        if coverage[key] != actual:
            problems.append(f"application.coverage.{key}={coverage[key]} ma contiene {actual}")
    if problems:
        version_label = "v3" if is_v3 else "v2"
        raise ValueError(f"Seed workbook {version_label} incoerente: " + "; ".join(problems))


def make_workbook_report(
    payload: dict[str, Any], source_filename: str, *, dry_run: bool
) -> ImportReport:
    validate_workbook_integrity(payload)
    meta = payload["meta"]
    report = ImportReport(
        kind="WORKBOOK_JSON",
        source_filename=source_filename,
        schema_version=meta["schema_version"],
        reference_date=meta.get("workbook_reference_date"),
        dry_run=dry_run,
    )
    sheets = report.entity("fogli_workbook")
    datasets = report.entity("dataset_workbook")
    sheets.created = len(payload["workbook"]["sheets"])
    sheets.created_keys = [sheet["name"] for sheet in payload["workbook"]["sheets"]]
    datasets.created = len(payload["datasets"])
    datasets.created_keys = [dataset["id"] for dataset in payload["datasets"]]
    audit = payload["audit"]
    report.totals = {
        "fogli": len(payload["workbook"]["sheets"]),
        "dataset": len(payload["datasets"]),
        "righe_dataset": sum(dataset["row_count"] for dataset in payload["datasets"]),
        "celle_non_vuote_o_annotate": audit["nonempty_or_annotated_cell_count"],
        "formule": audit["formula_cell_count"],
        "hash_sorgente": meta["source"]["sha256"],
        "copertura": "integrale",
        "proiezione_applicativa": payload["application"]["coverage"],
    }
    return report


def persist_workbook(payload: dict[str, Any], *, batch: ImportBatch) -> None:
    validate_workbook_integrity(payload)
    WorkbookSheetSnapshot.objects.bulk_create(
        [
            WorkbookSheetSnapshot(
                batch=batch,
                name=sheet["name"],
                position=position,
                state=sheet.get("state", ""),
                dimensions=sheet.get("dimensions", ""),
                payload=json_value(sheet),
            )
            for position, sheet in enumerate(payload["workbook"]["sheets"])
        ]
    )
    WorkbookDatasetSnapshot.objects.bulk_create(
        [
            WorkbookDatasetSnapshot(
                batch=batch,
                dataset_id=dataset["id"],
                sheet_name=dataset["sheet"],
                source_range=dataset["range"],
                row_count=dataset["row_count"],
                column_count=dataset["column_count"],
                columns=json_value(dataset["columns"]),
                rows=json_value(dataset["rows"]),
            )
            for dataset in payload["datasets"]
        ]
    )
