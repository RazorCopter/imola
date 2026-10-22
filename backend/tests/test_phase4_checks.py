from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from anomalies.models import Anomaly, AnomalyStatus, Scope, Severity
from anomalies.runner import run_checks
from domain.checks import (
    RULES,
    Finding,
    check_active_without_offer,
    check_canone_overuse,
    check_milestone_slipped,
    check_overrun_allocation,
    check_residual_expiring,
    check_residual_unallocated_closed,
)
from projects.models import BillingMilestone, OfferStatus, TimesheetStatus
from tests.factories import (
    CanoneFactory,
    CanoneSubactivityFactory,
    ProjectFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)
from timesheets.models import TimesheetEntry, TimesheetSource

pytestmark = pytest.mark.django_db

EXPECTED_RULES = {
    "CHK_DATE_ORDER",
    "CHK_END_PASSED_ACTIVE",
    "CHK_CLOSED_NO_DATE",
    "CHK_OVERRUN_PROJECT",
    "CHK_OVERRUN_ALLOCATION",
    "CHK_ALLOC_EXCEEDS_RESIDUAL",
    "CHK_RESIDUAL_EXPIRING",
    "CHK_RESIDUAL_UNALLOCATED_CLOSED",
    "CHK_ALLOC_FROM_EXPIRED",
    "CHK_RECON_DELTA",
    "CHK_MISSING_IN_PPM",
    "CHK_DOUBLE_COUNT",
    "CHK_CANONE_UNDERUSE",
    "CHK_CANONE_OVERUSE",
    "CHK_ACTIVE_WITHOUT_OFFER",
    "CHK_ALLOC_NO_SOURCE",
    "CHK_UNVERIFIED_DATA",
    "CHK_MILESTONE_SLIPPED",
}


def test_catalogo_contiene_esattamente_diciotto_regole_della_spec():
    assert set(RULES) == EXPECTED_RULES
    assert len(RULES) == 18


@pytest.mark.parametrize("rule_code", sorted(EXPECTED_RULES))
def test_ogni_regola_ha_un_negativo_su_database_vuoto(rule_code):
    assert list(RULES[rule_code]()) == []


def test_chk_residual_expiring_dopo_chiusura_im24517():
    project = ProjectFactory(
        code="IM24517-TEST",
        title="Solution design consulenza",
        budget_days=Decimal("25.0000"),
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=date(2025, 5, 30),
    )
    TimesheetEntry.objects.create(
        project=project,
        days=Decimal("11.6900"),
        source=TimesheetSource.SEED_INIZIALE,
        period=date(2025, 5, 1),
    )
    year = WalletYearFactory(year=2025)
    activity = WalletActivityFactory(code="STORICO-IM24517")
    WalletAllocationFactory(
        wallet_year=year,
        source_project=project,
        activity=activity,
        allocated_days=Decimal("1.0000"),
        external_ref="STORICO-IM24517",
    )
    as_of = date(2026, 10, 16)

    findings = list(check_residual_expiring(as_of=as_of))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_code == "CHK_RESIDUAL_EXPIRING"
    assert finding.entity_ref == "IM24517"
    assert finding.context["unallocated_days"] == "12.3100"
    assert finding.context["expires_on"] == "2026-12-31"


def test_chk_residual_unallocated_closed_zero_se_progetto_chiuso_senza_data():
    from tests.factories import ImportBatchFactory

    batch = ImportBatchFactory()
    ProjectFactory(
        code="IM26034-TEST",
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date=None,
        import_batch=batch,
    )
    assert list(check_residual_unallocated_closed(as_of=date(2026, 10, 16))) == []


def test_chk_overrun_allocation_rileva_superamento_budget_allocato():
    year = WalletYearFactory(year=2026)
    activity = WalletActivityFactory(code="ACT-1")
    alloc = WalletAllocationFactory(
        wallet_year=year,
        activity=activity,
        allocated_days=Decimal("5.0000"),
        external_ref="W26-TEST",
    )
    TimesheetEntry.objects.create(
        wallet_allocation=alloc,
        days=Decimal("6.0000"),
        source=TimesheetSource.SEED_INIZIALE,
        period=date(2026, 5, 1),
    )

    findings = list(check_overrun_allocation())
    assert len(findings) == 1
    assert findings[0].entity_ref == "W26-TEST"
    assert findings[0].severity == Severity.ALTA


def test_chk_canone_overuse_rileva_sforamento_monte():
    project = ProjectFactory(code="CAN-1")
    canone = CanoneFactory(project=project, semester="2026-S1", total_days=Decimal("10.0000"))
    sub = CanoneSubactivityFactory(canone=canone, title="Sub 1")
    TimesheetEntry.objects.create(
        canone_subactivity=sub,
        days=Decimal("12.0000"),
        source=TimesheetSource.SEED_INIZIALE,
        period=date(2026, 3, 1),
    )

    findings = list(check_canone_overuse())
    assert len(findings) == 1
    assert findings[0].rule_code == "CHK_CANONE_OVERUSE"
    assert findings[0].severity == Severity.ALTA


def test_chk_active_without_offer_rileva_progetti_non_accettati():
    ProjectFactory(
        code="IM-NO-OFFER",
        timesheet_status=TimesheetStatus.ATTIVO,
        offer_status=OfferStatus.INVIATA,
    )
    findings = list(check_active_without_offer())
    assert len(findings) == 1
    assert findings[0].entity_ref == "IM"


def test_chk_milestone_slipped_rileva_slittamenti():
    project = ProjectFactory(code="IM-MILE")
    milestone = BillingMilestone.objects.create(
        project=project,
        planned_date=date(2026, 1, 1),
        move_count=2,
    )
    findings = list(check_milestone_slipped())
    assert len(findings) == 1
    assert findings[0].entity_ref == str(milestone.id)


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
    assert second.updated == 0
    assert Anomaly.objects.filter(rule_code="CHK_TEST").count() == 1

    def updated_detector():
        if active:
            yield Finding(
                "CHK_TEST",
                "ENTITY-1",
                Severity.MEDIA,
                Scope.PROGETTO,
                "Descrizione aggiornata",
                context={"value": str(Decimal("2.0000"))},
            )

    monkeypatch.setitem(RULES, "CHK_TEST", updated_detector)
    updated_run = run_checks(["CHK_TEST"])
    assert updated_run.updated == 1
    assert Anomaly.objects.get(rule_code="CHK_TEST").description == "Descrizione aggiornata"

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
