"""API di sessione ed errori in formato RFC 7807.

Il punto delicato: una richiesta non autenticata deve rispondere **401** con
`code=session_expired`, non 403. Il frontend distingue i due casi per decidere se mostrare
la pagina di accesso o il modale di re-login che conserva il lavoro in corso.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, User
from rest_framework.test import APIClient

from core import roles

pytestmark = pytest.mark.django_db

PASSWORD = "password-molto-lunga-123"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def manager() -> User:
    roles.ensure_groups()
    user = User.objects.create_user("responsabile", password=PASSWORD)
    user.groups.add(Group.objects.get(name=roles.MANAGER))
    return user


class TestSessioneNonAutenticata:
    def test_risponde_401_e_non_403(self, client):
        response = client.get("/api/v1/auth/session")
        assert response.status_code == 401

    def test_il_corpo_e_problem_json_in_italiano(self, client):
        response = client.get("/api/v1/auth/session")
        assert response["Content-Type"].startswith("application/problem+json")
        body = response.json()
        assert body["code"] == "session_expired"
        assert body["status"] == 401
        assert body["title"] == "Autenticazione necessaria"
        assert body["instance"] == "/api/v1/auth/session"
        assert "accesso" in body["detail"]

    def test_anche_le_viste_di_dominio_rispondono_401(self, client):
        for path in ("/api/v1/projects/balances", "/api/v1/wallet/2026/balance"):
            assert client.get(path).status_code == 401


class TestLogin:
    def test_login_restituisce_ruoli_e_permessi(self, client, manager):
        response = client.post(
            "/api/v1/auth/login",
            {"username": "responsabile", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "responsabile"
        assert body["roles"] == [roles.MANAGER]
        assert body["can_write"] is True
        assert body["is_admin"] is False

    def test_credenziali_errate_danno_401_con_codice_dedicato(self, client, manager):
        response = client.post(
            "/api/v1/auth/login",
            {"username": "responsabile", "password": "sbagliata"},
            format="json",
        )
        assert response.status_code == 401
        assert response.json()["code"] == "credenziali-non-valide"

    def test_utenza_disattivata_rifiutata(self, client, manager):
        manager.is_active = False
        manager.save()
        response = client.post(
            "/api/v1/auth/login",
            {"username": "responsabile", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 401

    def test_campi_mancanti_danno_400_con_elenco_errori(self, client):
        response = client.post("/api/v1/auth/login", {}, format="json")
        assert response.status_code == 400
        body = response.json()
        assert body["status"] == 400
        assert {error["campo"] for error in body["errors"]} == {"username", "password"}

    def test_dopo_il_login_la_sessione_e_leggibile(self, client, manager):
        client.force_login(manager)
        response = client.get("/api/v1/auth/session")
        assert response.status_code == 200
        assert response.json()["username"] == "responsabile"

    def test_logout(self, client, manager):
        client.force_login(manager)
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.get("/api/v1/auth/session").status_code == 401


class TestImpostazioni:
    def test_lettura_consentita_a_chi_e_autenticato(self, client, manager):
        client.force_login(manager)
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        body = response.json()
        assert body["ore_per_giornata"] == "8.00"  # stringa: niente float sui decimali
        assert body["tolleranza_riconciliazione_gg"] == "0.0100"
        assert body["anni_validita_dopo_chiusura"] == 1

    def test_modifica_riservata_agli_amministratori(self, client, manager):
        client.force_login(manager)
        response = client.patch(
            "/api/v1/settings", {"anni_validita_dopo_chiusura": 2}, format="json"
        )
        assert response.status_code == 403
        assert response.json()["status"] == 403

    def test_un_amministratore_puo_modificare(self, client):
        roles.ensure_groups()
        admin = User.objects.create_superuser("amministratore", password=PASSWORD)
        client.force_login(admin)
        response = client.patch(
            "/api/v1/settings", {"anni_validita_dopo_chiusura": 2}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["anni_validita_dopo_chiusura"] == 2


class TestVisteCalcolate:
    def test_bilancio_wallet_di_un_anno_vuoto(self, client, manager):
        client.force_login(manager)
        response = client.get("/api/v1/wallet/2026/balance")
        assert response.status_code == 200
        body = response.json()
        assert body["anno"] == 2026
        assert body["allocato"] == "0.0000"
        assert body["disponibile"] == "0.0000"

    def test_i_bilanci_progetto_spiegano_il_calcolo(self, client, manager):
        from decimal import Decimal

        from tests.factories import ProjectFactory, TimesheetEntryFactory

        project = ProjectFactory(code="IM26-API", budget_days=Decimal("10.0000"))
        TimesheetEntryFactory(project=project, days=Decimal("2.5000"))

        client.force_login(manager)
        response = client.get("/api/v1/projects/balances")
        assert response.status_code == 200
        row = next(r for r in response.json()["results"] if r["codice"] == "IM26-API")
        assert row["residuo"] == "7.5000"
        assert row["stato_residuo"] == "VALIDO"
        assert "7,50 gg" in row["spiegazione_residuo"]

    def test_la_riconciliazione_risponde_anche_senza_snapshot(self, client, manager):
        client.force_login(manager)
        response = client.get("/api/v1/reconciliation/latest")
        assert response.status_code == 200
        assert response.json()["riepilogo"]["righe"] == 0
