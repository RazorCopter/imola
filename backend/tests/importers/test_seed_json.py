"""Test mirati per l'importer seed JSON."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from anomalies.models import (
    SEED_RULE_CODE,
    Anomaly,
    AnomalyStatus,
    build_fingerprint,
)
from canone.models import Canone, CanoneSubactivity
from core.models import AppSettings, Reliability
from directory.models import Organization, OrganizationKind, Person
from importers.report import ImportReport
from importers.seed_json import import_foundation
from ppm.models import PpmSnapshot, PpmSnapshotRow
from projects.models import BillingMilestone, Project
from tests.factories import ImportBatchFactory
from timesheets.models import TimesheetEntry, TimesheetSource
from wallet.models import (
    ActivityKind,
    AllocationStatus,
    WalletActivity,
    WalletAllocation,
    WalletYear,
)

pytestmark = pytest.mark.django_db


def foundation_payload() -> dict:
    return {
        "configurazione": {
            "cliente": {"codice": "BMED", "ragione_sociale": "Banca Mediolanum"},
            "fornitore": {"codice": "IMOLA", "ragione_sociale": "Imola Informatica"},
            "ore_per_giornata": Decimal("7.50"),
            "granularita_ppm_gg": Decimal("0.0625"),
            "tolleranza_riconciliazione_gg": Decimal("0.0100"),
            "regola_scadenza_residui": {"anni_validita_dopo_chiusura": 2},
        },
        "persone": [
            {"nome": "  Andrea   Ravagli ", "organizzazione": "BMED", "email": None},
            {"nome": "Ravagli Andrea", "organizzazione": "IMOLA", "email": None},
            {"nome": "Marco", "organizzazione": "IMOLA", "email": None},
        ],
        "meta": {"data_riferimento_dati": "2026-10-16"},
        "progetti": [],
        "canoni": [],
        "wallet": {"anno": 2026, "attivita": [], "allocazioni": []},
    }


def make_report() -> ImportReport:
    return ImportReport(kind="SEED_JSON", source_filename="seed_demo.json", dry_run=False)


def test_importa_configurazione_organizzazioni_e_persone_con_batch():
    batch = ImportBatchFactory()
    report = make_report()

    import_foundation(foundation_payload(), batch=batch, report=report)

    settings = AppSettings.objects.get(singleton=True)
    assert settings.hours_per_day == Decimal("7.50")
    assert settings.ppm_granularity_days == Decimal("0.0625")
    assert settings.reconciliation_tolerance_days == Decimal("0.0100")
    assert settings.residual_years_after_closure == 2

    bmed = Organization.objects.get(code="BMED")
    imola = Organization.objects.get(code="IMOLA")
    assert (bmed.name, bmed.kind, bmed.import_batch) == (
        "Banca Mediolanum",
        OrganizationKind.CLIENT,
        batch,
    )
    assert (imola.name, imola.kind, imola.import_batch) == (
        "Imola Informatica",
        OrganizationKind.SUPPLIER,
        batch,
    )

    assert Person.objects.count() == 3
    assert Person.objects.get(organization=bmed).full_name == "Andrea Ravagli"
    imola_person = Person.objects.get(organization=imola, name_key="andrea ravagli")
    assert imola_person.full_name == "Ravagli Andrea"
    assert imola_person.import_batch == batch
    partial = Person.objects.get(organization=imola, full_name="Marco")
    assert partial.needs_review is True
    assert "Nome parziale" in partial.review_note

    assert report.counts() == {"configurazione": 1, "organizzazioni": 2, "persone": 3}
    assert report.updated_total == 0


def test_secondo_import_e_idempotente():
    payload = foundation_payload()
    first_batch = ImportBatchFactory(source_filename="first.json")
    import_foundation(payload, batch=first_batch, report=make_report())

    second_report = make_report()
    import_foundation(
        payload,
        batch=ImportBatchFactory(source_filename="second.json"),
        report=second_report,
    )

    assert second_report.created_total == 0
    assert second_report.updated_total == 0
    assert second_report.entity("configurazione").unchanged == 1
    assert second_report.entity("organizzazioni").unchanged == 2
    assert second_report.entity("persone").unchanged == 3
    assert Organization.objects.count() == 2
    assert Person.objects.count() == 3
    assert set(Organization.objects.values_list("import_batch", flat=True)) == {first_batch.id}
    assert set(Person.objects.values_list("import_batch", flat=True)) == {first_batch.id}


def test_aggiorna_record_preesistenti_senza_appropriarsi_del_batch():
    original_batch = ImportBatchFactory(source_filename="original.json")
    first_report = make_report()
    payload = foundation_payload()
    import_foundation(payload, batch=original_batch, report=first_report)

    payload["configurazione"]["cliente"]["ragione_sociale"] = "Banca Mediolanum S.p.A."
    payload["persone"][0]["email"] = "andrea.ravagli@example.test"
    new_batch = ImportBatchFactory(source_filename="update.json")
    report = make_report()

    import_foundation(payload, batch=new_batch, report=report)

    bmed = Organization.objects.get(code="BMED")
    person = Person.objects.get(organization=bmed, full_name="Andrea Ravagli")
    assert bmed.name == "Banca Mediolanum S.p.A."
    assert person.email == "andrea.ravagli@example.test"
    assert bmed.import_batch == original_batch
    assert person.import_batch == original_batch
    assert report.entity("organizzazioni").updated == 1
    assert report.entity("persone").updated == 1
    assert report.entity("organizzazioni").updated_rows[0]["chiave"] == "BMED"


def project_row(**overrides) -> dict:
    row = {
        "codice": "IM26-IMPORT",
        "titolo": "Progetto importato",
        "tipo_contratto": "AQL",
        "codice_aro": None,
        "codice_rda": "RDA-1",
        "deliverable": "TE200",
        "referente_bmed": "Andrea Ravagli",
        "referente_imola": "Ravagli Andrea",
        "gg_budget": Decimal("12.0000"),
        "gg_consumati_su_progetto": Decimal("5.2500"),
        "data_inizio": "2026-01-10",
        "data_fine_prevista": "2026-12-31",
        "data_chiusura_consuntivazione": None,
        "anno_riferimento_residuo": None,
        "milestone_fatturazione": [
            {"data_prevista": "2026-05-01", "stato": "PIANIFICATA"},
            {"data_prevista": "2026-09-01", "stato": "DA_VERIFICARE"},
        ],
        "stato_offerta": "ACCETTATA",
        "stato_consuntivazione": "ATTIVO",
        "stato_fatturazione": "PARZIALE",
        "stato_excel_originale": "In corso",
        "note": "Nota seed",
        "affidabilita": "DA_VERIFICARE",
        "punti_da_verificare": ["Confermare la data finale"],
    }
    row.update(overrides)
    return row


def test_importa_progetto_milestone_e_consuntivo_iniziale():
    payload = foundation_payload()
    payload["progetti"] = [project_row()]
    batch = ImportBatchFactory()
    report = make_report()

    import_foundation(payload, batch=batch, report=report)

    project = Project.objects.get(code="IM26-IMPORT")
    assert project.import_batch == batch
    assert project.client_owner == Person.objects.get(
        organization__code="BMED", name_key="andrea ravagli"
    )
    assert project.supplier_owner == Person.objects.get(
        organization__code="IMOLA", name_key="andrea ravagli"
    )
    assert project.reliability == Reliability.DA_VERIFICARE
    assert project.verification_points[0]["testo"] == "Confermare la data finale"
    assert project.declared_residual_year is None

    assert BillingMilestone.objects.filter(project=project).count() == 2
    assert all(item.import_batch == batch for item in project.milestones.all())
    entry = TimesheetEntry.objects.get(project=project)
    assert (entry.period, entry.days, entry.source, entry.import_batch) == (
        date(2026, 10, 1),
        Decimal("5.2500"),
        TimesheetSource.SEED_INIZIALE,
        batch,
    )
    assert report.counts()["progetti"] == 1
    assert report.counts()["milestone"] == 2
    assert report.counts()["consuntivi_progetto"] == 1


def test_reimport_progetti_e_idempotente_e_non_riassegna_il_batch():
    payload = foundation_payload()
    payload["progetti"] = [project_row()]
    first_batch = ImportBatchFactory()
    import_foundation(payload, batch=first_batch, report=make_report())

    second_report = make_report()
    import_foundation(payload, batch=ImportBatchFactory(), report=second_report)

    assert Project.objects.count() == 1
    assert BillingMilestone.objects.count() == 2
    assert TimesheetEntry.objects.count() == 1
    project = Project.objects.get()
    assert project.import_batch == first_batch
    assert all(item.import_batch == first_batch for item in project.milestones.all())
    assert TimesheetEntry.objects.get().import_batch == first_batch
    assert second_report.created_total == 0
    assert second_report.updated_total == 0
    assert second_report.entity("progetti").unchanged == 1
    assert second_report.entity("milestone").unchanged == 2
    assert second_report.entity("consuntivi_progetto").unchanged == 1


def test_aggiorna_progetto_senza_appropriarsi_del_batch_e_report_serializzabile():
    payload = foundation_payload()
    payload["progetti"] = [project_row()]
    first_batch = ImportBatchFactory()
    import_foundation(payload, batch=first_batch, report=make_report())

    payload["progetti"][0]["titolo"] = "Titolo aggiornato"
    payload["progetti"][0]["referente_bmed"] = None
    report = make_report()
    import_foundation(payload, batch=ImportBatchFactory(), report=report)

    project = Project.objects.get()
    assert project.title == "Titolo aggiornato"
    assert project.client_owner is None
    assert project.import_batch == first_batch
    changes = report.entity("progetti").updated_rows[0]["modifiche"]
    assert changes["client_owner"]["dopo"] is None
    assert isinstance(changes["client_owner"]["prima"], str)
    report.as_dict()


def test_zero_duplicato_milestone_e_delta_append_only_sono_segnalati():
    payload = foundation_payload()
    payload["progetti"] = [
        project_row(
            codice="IM26-ZERO",
            gg_consumati_su_progetto=Decimal("0"),
            milestone_fatturazione=[
                {"data_prevista": "2026-05-01", "stato": "PIANIFICATA"},
                {"data_prevista": "2026-05-01", "stato": "FATTURATA"},
            ],
        ),
        project_row(codice="IM26-DELTA"),
    ]
    first_report = make_report()
    import_foundation(payload, batch=ImportBatchFactory(), report=first_report)

    assert not TimesheetEntry.objects.filter(project__code="IM26-ZERO").exists()
    assert len(first_report.entity("milestone").skipped) == 1
    assert len(first_report.entity("consuntivi_progetto").skipped) == 1

    payload["progetti"][1]["gg_consumati_su_progetto"] = Decimal("6.0000")
    second_report = make_report()
    import_foundation(payload, batch=ImportBatchFactory(), report=second_report)

    entry = TimesheetEntry.objects.get(project__code="IM26-DELTA")
    assert entry.days == Decimal("5.2500")
    assert any("non applicata, usare un import PPM" in item for item in second_report.warnings)


def canone_row(**overrides) -> dict:
    row = {
        "codice_progetto": "IM26-CANONE",
        "semestre": "2026-S2",
        "monte_gg": Decimal("173.0000"),
        "data_estrazione": "2026-10-16",
        "formula_target": {
            "base_gg": Decimal("2.0000"),
            "gg_per_settimana": Decimal("6.6900"),
            "settimane_trascorse": 15,
            "cap_al_monte": True,
        },
        "sottoattivita": [
            {
                "ufficio": "EA",
                "titolo": "#300228 [Studio AIL] Identificazione pattern",
                "gg_consuntivati": Decimal("12.1800"),
                "stima_trimestre": Decimal("15.0000"),
                "forecast_residuo_31_12": Decimal("3.0000"),
                "note": "Dato seed",
            },
            {
                "ufficio": None,
                "titolo": "Presidio architetturale",
                "gg_consuntivati": Decimal("0"),
                "stima_trimestre": None,
                "forecast_residuo_31_12": None,
                "note": None,
            },
        ],
    }
    row.update(overrides)
    return row


def canone_payload() -> dict:
    payload = foundation_payload()
    payload["progetti"] = [project_row(codice="IM26-CANONE", gg_consumati_su_progetto=Decimal("0"))]
    payload["canoni"] = [canone_row()]
    return payload


def test_importa_canone_sottoattivita_e_consuntivo_iniziale():
    payload = canone_payload()
    batch = ImportBatchFactory()
    report = make_report()

    import_foundation(payload, batch=batch, report=report)

    canone = Canone.objects.get(project__code="IM26-CANONE", semester="2026-S2")
    assert canone.import_batch == batch
    assert (canone.start_date, canone.end_date, canone.extracted_at) == (
        date(2026, 7, 1),
        date(2026, 12, 31),
        date(2026, 10, 16),
    )
    assert canone.total_days == Decimal("173.0000")
    assert canone.target_base_days == Decimal("2.0000")
    assert canone.target_days_per_week == Decimal("6.6900")
    assert canone.weeks_elapsed_at_import == 15
    assert canone.cap_at_total is True

    redmine = CanoneSubactivity.objects.get(canone=canone, title__startswith="#300228")
    assert redmine.import_batch == batch
    assert redmine.redmine_ref == "300228"
    assert redmine.needs_review is False
    assert redmine.quarter_estimate_days == Decimal("15.0000")
    assert redmine.forecast_remaining_days == Decimal("3.0000")
    entry = TimesheetEntry.objects.get(canone_subactivity=redmine)
    assert (entry.period, entry.days, entry.source, entry.import_batch) == (
        date(2026, 10, 1),
        Decimal("12.1800"),
        TimesheetSource.SEED_INIZIALE,
        batch,
    )
    assert not TimesheetEntry.objects.filter(
        canone_subactivity__title="Presidio architetturale"
    ).exists()
    assert report.counts()["canoni"] == 1
    assert report.counts()["sottoattivita_canone"] == 2
    assert report.counts()["consuntivi_canone"] == 1
    assert len(report.entity("consuntivi_canone").skipped) == 1


def test_reimport_canone_e_idempotente_e_non_riassegna_batch():
    payload = canone_payload()
    original_batch = ImportBatchFactory(source_filename="original.json")
    import_foundation(payload, batch=original_batch, report=make_report())

    second_report = make_report()
    import_foundation(
        payload,
        batch=ImportBatchFactory(source_filename="second.json"),
        report=second_report,
    )

    assert Canone.objects.count() == 1
    assert CanoneSubactivity.objects.count() == 2
    assert TimesheetEntry.objects.filter(canone_subactivity__isnull=False).count() == 1
    assert Canone.objects.get().import_batch == original_batch
    assert all(item.import_batch == original_batch for item in CanoneSubactivity.objects.all())
    assert second_report.entity("canoni").unchanged == 1
    assert second_report.entity("sottoattivita_canone").unchanged == 2
    assert second_report.entity("consuntivi_canone").unchanged == 1


def test_aggiorna_canone_e_sottoattivita_ma_non_il_consuntivo_append_only():
    payload = canone_payload()
    original_batch = ImportBatchFactory(source_filename="original.json")
    import_foundation(payload, batch=original_batch, report=make_report())
    payload["canoni"][0]["monte_gg"] = Decimal("180.0000")
    payload["canoni"][0]["formula_target"]["settimane_trascorse"] = 16
    payload["canoni"][0]["sottoattivita"][0]["note"] = "Nota aggiornata"
    payload["canoni"][0]["sottoattivita"][0]["gg_consuntivati"] = Decimal("13.0000")

    report = make_report()
    import_foundation(payload, batch=ImportBatchFactory(), report=report)

    canone = Canone.objects.get()
    subactivity = CanoneSubactivity.objects.get(title__startswith="#300228")
    entry = TimesheetEntry.objects.get(canone_subactivity=subactivity)
    assert (canone.total_days, canone.weeks_elapsed_at_import) == (Decimal("180.0000"), 16)
    assert canone.import_batch == original_batch
    assert subactivity.notes == "Nota aggiornata"
    assert subactivity.import_batch == original_batch
    assert entry.days == Decimal("12.1800")
    assert report.entity("canoni").updated == 1
    assert report.entity("sottoattivita_canone").updated == 1
    assert any("non applicata, usare un import PPM" in item for item in report.warnings)
    report.as_dict()


def test_canone_scartato_per_progetto_assente_e_duplicati_nel_payload():
    payload = canone_payload()
    duplicate = canone_row(monte_gg=Decimal("190.0000"))
    missing = canone_row(codice_progetto="IM26-ASSENTE", semestre="2026-S1")
    payload["canoni"] = [payload["canoni"][0], duplicate, missing]
    payload["canoni"][0]["sottoattivita"].append(dict(payload["canoni"][0]["sottoattivita"][0]))
    report = make_report()

    import_foundation(payload, batch=ImportBatchFactory(), report=report)

    assert Canone.objects.count() == 1
    assert CanoneSubactivity.objects.count() == 2
    assert len(report.entity("canoni").skipped) == 2
    assert {item["motivo"] for item in report.entity("canoni").skipped} == {
        "Canone duplicato nel payload",
        "Progetto di riferimento non trovato",
    }
    assert len(report.entity("sottoattivita_canone").skipped) == 1


def wallet_activity(**overrides) -> dict:
    row = {
        "codice": "IM26-WALLET",
        "titolo": "Attività sul progetto wallet",
        "tipo": "PROGETTO",
        "referente_bmed": "Andrea Ravagli",
        "referente_imola": "Ravagli Andrea",
        "note": None,
    }
    row.update(overrides)
    return row


def wallet_allocation(**overrides) -> dict:
    row = {
        "id_import": "W26-001",
        "anno_wallet": 2026,
        "progetto_origine": "IM26-WALLET",
        "attivita": "IM26-WALLET",
        "gg_allocati": Decimal("8.50"),
        "gg_consumati_iniziali": Decimal("3.25"),
        "stato": "APERTA",
        "note": None,
        "affidabilita": "DA_VERIFICARE",
        "punti_da_verificare": ["Confermare allocazione"],
    }
    row.update(overrides)
    return row


def wallet_payload() -> dict:
    payload = foundation_payload()
    payload["progetti"] = [project_row(codice="IM26-WALLET", gg_consumati_su_progetto=0)]
    payload["wallet"] = {
        "anno": 2026,
        "attivita": [wallet_activity()],
        "allocazioni": [wallet_allocation()],
    }
    return payload


def test_importa_wallet_allocazione_e_consuntivo_iniziale():
    payload = wallet_payload()
    batch = ImportBatchFactory()
    report = make_report()

    import_foundation(payload, batch=batch, report=report)

    year = WalletYear.objects.get(year=2026)
    activity = WalletActivity.objects.get(code="IM26-WALLET")
    allocation = WalletAllocation.objects.get(external_ref="W26-001")
    entry = TimesheetEntry.objects.get(wallet_allocation=allocation)
    assert year.import_batch == batch
    assert (activity.kind, activity.project.code, activity.import_batch) == (
        ActivityKind.PROGETTO,
        "IM26-WALLET",
        batch,
    )
    assert allocation.wallet_year == year
    assert allocation.source_project.code == "IM26-WALLET"
    assert allocation.allocated_days == Decimal("8.5000")
    assert allocation.reliability == Reliability.DA_VERIFICARE
    assert allocation.verification_points[0]["testo"] == "Confermare allocazione"
    assert entry.days == Decimal("3.2500")
    assert entry.period == date(2026, 10, 1)
    assert entry.source == TimesheetSource.SEED_INIZIALE
    assert entry.import_batch == batch
    assert report.entity("anni_wallet").created == 1
    assert report.entity("attivita_wallet").created == 1
    assert report.entity("allocazioni_wallet").created == 1
    assert report.entity("consuntivi_wallet").created == 1


def test_reimport_wallet_invariato_non_duplica_e_non_cambia_ownership():
    payload = wallet_payload()
    first_batch = ImportBatchFactory()
    import_foundation(payload, batch=first_batch, report=make_report())
    second_batch = ImportBatchFactory()
    report = make_report()

    import_foundation(payload, batch=second_batch, report=report)

    assert WalletYear.objects.count() == 1
    assert WalletActivity.objects.count() == 1
    assert WalletAllocation.objects.count() == 1
    assert TimesheetEntry.objects.filter(wallet_allocation__isnull=False).count() == 1
    assert WalletActivity.objects.get().import_batch == first_batch
    assert WalletAllocation.objects.get().import_batch == first_batch
    assert report.entity("attivita_wallet").unchanged == 1
    assert report.entity("allocazioni_wallet").unchanged == 1
    assert report.entity("consuntivi_wallet").unchanged == 1


def test_aggiorna_campi_wallet_ma_non_consuntivo_append_only():
    payload = wallet_payload()
    first_batch = ImportBatchFactory()
    import_foundation(payload, batch=first_batch, report=make_report())
    payload["wallet"]["attivita"][0]["titolo"] = "Titolo aggiornato"
    payload["wallet"]["allocazioni"][0].update(
        gg_allocati=Decimal("9.00"),
        gg_consumati_iniziali=Decimal("4.00"),
        stato="CHIUSA",
    )
    report = make_report()

    import_foundation(payload, batch=ImportBatchFactory(), report=report)

    activity = WalletActivity.objects.get()
    allocation = WalletAllocation.objects.get()
    assert activity.title == "Titolo aggiornato"
    assert allocation.allocated_days == Decimal("9.0000")
    assert allocation.status == AllocationStatus.CHIUSA
    assert TimesheetEntry.objects.get(wallet_allocation=allocation).days == Decimal("3.2500")
    assert report.entity("attivita_wallet").updated == 1
    assert report.entity("allocazioni_wallet").updated == 1
    assert len(report.warnings) == 1
    assert "differenza non applicata" in report.warnings[0]


def test_wallet_zero_non_genera_movimento_e_importi_negativi_sono_scartati():
    payload = wallet_payload()
    payload["wallet"]["allocazioni"] = [
        wallet_allocation(gg_allocati=Decimal("0"), gg_consumati_iniziali=Decimal("0")),
        wallet_allocation(
            id_import="W26-NEG",
            gg_allocati=Decimal("-1"),
            gg_consumati_iniziali=Decimal("-0.5"),
        ),
    ]
    report = make_report()

    import_foundation(payload, batch=ImportBatchFactory(), report=report)

    assert WalletAllocation.objects.filter(external_ref="W26-001").exists()
    assert not WalletAllocation.objects.filter(external_ref="W26-NEG").exists()
    assert not TimesheetEntry.objects.filter(wallet_allocation__isnull=False).exists()
    assert len(report.entity("allocazioni_wallet").skipped) == 1


def test_wallet_scarti_per_duplicati_e_riferimenti_mancanti():
    payload = wallet_payload()
    payload["wallet"]["attivita"].extend(
        [
            wallet_activity(titolo="Duplicata"),
            wallet_activity(codice="IM-MISSING", titolo="Manca", tipo="PROGETTO"),
            wallet_activity(
                codice="ATT-OWNER-MISSING",
                tipo="ATTIVITA",
                referente_bmed="Persona Assente",
            ),
        ]
    )
    payload["wallet"]["allocazioni"].extend(
        [
            wallet_allocation(gg_allocati=Decimal("99")),
            wallet_allocation(id_import="W26-NO-ACT", attivita="ATT-INVISIBILE"),
            wallet_allocation(id_import="W26-NO-SOURCE", progetto_origine="IM-INVISIBILE"),
        ]
    )
    report = make_report()

    import_foundation(payload, batch=ImportBatchFactory(), report=report)

    assert WalletActivity.objects.count() == 1
    assert WalletAllocation.objects.count() == 1
    assert len(report.entity("attivita_wallet").skipped) == 3
    assert len(report.entity("allocazioni_wallet").skipped) == 3


def test_importa_wallet_storico_e_scarti_zero_duplicato():
    payload = foundation_payload()
    payload["progetti"] = [
        project_row(
            codice="IM26-STORICO",
            gg_consumati_su_progetto=0,
            gg_wallet_storico_gia_usati=Decimal("1.25"),
        ),
        project_row(
            codice="IM25270-3313-BMED-ARCH-ZERO",
            gg_consumati_su_progetto=0,
            gg_wallet_storico_gia_usati=Decimal("0"),
        ),
        project_row(
            codice="IM25151-3313-BMED-ARCH-ICT-ASSET-LIFECYCLE-OBSOLESCENZA",
            gg_consumati_su_progetto=0,
            gg_wallet_storico_gia_usati=Decimal("5"),
        ),
    ]
    report = make_report()
    batch = ImportBatchFactory()

    import_foundation(payload, batch=batch, report=report)

    activity = WalletActivity.objects.get(code="STORICO-IM26-STORICO")
    allocation = WalletAllocation.objects.get(external_ref="STORICO-IM26-STORICO")
    entry = TimesheetEntry.objects.get(wallet_allocation=allocation)
    assert activity.is_technical is True
    assert allocation.wallet_year.year == 2025
    assert allocation.status == AllocationStatus.CHIUSA
    assert allocation.reliability == Reliability.DA_VERIFICARE
    assert allocation.is_technical is True
    assert entry.days == Decimal("1.2500")
    skipped = report.entity("allocazioni_wallet_storiche").skipped
    assert len(skipped) == 2
    assert any("zero" in item["motivo"] for item in skipped)
    assert any("W26-012" in item["motivo"] for item in skipped)


def ppm_and_anomalies_payload() -> dict:
    payload = foundation_payload()
    payload["progetti"] = [project_row(codice="IM26-PPM", gg_consumati_su_progetto=0)]
    payload["snapshot_ppm"] = [
        {
            "tipo": "PPM_WALLET",
            "titolo": "Wallet 2026",
            "data_estrazione": "2026-10-16T11:05:18",
            "file_origine": "wallet.xlsx",
            "righe": [
                {
                    "codice_progetto": "IM26-PPM",
                    "responsabile_imola": None,
                    "stato_ppm": "Attivo",
                    "gg_previsti": Decimal("0"),
                    "gg_residui": None,
                    "gg_totali": Decimal("0"),
                },
                {
                    "codice_progetto": "IM26-MANCANTE",
                    "responsabile_imola": "Mario Rossi",
                    "stato_ppm": "",
                    "gg_previsti": Decimal("1.25"),
                    "gg_residui": Decimal("-0.25"),
                    "gg_totali": Decimal("1.50"),
                },
            ],
            "totali": {"gg_previsti": Decimal("1.25"), "gg_totali": Decimal("1.50")},
        }
    ]
    payload["anomalie_aperte"] = [
        {
            "id_import": "AN-001",
            "severita": "ALTA",
            "ambito": "PROGETTO",
            "descrizione": "Dato da verificare",
            "codice_progetto": "IM26-PPM",
            "stato": "IN_VERIFICA",
        },
        {
            "id_import": "AN-002",
            "severita": "BASSA",
            "ambito": "RICONCILIAZIONE",
            "descrizione": "Riferimento non disponibile",
            "codice_progetto": "IM26-MANCANTE",
            "stato": "APERTA",
        },
    ]
    return payload


def test_importa_snapshot_righe_raw_zero_null_e_anomalie_seed():
    payload = ppm_and_anomalies_payload()
    batch = ImportBatchFactory()
    report = make_report()

    import_foundation(payload, batch=batch, report=report)

    snapshot = PpmSnapshot.objects.get()
    assert snapshot.import_batch == batch
    assert snapshot.row_count == 2
    assert snapshot.totals["gg_previsti"] == "1.25"
    linked = PpmSnapshotRow.objects.get(project_code="IM26-PPM")
    assert linked.project.code == "IM26-PPM"
    assert linked.planned_days == Decimal("0")
    assert linked.residual_days is None
    assert linked.total_days == Decimal("0")
    assert linked.raw["codice_progetto"] == "IM26-PPM"
    assert linked.raw["gg_previsti"] == "0"
    assert linked.raw["gg_totali"] == "0"
    unmatched = PpmSnapshotRow.objects.get(project_code="IM26-MANCANTE")
    assert unmatched.project is None
    assert "non trovato" in unmatched.unmatched_reason
    anomaly = Anomaly.objects.get(fingerprint=build_fingerprint(SEED_RULE_CODE, "AN-001"))
    assert (anomaly.severity, anomaly.status, anomaly.project.code) == (
        "ALTA",
        AnomalyStatus.RISOLTA,
        "IM26-PPM",
    )
    assert (
        anomaly.resolution_note == "superata dalla migrazione (difetto del file Excel di origine)"
    )
    assert anomaly.resolved_at is not None
    assert anomaly.context["raw"]["id_import"] == "AN-001"
    assert anomaly.context["raw"]["severita"] == "ALTA"
    review = Anomaly.objects.get(fingerprint=build_fingerprint(SEED_RULE_CODE, "AN-002"))
    assert review.project is None
    assert "revisione_riferimento" in review.context
    assert report.entity("snapshot_ppm").created == 1
    assert report.entity("righe_snapshot_ppm").created == 2
    assert report.entity("anomalie_seed").created == 2
    assert len(report.entity("riferimenti_anomalie_seed").skipped) == 1


def test_reimport_snapshot_e_anomalie_invariato_preserva_ownership():
    payload = ppm_and_anomalies_payload()
    first_batch = ImportBatchFactory()
    import_foundation(payload, batch=first_batch, report=make_report())
    report = make_report()

    import_foundation(payload, batch=ImportBatchFactory(), report=report)

    assert PpmSnapshot.objects.count() == 1
    assert PpmSnapshotRow.objects.count() == 2
    assert Anomaly.objects.count() == 2
    assert PpmSnapshot.objects.get().import_batch == first_batch
    assert set(PpmSnapshotRow.objects.values_list("import_batch", flat=True)) == {first_batch.id}
    assert set(Anomaly.objects.values_list("import_batch", flat=True)) == {first_batch.id}
    assert report.entity("snapshot_ppm").unchanged == 1
    assert report.entity("righe_snapshot_ppm").unchanged == 2
    assert report.entity("anomalie_seed").unchanged == 2


def test_aggiorna_snapshot_riga_e_anomalia_con_stessa_chiave_naturale():
    payload = ppm_and_anomalies_payload()
    first_batch = ImportBatchFactory()
    import_foundation(payload, batch=first_batch, report=make_report())
    payload["snapshot_ppm"][0]["titolo"] = "Wallet aggiornato"
    payload["snapshot_ppm"][0]["righe"][0]["gg_totali"] = Decimal("2.50")
    payload["anomalie_aperte"][0].update(
        severita="MEDIA", descrizione="Descrizione aggiornata", stato="RISOLTA"
    )
    report = make_report()

    import_foundation(payload, batch=ImportBatchFactory(), report=report)

    assert PpmSnapshot.objects.get().title == "Wallet aggiornato"
    assert PpmSnapshotRow.objects.get(project_code="IM26-PPM").total_days == Decimal("2.50")
    anomaly = Anomaly.objects.get(fingerprint=build_fingerprint(SEED_RULE_CODE, "AN-001"))
    assert (anomaly.severity, anomaly.description, anomaly.status, anomaly.import_batch) == (
        "MEDIA",
        "Descrizione aggiornata",
        "RISOLTA",
        first_batch,
    )
    assert report.entity("snapshot_ppm").updated == 1
    assert report.entity("righe_snapshot_ppm").updated == 1
    assert report.entity("anomalie_seed").updated == 1


def test_scarti_per_duplicati_snapshot_righe_e_anomalie():
    payload = ppm_and_anomalies_payload()
    payload["snapshot_ppm"].append(dict(payload["snapshot_ppm"][0]))
    payload["snapshot_ppm"][0]["righe"].append(dict(payload["snapshot_ppm"][0]["righe"][0]))
    payload["anomalie_aperte"].append(dict(payload["anomalie_aperte"][0]))
    report = make_report()

    import_foundation(payload, batch=ImportBatchFactory(), report=report)

    assert PpmSnapshot.objects.count() == 1
    assert PpmSnapshotRow.objects.count() == 2
    assert Anomaly.objects.count() == 2
    assert len(report.entity("snapshot_ppm").skipped) == 1
    assert len(report.entity("righe_snapshot_ppm").skipped) == 1
    assert len(report.entity("anomalie_seed").skipped) == 1


def test_riferimento_normalizzato_ambiguo_richiede_revisione():
    payload = ppm_and_anomalies_payload()
    payload["progetti"] = []
    first_batch = ImportBatchFactory()
    for code in ("IM26-BMED-PPM", "IM26-PPM-BMED"):
        Project.objects.create(
            code=code,
            title=code,
            contract_type="WALLET",
            offer_status="ACCETTATA",
            timesheet_status="ATTIVO",
            billing_status="DA_FATTURARE",
            budget_days=Decimal("1"),
            reliability="CERTO",
            import_batch=first_batch,
        )
    payload["snapshot_ppm"][0]["righe"] = [
        {
            "codice_progetto": "im26-bmed-ppm",
            "gg_previsti": Decimal("1"),
            "gg_residui": Decimal("0"),
            "gg_totali": Decimal("1"),
        }
    ]
    payload["anomalie_aperte"] = [
        {
            "id_import": "AN-AMB",
            "severita": "MEDIA",
            "ambito": "PROGETTO",
            "descrizione": "Ambigua",
            "codice_progetto": "im26-bmed-ppm",
            "stato": "APERTA",
        }
    ]
    report = make_report()

    import_foundation(payload, batch=ImportBatchFactory(), report=report)

    ppm_row = PpmSnapshotRow.objects.get()
    assert ppm_row.project is None
    assert "ambiguo" in ppm_row.unmatched_reason
    anomaly = Anomaly.objects.get()
    assert anomaly.project is None
    assert "ambiguo" in anomaly.context["revisione_riferimento"]
    assert len(report.entity("riferimenti_anomalie_seed").skipped) == 1


def test_import_coda_seed_resta_atomico(monkeypatch):
    payload = ppm_and_anomalies_payload()

    def fail_create(*args, **kwargs):
        raise RuntimeError("errore anomalie")

    monkeypatch.setattr(Anomaly.objects, "create", fail_create)
    with pytest.raises(RuntimeError, match="errore anomalie"):
        import_foundation(payload, batch=ImportBatchFactory(), report=make_report())

    assert PpmSnapshot.objects.count() == 0
    assert PpmSnapshotRow.objects.count() == 0
    assert Project.objects.count() == 0
