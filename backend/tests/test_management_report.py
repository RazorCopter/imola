from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from core import roles
from projects.models import TimesheetStatus
from tests.factories import (
    CanoneFactory,
    CanoneSubactivityFactory,
    PersonFactory,
    ProjectFactory,
    TimesheetEntryFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
)
from tests.test_roles_object_permissions import make_client_for_role

pytestmark = pytest.mark.django_db


def test_report_access_only_admin():
    for role in (roles.MANAGER, roles.REFERENT, roles.SUPPLIER):
        client, _ = make_client_for_role(role)
        assert client.get("/api/v1/admin/management-report").status_code == 403
    client, _ = make_client_for_role(roles.ADMIN)
    assert client.get("/api/v1/admin/management-report").status_code == 200


def test_report_scope_e_valori():
    client, _ = make_client_for_role(roles.ADMIN)
    owner = PersonFactory(full_name="Mario Rossi")
    ProjectFactory(code="P-ATTIVO", client_owner=owner, budget_days=Decimal("20"))
    ProjectFactory(
        code="P-CHIUSO",
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2026, 1, 1),
    )
    activity = WalletActivityFactory(client_owner=owner)
    architect = PersonFactory(full_name="Nicoletti Pietro")
    allocation = WalletAllocationFactory(
        activity=activity, assignee=architect, allocated_days=Decimal("8")
    )
    TimesheetEntryFactory(wallet_allocation=allocation, days=Decimal("3"))
    canone = CanoneFactory(start_date=date(2026, 7, 1), end_date=date(2026, 12, 31))
    sub = CanoneSubactivityFactory(canone=canone, office="CROSS", reserved_days=Decimal("10"))
    TimesheetEntryFactory(canone_subactivity=sub, days=Decimal("4"))
    closed = CanoneSubactivityFactory(
        canone=canone, office="CROSS", title="Completata", reserved_days=Decimal("5")
    )
    TimesheetEntryFactory(canone_subactivity=closed, days=Decimal("5"))
    with patch("api.management_report.timezone.localdate", return_value=date(2026, 10, 29)):
        response = client.get("/api/v1/admin/management-report")
    assert response.status_code == 200
    body = response.json()
    row = next(x for x in body["projects"] if x["code"] == "P-ATTIVO")
    assert row["owner"] == "Mario Rossi" and Decimal(row["budget"]) == 20
    assert not any(x["code"] == "P-CHIUSO" for x in body["projects"])
    assert Decimal(body["wallet"][0]["consumed"]) == 3
    assert Decimal(body["wallet"][0]["remaining"]) == 5
    # Chi risponde delle giornate e l'assegnatario dell'allocazione, non solo il
    # referente BMED dell'attivita, che per le attivita create dal wallet resta vuoto.
    assert body["wallet"][0]["assignee"] == "Nicoletti Pietro"
    assert body["wallet"][0]["owner"] == "Mario Rossi"

    assert body["domains"][0]["domain"] == "CROSS"
    assert Decimal(body["domains"][0]["remaining"]) == 6
    assert Decimal(body["domains"][0]["consumed"]) == 9
    assert Decimal(body["organico_monte"]) == canone.total_days
    assert len(body["activities"]) == 1
    assert body["activities"][0]["title"] == sub.title


def test_report_annual_costs_exclude_history_and_future():
    from core.models import AppSettings

    settings = AppSettings.get_solo()
    settings.daily_person_cost = Decimal("100")
    settings.save()
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory()
    TimesheetEntryFactory(project=project, period=date(2026, 2, 1), days="3")
    TimesheetEntryFactory(project=project, period=date(2025, 2, 1), days="9")
    TimesheetEntryFactory(project=project, period=date(2026, 12, 1), days="9")
    allocation = WalletAllocationFactory()
    TimesheetEntryFactory(wallet_allocation=allocation, period=date(2026, 3, 1), days="2")
    with patch("api.management_report.timezone.localdate", return_value=date(2026, 10, 29)):
        body = client.get("/api/v1/admin/management-report").json()
    economics = body["economics"]
    assert Decimal(economics["kpi"]["total_cost"]) == 500
    assert {r["source"]: Decimal(r["cost"]) for r in economics["by_source"]} == {
        "PROJECT": Decimal("300"),
        "WALLET": Decimal("200"),
    }
    assert [r["month"] for r in economics["monthly_trend"]] == ["2026-02", "2026-03"]


def test_il_report_wallet_mostra_l_assegnatario_anche_senza_referente_bmed():
    client, _ = make_client_for_role(roles.ADMIN)
    architect = PersonFactory(full_name="Gabriele Cataldo")
    # Attivita creata dal wallet: nessun referente BMED, com'e nei dati reali.
    activity = WalletActivityFactory(code="ACT-SENZA-REFERENTE", client_owner=None)
    WalletAllocationFactory(activity=activity, assignee=architect, allocated_days=Decimal("4"))

    body = client.get("/api/v1/admin/management-report").json()

    row = next(x for x in body["wallet"] if x["code"] == "ACT-SENZA-REFERENTE")
    assert row["owner"] is None
    assert row["assignee"] == "Gabriele Cataldo"


def test_le_sezioni_sono_ordinate_per_chiave_di_raggruppamento():
    """Progetti per referente BMED, wallet per assegnatario, canone per dominio."""
    client, _ = make_client_for_role(roles.ADMIN)
    rossi = PersonFactory(full_name="Rossi Mario")
    bianchi = PersonFactory(full_name="Bianchi Anna")

    ProjectFactory(code="P-3", client_owner=rossi, budget_days=Decimal("1"))
    ProjectFactory(code="P-1", client_owner=bianchi, budget_days=Decimal("1"))
    ProjectFactory(code="P-2", client_owner=rossi, budget_days=Decimal("1"))
    ProjectFactory(code="P-0", client_owner=None, budget_days=Decimal("1"))

    for code, assignee in (("ACT-Z", rossi), ("ACT-A", bianchi), ("ACT-M", rossi)):
        WalletAllocationFactory(
            activity=WalletActivityFactory(code=code),
            assignee=assignee,
            source_project=None,
            allocated_days=Decimal("1"),
        )
    WalletAllocationFactory(
        activity=WalletActivityFactory(code="ACT-SENZA"),
        assignee=None,
        source_project=None,
        allocated_days=Decimal("1"),
    )

    canone = CanoneFactory(start_date=date(2026, 7, 1), end_date=date(2026, 12, 31))
    for office, title in (("TA", "Terza"), ("EA", "Prima"), ("TA", "Seconda"), ("CROSS", "Quarta")):
        CanoneSubactivityFactory(
            canone=canone, office=office, title=title, reserved_days=Decimal("5")
        )

    with patch("api.management_report.timezone.localdate", return_value=date(2026, 10, 29)):
        body = client.get("/api/v1/admin/management-report").json()

    # I progetti si raggruppano sotto il referente; senza referente vanno in fondo.
    # Il canone porta con se il proprio progetto: guardo solo quelli creati qui.
    assert [(x["owner"], x["code"]) for x in body["projects"] if x["code"].startswith("P-")] == [
        ("Bianchi Anna", "P-1"),
        ("Rossi Mario", "P-2"),
        ("Rossi Mario", "P-3"),
        (None, "P-0"),
    ]
    assert [(x["assignee"], x["code"]) for x in body["wallet"]] == [
        ("Bianchi Anna", "ACT-A"),
        ("Rossi Mario", "ACT-M"),
        ("Rossi Mario", "ACT-Z"),
        (None, "ACT-SENZA"),
    ]
    assert [(x["domain"], x["title"]) for x in body["activities"]] == [
        ("CROSS", "Quarta"),
        ("EA", "Prima"),
        ("TA", "Seconda"),
        ("TA", "Terza"),
    ]
