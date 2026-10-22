"""Test di accettazione sui dati esatti del seed reale della Fase 2."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from domain.wallet_balance import wallet_year_balance
from projects.models import Project, TimesheetStatus
from tests.factories import UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.seedfile]


@pytest.fixture
def imported_seed(seed_file: Path) -> Path:
    if not seed_file.is_file():
        pytest.skip(f"File seed non presente in {seed_file}")
    call_command("import_seed", str(seed_file), "--apply", verbosity=0)
    return seed_file


@pytest.fixture
def authenticated_client(imported_seed: Path) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=UserFactory())
    return client


def test_wallet_api_espone_totali_e_w26_001_del_seed_reale(authenticated_client: APIClient):
    response = authenticated_client.get("/api/v1/wallet/2026/balance")

    assert response.status_code == 200
    body = response.json()
    assert body["allocato"] == "130.8900"
    assert body["consumato"] == "120.7900"
    assert body["disponibile"] == "10.1000"
    assert body["disponibile_da_allocazioni"] == "10.1000"
    assert body["residui_validi_non_allocati"] == "0.0000"
    assert body["budget_residuo_progetti_in_corso"] == "129.9150"
    assert body["sforamenti_progetti_in_corso"] == "-8.2400"
    assert body["dettaglio_residui"]["VALIDO"]["progetti"] == []

    allocation = next(row for row in body["allocazioni"] if row["riferimento"] == "W26-001")
    assert allocation == {
        "riferimento": "W26-001",
        "progetto_origine": "IM24133-3313-BMED-ARCH-NUOVO-PROTECTION-MODEL",
        "attivita": "IM24133-3313-BMED-ARCH-NUOVO-PROTECTION-MODEL",
        "allocato": "50.0000",
        "consumato": "50.0000",
        "disponibile": "0.0000",
        "stato": "APERTA",
    }


def test_chiusura_im24517_rende_spendibile_solo_il_suo_residuo(imported_seed: Path):
    project = Project.objects.get(code__startswith="IM24517")
    project.timesheet_status = TimesheetStatus.CHIUSO
    project.actual_closure_date = date(2025, 5, 30)
    project.save(update_fields=["timesheet_status", "actual_closure_date", "updated_at"])

    balance = wallet_year_balance(2026, today=date(2026, 10, 16))
    assert balance.unallocated_valid_days + balance.unallocated_expiring_days == Decimal("12.3100")
    assert balance.unallocated_valid_days == Decimal("0.0000")
    assert balance.unallocated_expiring_days == Decimal("12.3100")


def test_review_queue_api_espone_i_dodici_progetti_esatti(authenticated_client: APIClient):
    response = authenticated_client.get(
        "/api/v1/review-queue", {"as_of": date(2026, 10, 16).isoformat()}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 12
    assert body["da_verificare_count"] == 9
    assert body["chiuso_senza_data_count"] == 3
    assert [row["codice"] for row in body["results"]] == [
        "IM24517-3313-BMED-ARCH-SOLUTION-DESIGN-CONSULENZA-AMMINISTRATO",
        "IM25026-3313-BMED-ARCH-SOLUTION-DESIGN-INTEGRAZIONE-SCHEDA-FONDO",
        "IM25075-3313-BMED-ARCH-SOLUTION-DESIGN-APP-FB-WAVE-2",
        "IM25151-3313-BMED-ARCH-ICT-ASSET-LIFECYCLE-OBSOLESCENZA",
        "IM25188-3313-BMED-ARCH-INTEGR-NOTIFICHE-PUSH-APP-MED-ALERT-SEC",
        "IM25206-3313-BMED-ARCH-DATABRICKS-SUPERAMENTO-CRMA-DATALAB",
        "IM25236-3313-BMED-ARCH-RAFFORZAMENTO-DATA-QUALITY-TECNICA",
        "IM25255-3313-BMED-ARCH-ADEGUA-OSI-ORIGINATION-MONIT-CRED-ORD",
        "IM25270-3313-BMED-ARCH-SOLUTION-DESIGN-AGILE-CREDIT",
        "IM26034-3313-BMED-ARCH-SOLUTION-DESIGN-MIGRAZIONE-VIYA",
        "IM26047-3313-BMED-ARCH-SOLUTION-DESIGN-MARKET-RISK-W2",
        "IM26075-3313-BMED-ARCH-MIGRAZIONE-COMP-ARCH-OSB14",
    ]

    for row in body["results"][:9]:
        assert row["data_chiusura_proposta"].startswith("2025-")
        assert row["scadenza_potenziale"] == "2026-12-31"
        if Decimal(row["residuo"]) > Decimal("0.0000"):
            assert row["in_scadenza_entro_90gg"] is True
            assert row["avviso_scadenza"].endswith("utilizzabili fino al 31/12/2026.")
        else:
            assert row["in_scadenza_entro_90gg"] is False
            assert row["avviso_scadenza"] is None
