from __future__ import annotations

from decimal import Decimal

import pytest

from anomalies.models import Anomaly, AnomalyStatus, Scope, Severity
from anomalies.runner import run_checks
from domain.checks import RULES, Finding

pytestmark = pytest.mark.django_db


def test_catalogo_contiene_esattamente_diciotto_regole():
    assert len(RULES) == 18
    assert len(set(RULES)) == 18
    assert all(code.startswith("CHK_") for code in RULES)


@pytest.mark.parametrize("rule_code", sorted(RULES))
def test_ogni_regola_ha_un_negativo_su_database_vuoto(rule_code):
    assert list(RULES[rule_code]()) == []


def test_runner_crea_aggiorna_e_risolve_senza_duplicare(monkeypatch):
    active = True

    def detector():
        if active:
            yield Finding(
                "CHK_TEST",
                "ENTITY-1",
                Severity.MEDIA,
                Scope.PROGETTO,
                "Descrizione iniziale",
                context={"value": str(Decimal("1.0000"))},
            )

    monkeypatch.setitem(RULES, "CHK_TEST", detector)
    first = run_checks(["CHK_TEST"])
    second = run_checks(["CHK_TEST"])

    assert first.created == 1
    assert second.created == 0
    assert second.updated == 1
    assert Anomaly.objects.filter(rule_code="CHK_TEST").count() == 1

    active = False
    third = run_checks(["CHK_TEST"])
    anomaly = Anomaly.objects.get(rule_code="CHK_TEST")
    assert third.resolved == 1
    assert anomaly.status == AnomalyStatus.RISOLTA


def test_deroga_attiva_viene_rispettata(monkeypatch):
    def detector():
        yield Finding("CHK_TEST", "ENTITY-1", Severity.BASSA, Scope.ANAGRAFICA, "Dato")

    monkeypatch.setitem(RULES, "CHK_TEST", detector)
    run_checks(["CHK_TEST"])
    anomaly = Anomaly.objects.get(rule_code="CHK_TEST")
    anomaly.accept("Deroga approvata")
    anomaly.save()

    report = run_checks(["CHK_TEST"])

    anomaly.refresh_from_db()
    assert report.created == 0
    assert anomaly.status == AnomalyStatus.ACCETTATA
