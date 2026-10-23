from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth.models import Group
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from core import roles
from exporters import export_csv_bytes, export_excel_bytes, export_json_bytes
from importers.ppm import apply_ppm, dry_run_ppm, parse_ppm_xlsx, rollback_ppm
from imports.models import ImportBatch, ImportStatus
from tests.factories import ProjectFactory, UserFactory
from timesheets.models import TimesheetEntry, TimesheetSource

pytestmark = pytest.mark.django_db


def make_ppm(path, rows, total=None):
    wb = Workbook()
    ws = wb.active
    ws.append(["Progetti Gruppo Progetto - Test"])
    ws.append(["Estratto il 16/10/2026 alle 11:05:18"])
    ws.append([])
    ws.append(["Progetto", "gg tot"])
    for code, days in rows:
        ws.append([code, days])
    ws.append(["Totale", total if total is not None else sum(days for _, days in rows)])
    wb.save(path)


def test_parser_cerca_header_data_totale_e_match_normalizzato(tmp_path):
    project = ProjectFactory(code="IM100-3313-BMED-ARCH-TEST")
    path = tmp_path / "ppm.xlsx"
    make_ppm(path, [("im100-3313-arch-test", 10.5)], total=10.5)

    parsed = parse_ppm_xlsx(path)
    report = dry_run_ppm(path)

    assert parsed.header_row == 4
    assert parsed.extracted_at.strftime("%Y-%m-%d %H:%M:%S") == "2026-10-16 11:05:18"
    assert parsed.balanced is True
    assert report.recognized == 1
    assert report.unmatched == 0
    assert report.rows[0]["progetto"] == project.code


def test_apply_a_differenza_e_reimport_idempotente(tmp_path):
    plus = ProjectFactory(code="IMPLUS-3313-BMED-ARCH-TEST", budget_days=20)
    minus = ProjectFactory(code="IMMINUS-3313-BMED-ARCH-TEST", budget_days=20)
    TimesheetEntry.objects.create(
        project=plus,
        period=date(2026, 10, 1),
        days=Decimal("5.0000"),
        source=TimesheetSource.MANUALE,
    )
    TimesheetEntry.objects.create(
        project=minus,
        period=date(2026, 10, 1),
        days=Decimal("8.0000"),
        source=TimesheetSource.MANUALE,
    )
    path = tmp_path / "ppm.xlsx"
    make_ppm(path, [(plus.code, 6.5), (minus.code, 7.25)], total=13.75)

    first = apply_ppm(path)
    second = apply_ppm(path)

    assert first.entries_created == 2
    assert second.entries_created == 0
    entries = TimesheetEntry.objects.filter(import_batch__isnull=False).order_by("project__code")
    assert list(entries.values_list("days", "source")) == [
        (Decimal("-0.7500"), TimesheetSource.STORNO),
        (Decimal("1.5000"), TimesheetSource.PPM_IMPORT),
    ]


def test_rollback_ppm_crea_storni_e_non_cancella(tmp_path):
    project = ProjectFactory(code="IMROLL-3313-BMED-ARCH-TEST", budget_days=20)
    path = tmp_path / "ppm.xlsx"
    make_ppm(path, [(project.code, 2)], total=2)
    report = apply_ppm(path)
    before = TimesheetEntry.objects.count()

    result = rollback_ppm(report.batch_id)

    assert result["storni_creati"] == 1
    assert TimesheetEntry.objects.count() == before + 1
    assert ImportBatch.objects.get(pk=report.batch_id).status == ImportStatus.ROLLED_BACK


def test_export_schema_csv_ed_excel_multifoglio():
    ProjectFactory(code="IMEXPORT-TEST")
    payload = json.loads(export_json_bytes())
    assert payload["schema_version"] == "1.0.0"
    assert b"schema_version" in export_csv_bytes("projects")
    workbook = load_workbook(BytesIO(export_excel_bytes()), read_only=True)
    assert workbook.sheetnames == [
        "Progetti",
        "Wallet",
        "Canone",
        "Riconciliazione",
        "Anomalie",
    ]


def test_api_export_richiede_autenticazione():
    client = APIClient()
    assert client.get("/api/v1/export/json").status_code == 401
    admin_user = UserFactory()
    roles.ensure_groups()
    admin_user.groups.add(Group.objects.get(name=roles.ADMIN))
    client.force_authenticate(user=admin_user)
    assert client.get("/api/v1/export/json").status_code == 200
    assert client.get("/api/v1/export/csv/projects").status_code == 200
    assert client.get("/api/v1/export/excel").status_code == 200
