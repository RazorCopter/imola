from __future__ import annotations

from decimal import Decimal

import pytest

from core import roles
from projects.models import (
    ContractType,
    OfferStatus,
    TimesheetStatus,
)
from tests.factories import (
    OrganizationFactory,
    PersonFactory,
    ProjectFactory,
    SupplierOrganizationFactory,
)
from tests.test_roles_object_permissions import make_client_for_role

pytestmark = pytest.mark.django_db


def test_admin_patch_completo_progetto():
    client, _ = make_client_for_role(roles.ADMIN)
    bmed_org = OrganizationFactory(code="BMED-TEST")
    imola_org = SupplierOrganizationFactory(code="IMOLA-TEST")
    client_person = PersonFactory(full_name="Referente BMED Test", organization=bmed_org)
    supplier_person = PersonFactory(full_name="Referente Imola Test", organization=imola_org)

    project = ProjectFactory(
        code="IM26099-TEST",
        title="Titolo Originale",
        budget_days=Decimal("12.5000"),
        contract_type=ContractType.AQL,
        offer_status=OfferStatus.ACCETTATA,
        timesheet_status=TimesheetStatus.NON_AVVIATO,
    )

    payload = {
        "expected_version": project.version,
        "title": "Titolo Aggiornato",
        "contract_type": ContractType.CORPO,
        "budget_days": "18.0000",
        "aro_code": "ARO-99",
        "rda_code": "RDA-99",
        "deliverable": "Doc di sintesi",
        "client_owner": client_person.id,
        "supplier_owner": supplier_person.id,
        "start_date": "2026-02-01",
        "planned_end_date": "2026-10-31",
        "notes": "Note aggiornate",
    }

    res = client.patch(f"/api/v1/projects/{project.id}", payload, format="json")
    assert res.status_code == 200, res.data
    data = res.json()
    assert data["title"] == "Titolo Aggiornato"
    assert data["contract_type"] == ContractType.CORPO
    assert data["budget_days"] == "18.0000"
    assert data["aro_code"] == "ARO-99"
    assert str(data["client_owner"]) == str(client_person.id)
    assert str(data["supplier_owner"]) == str(supplier_person.id)
    assert data["version"] == 2
    assert "ETag" in res.headers


def test_referente_puo_modificare_solo_campi_annotazione_sul_proprio():
    owner = PersonFactory(full_name="Referente Mio", email="referente.mio@example.com")
    project = ProjectFactory(client_owner=owner, notes="Iniziale")
    client, _ = make_client_for_role(roles.REFERENT, email="referente.mio@example.com")

    # Consentito: notes, planned_end_date
    res_ok = client.patch(
        f"/api/v1/projects/{project.id}",
        {
            "expected_version": project.version,
            "notes": "Nuova nota",
            "planned_end_date": "2026-12-15",
        },
        format="json",
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["notes"] == "Nuova nota"

    # Vietato per referente: budget_days o contract_type -> 403 Forbidden dal permission check
    res_forbidden_field = client.patch(
        f"/api/v1/projects/{project.id}",
        {
            "expected_version": res_ok.json()["version"],
            "budget_days": "20.0000",
        },
        format="json",
    )
    assert res_forbidden_field.status_code == 403


def test_patch_senza_versione_restituisce_428():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory()
    res = client.patch(f"/api/v1/projects/{project.id}", {"notes": "Senza versione"}, format="json")
    assert res.status_code == 428


def test_patch_versione_obsoleta_restituisce_409():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(notes="Iniziale")
    project.notes = "Modifica parallela"
    project.save()

    res = client.patch(
        f"/api/v1/projects/{project.id}",
        {"expected_version": 1, "notes": "Modifica in ritardo"},
        format="json",
    )
    assert res.status_code == 409
    assert res.json()["code"] == "risorsa-obsoleta"


def test_chiusura_richiede_actual_closure_date_invariante_d03():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(
        timesheet_status=TimesheetStatus.ATTIVO,
        offer_status=OfferStatus.ACCETTATA,
        actual_closure_date=None,
    )

    # Passare a CHIUSO senza data_chiusura fallisce
    res = client.patch(
        f"/api/v1/projects/{project.id}",
        {
            "expected_version": project.version,
            "timesheet_status": TimesheetStatus.CHIUSO,
            "actual_closure_date": None,
        },
        format="json",
    )
    assert res.status_code == 400
    assert "actual_closure_date" in str(res.json())

    # Con actual_closure_date valida ha successo
    res_ok = client.patch(
        f"/api/v1/projects/{project.id}",
        {
            "expected_version": project.version,
            "timesheet_status": TimesheetStatus.CHIUSO,
            "actual_closure_date": "2026-06-30",
        },
        format="json",
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["timesheet_status"] == TimesheetStatus.CHIUSO


def test_cambio_codice_rifiutato_come_campo_non_modificabile():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory(code="IM-ORIGINALE")
    res = client.patch(
        f"/api/v1/projects/{project.id}",
        {"expected_version": project.version, "code": "IM-NUOVO-CODICE"},
        format="json",
    )
    assert res.status_code == 400
    project.refresh_from_db()
    assert project.code == "IM-ORIGINALE"


def test_campi_calcolati_e_provenienza_rifiutati():
    client, _ = make_client_for_role(roles.ADMIN)
    project = ProjectFactory()
    for field in ("residual_reference_year", "import_batch", "created_by", "version"):
        res = client.patch(
            f"/api/v1/projects/{project.id}",
            {"expected_version": project.version, field: "valore_abusivo"},
            format="json",
        )
        assert res.status_code == 400


def test_endpoint_options_progetti():
    client, _ = make_client_for_role(roles.ADMIN)
    res = client.get("/api/v1/projects/options")
    assert res.status_code == 200
    data = res.json()
    assert "contract_types" in data
    assert "offer_statuses" in data
    assert "timesheet_statuses" in data
    assert "billing_statuses" in data
    assert "organizations" in data
    assert "people" in data
