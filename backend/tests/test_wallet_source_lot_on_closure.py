"""Il residuo di un progetto chiuso diventa una fonte wallet prelevabile.

Regressione: la capienza del wallet veniva mostrata partendo dai residui dei progetti
chiusi, ma `reserve_fifo` preleva dai lotti sorgente, che nessuna chiusura creava.
Risultato: il wallet dichiarava giornate disponibili e rifiutava ogni utilizzo con
"Capienza wallet insufficiente per la riserva richiesta".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from core import roles
from projects.models import ContractType, TimesheetStatus
from tests.factories import PersonFactory, ProjectFactory, TimesheetEntryFactory
from tests.test_roles_object_permissions import make_client_for_role
from wallet.models import WalletAllocation, WalletSourceLot, WalletYear
from wallet.services import ensure_source_lot

pytestmark = pytest.mark.django_db


def close_via_api(client, project, closure_date: date):
    return client.patch(
        f"/api/v1/projects/{project.id}",
        {
            "timesheet_status": TimesheetStatus.CHIUSO,
            "actual_closure_date": closure_date.isoformat(),
            "expected_version": project.version,
        },
        format="json",
    )


def test_chiusura_da_interfaccia_crea_il_lotto_e_consente_l_utilizzo():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(code="PRJ-SCAI", budget_days=Decimal("10.0000"))
    TimesheetEntryFactory(project=project, days=Decimal("3.6900"))
    architect = PersonFactory(full_name="Gabriele Cataldo")

    closed = close_via_api(client, project, date(2026, 3, 31))
    assert closed.status_code == 200, closed.data

    lot = WalletSourceLot.objects.get(source_project=project)
    assert lot.capacity_days == Decimal("6.3100")
    assert lot.wallet_year.year == 2026
    assert lot.effective_date == date(2026, 3, 31)
    assert lot.external_ref == "AUTO-CHIUSURA:PRJ-SCAI:2026"

    balance = client.get("/api/v1/wallet/2026/balance").json()
    assert balance["capacita_totale_origini"] == "6.3100"
    assert balance["residuo_wallet_non_allocato"] == "6.3100"

    # Il nuovo utilizzo per l'intera capienza ora passa.
    created = client.post(
        "/api/v1/wallet/allocations",
        {
            "year": 2026,
            "assignee": architect.id,
            "allocated_days": "6.3100",
            "activity_title": "TE200 PIM/BIA",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    data = created.json()
    assert data["funding"] == [{"source_project_code": "PRJ-SCAI", "days": "6.3100", "sequence": 1}]
    assert data["available_source_after"] == "0.0000"
    allocation = WalletAllocation.objects.get(pk=data["id"])
    assert allocation.requires_source_attribution is False

    # Un secondo utilizzo non trova piu capienza.
    exhausted = client.post(
        "/api/v1/wallet/allocations",
        {
            "year": 2026,
            "assignee": architect.id,
            "allocated_days": "1.0000",
            "activity_title": "TE201 ALTRO",
        },
        format="json",
    )
    assert exhausted.status_code == 400


def test_utilizzo_parziale_lascia_il_resto_prelevabile():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(code="PRJ-PARZIALE", budget_days=Decimal("10.0000"))
    TimesheetEntryFactory(project=project, days=Decimal("3.6900"))
    architect = PersonFactory(full_name="Architetto")
    assert close_via_api(client, project, date(2026, 3, 31)).status_code == 200

    first = client.post(
        "/api/v1/wallet/allocations",
        {
            "year": 2026,
            "assignee": architect.id,
            "allocated_days": "2.0000",
            "activity_title": "ATT-1",
        },
        format="json",
    )
    assert first.status_code == 201, first.data
    second = client.post(
        "/api/v1/wallet/allocations",
        {
            "year": 2026,
            "assignee": architect.id,
            "allocated_days": "4.3100",
            "activity_title": "ATT-2",
        },
        format="json",
    )
    assert second.status_code == 201, second.data
    balance = client.get("/api/v1/wallet/2026/balance").json()
    assert balance["totale_allocato"] == "6.3100"
    assert balance["residuo_wallet_non_allocato"] == "0.0000"


def test_il_lotto_e_unico_e_non_si_riduce_dopo_un_impegno():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(code="PRJ-IDEMPOTENTE", budget_days=Decimal("8.0000"))
    architect = PersonFactory(full_name="Architetto")
    assert close_via_api(client, project, date(2026, 5, 10)).status_code == 200
    project.refresh_from_db()

    # Richiamare la chiusura non duplica il lotto.
    assert close_via_api(client, project, date(2026, 5, 10)).status_code == 200
    assert WalletSourceLot.objects.filter(source_project=project).count() == 1

    created = client.post(
        "/api/v1/wallet/allocations",
        {
            "year": 2026,
            "assignee": architect.id,
            "allocated_days": "8.0000",
            "activity_title": "ATT-IMPEGNO",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    # Con giornate gia impegnate la capienza non viene riallineata al ribasso.
    TimesheetEntryFactory(project=project, days=Decimal("5.0000"))
    project.refresh_from_db()
    ensure_source_lot(project)
    assert WalletSourceLot.objects.get(source_project=project).capacity_days == Decimal("8.0000")


def test_il_residuo_di_una_chiusura_passata_alimenta_il_wallet_in_uso():
    """Chiuso nel 2025 ma valido fino al 31/12/2026: lo spende il wallet 2026."""
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(
        code="PRJ-CHIUSO-2025",
        budget_days=Decimal("5.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2025, 12, 31),
    )
    TimesheetEntryFactory(project=project, days=Decimal("3.3700"))

    lot = ensure_source_lot(project, today=date(2026, 10, 30))

    assert lot is not None
    assert lot.capacity_days == Decimal("1.6300")
    # La provenienza resta il 2025, la capienza vive nel wallet 2026.
    assert lot.source_year == 2025
    assert lot.wallet_year.year == 2026
    assert lot.effective_date == date(2025, 12, 31)

    balance = client.get("/api/v1/wallet/2026/balance").json()
    assert balance["capacita_totale_origini"] == "1.6300"
    assert balance["residuo_wallet_non_allocato"] == "1.6300"


def test_un_lotto_non_ancora_speso_si_riallinea_al_wallet_che_lo_spende():
    """Un lotto creato nell'anno sbagliato non deve restare invisibile."""
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(
        code="PRJ-LOTTO-ANNO-SBAGLIATO",
        budget_days=Decimal("2.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2025, 12, 31),
    )
    wallet_2025 = WalletYear.objects.create(year=2025)
    lot = WalletSourceLot.objects.create(
        wallet_year=wallet_2025,
        source_project=project,
        source_year=2025,
        capacity_days=Decimal("2.0000"),
        effective_date=date(2025, 12, 31),
        external_ref="AUTO-CHIUSURA:PRJ-LOTTO-ANNO-SBAGLIATO:2025",
    )
    assert client.get("/api/v1/wallet/2026/balance").json()["capacita_totale_origini"] == "0.0000"

    ensure_source_lot(project, today=date(2026, 10, 30))

    lot.refresh_from_db()
    assert lot.wallet_year.year == 2026
    assert lot.source_year == 2025
    assert client.get("/api/v1/wallet/2026/balance").json()["capacita_totale_origini"] == "2.0000"


def test_niente_lotto_per_residui_scaduti_canoni_o_capienza_nulla():
    scaduto = ProjectFactory(
        code="PRJ-SCADUTO",
        budget_days=Decimal("5.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2020, 1, 31),
    )
    canone = ProjectFactory(
        code="PRJ-CANONE",
        contract_type=ContractType.CANONE,
        budget_days=Decimal("5.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 1, 31),
    )
    esaurito = ProjectFactory(
        code="PRJ-ESAURITO",
        budget_days=Decimal("4.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 1, 31),
    )
    TimesheetEntryFactory(project=esaurito, days=Decimal("4.0000"))
    aperto = ProjectFactory(code="PRJ-APERTO", budget_days=Decimal("5.0000"))

    for project in (scaduto, canone, esaurito, aperto):
        assert ensure_source_lot(project) is None, project.code
    assert not WalletSourceLot.objects.exists()


def test_comando_di_allineamento_crea_i_lotti_mancanti_ed_e_idempotente():
    project = ProjectFactory(
        code="PRJ-PREESISTENTE",
        budget_days=Decimal("10.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 3, 31),
    )
    TimesheetEntryFactory(project=project, days=Decimal("3.6900"))

    dry = StringIO()
    call_command("sync_wallet_source_lots", "--dry-run", stdout=dry)
    assert "PRJ-PREESISTENTE" in dry.getvalue()
    assert not WalletSourceLot.objects.exists()

    out = StringIO()
    call_command("sync_wallet_source_lots", stdout=out)
    assert "Lotti creati: 1" in out.getvalue()
    assert WalletSourceLot.objects.get(source_project=project).capacity_days == Decimal("6.3100")

    again = StringIO()
    call_command("sync_wallet_source_lots", stdout=again)
    assert "Lotti creati: 0" in again.getvalue()
    assert WalletSourceLot.objects.count() == 1
