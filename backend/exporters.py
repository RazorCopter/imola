"""Export leggibili e versionati del Supplier Ledger."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone
from openpyxl import Workbook  # type: ignore[import-untyped]

from anomalies.models import Anomaly
from canone.models import Canone
from domain.canone_status import canone_status
from domain.reconciliation import reconcile
from domain.residuals import project_balance_qs
from domain.wallet_balance import allocation_balance_qs
from wallet.models import WalletAllocation

SCHEMA_VERSION = "1.0.0"


def _jsonable(value):
    from uuid import UUID

    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def export_payload() -> dict:
    projects = [
        {
            "code": row.code,
            "title": row.title,
            "budget_days": row.budget_days,
            "consumed_days": row.total_consumed_days,
            "residual_days": row.residual_days,
            "timesheet_status": row.timesheet_status,
            "billing_status": row.billing_status,
        }
        for row in project_balance_qs().order_by("code")
    ]
    wallet = [
        {
            "year": row.wallet_year.year,
            "allocation_ref": row.external_ref,
            "source_project": row.source_project.code if row.source_project else None,
            "activity": row.activity.code,
            "allocated_days": row.allocated_days,
            "consumed_days": row.consumed_days,
            "available_days": row.available_days,
            "status": row.status,
        }
        for row in allocation_balance_qs(
            WalletAllocation.objects.select_related("wallet_year", "source_project", "activity")
        ).order_by("wallet_year__year", "external_ref")
    ]
    canoni = []
    for item in Canone.objects.select_related("project").order_by("semester"):
        status = canone_status(item)
        canoni.append(
            {
                "project": item.project.code,
                "semester": item.semester,
                "total_days": status.total_days,
                "consumed_days": status.consumed_days,
                "target_days": status.target,
                "delta_days": status.delta,
                "forecast_days": status.forecast,
            }
        )
    reconciliation = [row.as_dict() for row in reconcile()]
    anomalies = list(
        Anomaly.objects.order_by("rule_code", "detected_at").values(
            "external_ref",
            "rule_code",
            "severity",
            "scope",
            "description",
            "status",
            "resolution_note",
        )
    )
    return _jsonable(
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": timezone.now().isoformat(),
            "projects": projects,
            "wallet": wallet,
            "canoni": canoni,
            "reconciliation": reconciliation,
            "anomalies": anomalies,
        }
    )


def export_json_bytes() -> bytes:
    return json.dumps(export_payload(), ensure_ascii=False, indent=2).encode("utf-8")


def _csv_rows(entity: str) -> list[dict]:
    payload = export_payload()
    aliases = {
        "projects": "projects",
        "progetti": "projects",
        "wallet": "wallet",
        "canone": "canoni",
        "canoni": "canoni",
        "reconciliation": "reconciliation",
        "riconciliazione": "reconciliation",
        "anomalies": "anomalies",
        "anomalie": "anomalies",
    }
    key = aliases.get(entity.lower())
    if key is None:
        raise ValueError(f"Entità export non valida: {entity}")
    return payload[key]


def export_csv_bytes(entity: str) -> bytes:
    rows = _csv_rows(entity)
    output = io.StringIO()
    if rows:
        rows = [{"schema_version": SCHEMA_VERSION, **row} for row in rows]
    fields = list(rows[0]) if rows else ["schema_version"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    if rows:
        writer.writerows(rows)
    else:
        writer.writerow({"schema_version": SCHEMA_VERSION})
    return output.getvalue().encode("utf-8-sig")


def export_excel_bytes() -> bytes:
    payload = export_payload()
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = [
        ("Progetti", payload["projects"]),
        ("Wallet", payload["wallet"]),
        ("Canone", payload["canoni"]),
        ("Riconciliazione", payload["reconciliation"]),
        ("Anomalie", payload["anomalies"]),
    ]
    for title, rows in sheets:
        sheet = workbook.create_sheet(title)
        sheet.append(["schema_version", SCHEMA_VERSION])
        if not rows:
            continue
        fields = list(rows[0])
        sheet.append(fields)
        for row in rows:
            sheet.append([row.get(field) for field in fields])
        sheet.freeze_panes = "A3"
        sheet.auto_filter.ref = f"A2:{chr(64 + min(len(fields), 26))}{sheet.max_row}"
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
