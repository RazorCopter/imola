"""Censimento di un consuntivo a nome di un altro utente: solo Admin."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group

from core import capabilities, roles
from tests.factories import CanoneSubactivityFactory, ProjectFactory, UserFactory
from tests.test_roles_object_permissions import make_client_for_role
from timesheets.models import TimesheetEntry

pytestmark = pytest.mark.django_db


def make_supplier_user(username: str):
    roles.ensure_groups()
    user = UserFactory(username=username, first_name="Mario", last_name="Rossi")
    user.groups.add(Group.objects.get(name=roles.SUPPLIER))
    return user


def test_capability_e_riservata_ad_admin():
    assert capabilities.ASSIGN_TIMESHEET_AUTHOR in capabilities.RESERVED_CAPABILITIES
    for role in (roles.MANAGER, roles.REFERENT, roles.SUPPLIER):
        assert capabilities.ASSIGN_TIMESHEET_AUTHOR not in capabilities.capabilities_for_role(role)
    assert capabilities.ASSIGN_TIMESHEET_AUTHOR in capabilities.capabilities_for_role(roles.ADMIN)


def test_admin_elenca_gli_utenti_selezionabili_e_gli_altri_ruoli_no():
    admin, _ = make_client_for_role(roles.ADMIN)
    imola = make_supplier_user("imola")
    referente = UserFactory(username="referente-solo-lettura")
    referente.groups.add(Group.objects.get(name=roles.REFERENT))

    response = admin.get("/api/v1/timesheets/authors")

    assert response.status_code == 200, response.data
    results = response.json()["results"]
    usernames = [row["username"] for row in results]
    assert "imola" in usernames
    # Il referente non può consuntivare: non è un autore proponibile.
    assert "referente-solo-lettura" not in usernames
    assert next(row for row in results if row["username"] == "imola") == {
        "id": imola.pk,
        "username": "imola",
        "full_name": "Mario Rossi",
        "roles": [roles.SUPPLIER],
    }

    supplier, _ = make_client_for_role(roles.SUPPLIER)
    assert supplier.get("/api/v1/timesheets/authors").status_code == 403


def test_admin_intesta_il_consuntivo_di_progetto_a_imola():
    admin, admin_user = make_client_for_role(roles.ADMIN)
    imola = make_supplier_user("imola")
    project = ProjectFactory(code="PRJ-AUTORE", budget_days=Decimal("10.0000"))

    response = admin.post(
        f"/api/v1/projects/{project.id}/ledger",
        {
            "giornate": "2",
            "data": "2026-10-20",
            "descrizione": "Consuntivo registrato per Imola",
            "utente": imola.pk,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    entry = TimesheetEntry.objects.get(project=project)
    assert entry.created_by == imola
    assert entry.updated_by == admin_user

    ledger = admin.get(f"/api/v1/projects/{project.id}/ledger").json()["consuntivi"][0]
    assert ledger["utente"] == "Mario Rossi"
    assert ledger["utente_id"] == imola.pk


def test_senza_utente_il_consuntivo_resta_di_chi_scrive():
    admin, admin_user = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(code="PRJ-AUTORE-DEFAULT", budget_days=Decimal("10.0000"))

    response = admin.post(
        f"/api/v1/projects/{project.id}/ledger",
        {"giornate": "1", "data": "2026-10-20", "descrizione": "Consuntivo proprio"},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert TimesheetEntry.objects.get(project=project).created_by == admin_user


def test_il_fornitore_non_puo_intestare_il_consuntivo_a_un_altro_utente():
    supplier, supplier_user = make_client_for_role(roles.SUPPLIER)
    altro = make_supplier_user("imola")
    project = ProjectFactory(code="PRJ-AUTORE-NEGATO", budget_days=Decimal("10.0000"))

    response = supplier.post(
        f"/api/v1/projects/{project.id}/ledger",
        {
            "giornate": "1",
            "data": "2026-10-20",
            "descrizione": "Tentativo per conto terzi",
            "utente": altro.pk,
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "utente" in response.json()
    assert not TimesheetEntry.objects.filter(project=project).exists()
    assert supplier_user != altro


def test_utente_inesistente_o_non_abilitato_viene_rifiutato():
    admin, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(code="PRJ-AUTORE-INVALIDO", budget_days=Decimal("10.0000"))
    referente = UserFactory(username="referente-non-consuntiva")
    roles.ensure_groups()
    referente.groups.add(Group.objects.get(name=roles.REFERENT))

    for value in (999999, referente.pk):
        response = admin.post(
            f"/api/v1/projects/{project.id}/ledger",
            {"giornate": "1", "data": "2026-10-20", "descrizione": "x", "utente": value},
            format="json",
        )
        assert response.status_code == 400, response.data
        assert "utente" in response.json()
    assert not TimesheetEntry.objects.filter(project=project).exists()


def test_admin_intesta_a_imola_anche_il_consuntivo_del_canone():
    admin, admin_user = make_client_for_role(roles.ADMIN)
    imola = make_supplier_user("imola")
    row = CanoneSubactivityFactory(
        reserved_days=Decimal("5.0000"),
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
    )

    response = admin.post(
        f"/api/v1/canoni/{row.canone_id}/subactivities/{row.id}/timesheets",
        {
            "data": "2026-07-15",
            "giornate": "2",
            "descrizione": "Attività svolta da Imola",
            "utente": imola.pk,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    entry = TimesheetEntry.objects.get(canone_subactivity=row)
    assert entry.created_by == imola
    assert entry.updated_by == admin_user
    consuntivo = next(
        sub for sub in response.json()["subactivities"] if sub["id"] == str(row.id)
    )["consuntivi"][0]
    assert consuntivo["utente_id"] == imola.pk


def test_la_rettifica_admin_puo_cambiare_l_autore_del_consuntivo():
    admin, _ = make_client_for_role(roles.ADMIN)
    imola = make_supplier_user("imola")
    project = ProjectFactory(code="PRJ-AUTORE-RETTIFICA", budget_days=Decimal("10.0000"))
    created = admin.post(
        f"/api/v1/projects/{project.id}/ledger",
        {"giornate": "1", "data": "2026-10-20", "descrizione": "Prima stesura"},
        format="json",
    )
    entry_id = created.json()["id"]

    response = admin.patch(
        f"/api/v1/projects/{project.id}/ledger/{entry_id}",
        {
            "giornate": "1",
            "data": "2026-10-20",
            "descrizione": "Prima stesura",
            "utente": imola.pk,
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    replacement = TimesheetEntry.objects.get(pk=response.json()["id"])
    assert replacement.created_by == imola


def test_la_capability_non_e_assegnabile_agli_altri_ruoli():
    admin, _ = make_client_for_role(roles.ADMIN)

    response = admin.put(
        "/api/v1/admin/roles/capabilities",
        {
            "role": roles.SUPPLIER,
            "capabilities": [capabilities.ASSIGN_TIMESHEET_AUTHOR],
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert capabilities.ASSIGN_TIMESHEET_AUTHOR not in capabilities.capabilities_for_role(
        roles.SUPPLIER
    )
