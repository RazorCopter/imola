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
    allocation = WalletAllocationFactory(activity=activity, allocated_days=Decimal("8"))
    TimesheetEntryFactory(wallet_allocation=allocation, days=Decimal("3"))
    canone = CanoneFactory(start_date=date(2026, 7, 1), end_date=date(2026, 12, 31))
    sub = CanoneSubactivityFactory(canone=canone, office="CROSS", reserved_days=Decimal("10"))
    TimesheetEntryFactory(canone_subactivity=sub, days=Decimal("4"))
    with patch("api.management_report.timezone.localdate", return_value=date(2026, 10, 29)):
        response = client.get("/api/v1/admin/management-report")
    assert response.status_code == 200
    body = response.json()
    row = next(x for x in body["projects"] if x["code"] == "P-ATTIVO")
    assert row["owner"] == "Mario Rossi" and Decimal(row["budget"]) == 20
    assert not any(x["code"] == "P-CHIUSO" for x in body["projects"])
    assert Decimal(body["wallet"][0]["consumed"]) == 3
    assert Decimal(body["wallet"][0]["remaining"]) == 5
    assert body["domains"][0]["domain"] == "CROSS"
    assert Decimal(body["domains"][0]["remaining"]) == 6
