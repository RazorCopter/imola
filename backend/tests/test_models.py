"""Vincoli e invarianti dei modelli: ciò che il database deve impedire comunque."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.current_user import acting_as
from core.models import AppSettings, Reliability, verification_point
from directory.normalization import comparison_key, normalize_person_name
from projects.models import MilestoneStatus, OfferStatus, Project, TimesheetStatus
from tests.factories import (
    CanoneFactory,
    CanoneSubactivityFactory,
    ImportBatchFactory,
    MilestoneFactory,
    PersonFactory,
    ProjectFactory,
    TimesheetEntryFactory,
    UserFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)
from timesheets.models import TimesheetEntry, TimesheetSource

pytestmark = pytest.mark.django_db


class TestTracciatura:
    def test_lutente_corrente_popola_creato_da(self):
        user = UserFactory(username="gbleve")
        with acting_as(user):
            project = ProjectFactory(code="IM26-TRACCIA")
        assert project.created_by == user
        assert project.updated_by == user

    def test_la_versione_cresce_a_ogni_salvataggio(self):
        project = ProjectFactory(code="IM26-VERSIONE")
        assert project.version == 1
        project.title = "Titolo aggiornato"
        project.save()
        assert project.version == 2

    def test_la_history_registra_le_modifiche(self):
        project = ProjectFactory(code="IM26-HISTORY")
        project.notes = "Nota aggiunta"
        project.save()
        assert project.history.count() == 2


class TestVincoliProgetto:
    def test_budget_negativo_rifiutato_dal_database(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectFactory(code="IM26-NEG", budget_days=Decimal("-1.0000"))

    def test_fine_prima_dellinizio_rifiutata_dal_database(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectFactory(
                code="IM26-DATE",
                start_date=date(2026, 6, 1),
                planned_end_date=date(2026, 1, 1),
            )

    def test_chiuso_senza_data_rifiutato_se_non_viene_da_import(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectFactory(
                code="IM26-CHIUSO-SENZA-DATA",
                timesheet_status=TimesheetStatus.CHIUSO,
                actual_closure_date=None,
            )

    def test_chiuso_senza_data_ammesso_dallimport(self):
        """D-03: i 3 progetti chiusi senza data del seed devono poter entrare."""
        batch = ImportBatchFactory()
        project = ProjectFactory(
            code="IM26034-3313-BMED-ARCH-SOLUTION-DESIGN-MIGRAZIONE-VIYA",
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=None,
            import_batch=batch,
            declared_residual_year=2026,
        )
        project.refresh_from_db()
        assert project.residual_reference_year is None
        assert project.declared_residual_year == 2026

    def test_attivo_senza_offerta_accettata_bloccato_dalla_validazione(self):
        project = ProjectFactory.build(
            code="IM26-OFFERTA",
            offer_status=OfferStatus.INVIATA,
            timesheet_status=TimesheetStatus.ATTIVO,
        )
        with pytest.raises(ValidationError) as excinfo:
            project.full_clean()
        assert "timesheet_status" in excinfo.value.message_dict

    def test_lanno_del_residuo_e_derivato_dalla_data_di_chiusura(self):
        project = ProjectFactory(
            code="IM25-CHIUSO",
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=date(2025, 11, 15),
        )
        project.refresh_from_db()
        assert project.residual_reference_year == 2025

    def test_lanno_del_residuo_non_e_scrivibile(self):
        field = Project._meta.get_field("residual_reference_year")
        assert field.generated is True


class TestPuntiDaVerificare:
    def test_chiudere_un_punto_richiede_la_nota(self):
        project = ProjectFactory(
            code="IM26-VERIFICHE",
            reliability=Reliability.DA_VERIFICARE,
            verification_points=[verification_point("Data fine da aggiornare.")],
        )
        with pytest.raises(ValidationError):
            project.mark_verification_point(0, "")

    def test_chiudere_lultimo_punto_riporta_laffidabilita_a_certo(self):
        user = UserFactory(username="verificatore")
        project = ProjectFactory(
            code="IM26-VERIFICHE-2",
            reliability=Reliability.DA_VERIFICARE,
            verification_points=[verification_point("Verificare lo sforamento.")],
        )
        project.mark_verification_point(0, "Confrontato con il PPM del 16/10.", user)
        project.save()

        assert project.open_verification_points == []
        assert project.reliability == Reliability.CERTO
        assert project.verification_points[0]["verificato_da"] == "verificatore"

    def test_con_piu_punti_aperti_laffidabilita_resta_da_verificare(self):
        project = ProjectFactory(
            code="IM26-VERIFICHE-3",
            reliability=Reliability.DA_VERIFICARE,
            verification_points=[verification_point("Uno"), verification_point("Due")],
        )
        project.mark_verification_point(0, "Chiuso il primo.")
        assert project.reliability == Reliability.DA_VERIFICARE
        assert len(project.open_verification_points) == 1

    def test_indice_inesistente_rifiutato(self):
        project = ProjectFactory(code="IM26-VERIFICHE-4")
        with pytest.raises(ValidationError):
            project.mark_verification_point(5, "Nota")


class TestMilestone:
    def test_spostare_richiede_la_motivazione(self):
        milestone = MilestoneFactory()
        with pytest.raises(ValidationError):
            milestone.move_to(date(2026, 9, 1), "")

    def test_lo_spostamento_viene_storicizzato(self):
        milestone = MilestoneFactory(planned_date=date(2026, 8, 1))
        milestone.move_to(date(2026, 9, 1), "Spostata da agosto a settembre.")
        milestone.save()

        assert milestone.planned_date == date(2026, 9, 1)
        assert milestone.move_count == 1
        assert milestone.status == MilestoneStatus.SPOSTATA
        assert milestone.moves[0]["da"] == "2026-08-01"
        assert milestone.moves[0]["motivazione"] == "Spostata da agosto a settembre."


class TestConsuntiviAppendOnly:
    def test_serve_esattamente_un_bersaglio(self):
        project = ProjectFactory(code="IM26-TARGET")
        allocation = WalletAllocationFactory(
            source_project=project,
            activity=WalletActivityFactory(code="ATT-TARGET"),
            wallet_year=WalletYearFactory(year=2026),
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            TimesheetEntry.objects.create(
                project=project,
                wallet_allocation=allocation,
                period=date(2026, 10, 1),
                days=Decimal("1.0000"),
                source=TimesheetSource.MANUALE,
            )

    def test_nessun_bersaglio_rifiutato(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            TimesheetEntry.objects.create(
                period=date(2026, 10, 1),
                days=Decimal("1.0000"),
                source=TimesheetSource.MANUALE,
            )

    def test_giornate_a_zero_rifiutate(self):
        project = ProjectFactory(code="IM26-ZERO")
        with pytest.raises(IntegrityError), transaction.atomic():
            TimesheetEntry.objects.create(
                project=project,
                period=date(2026, 10, 1),
                days=Decimal("0.0000"),
                source=TimesheetSource.MANUALE,
            )

    def test_il_periodo_e_normalizzato_al_primo_del_mese(self):
        entry = TimesheetEntryFactory(
            project=ProjectFactory(code="IM26-PERIODO"), period=date(2026, 10, 16)
        )
        assert entry.period == date(2026, 10, 1)

    def test_una_riga_non_si_modifica(self):
        entry = TimesheetEntryFactory(project=ProjectFactory(code="IM26-IMMUTABILE"))
        entry.days = Decimal("99.0000")
        with pytest.raises(ValidationError):
            entry.save()

    def test_una_riga_non_si_cancella(self):
        entry = TimesheetEntryFactory(project=ProjectFactory(code="IM26-NO-DELETE"))
        with pytest.raises(ValidationError):
            entry.delete()

    def test_lo_storno_ha_segno_opposto_e_punta_alloriginale(self):
        entry = TimesheetEntryFactory(
            project=ProjectFactory(code="IM26-STORNO"), days=Decimal("3.5000")
        )
        reversal = entry.build_reversal("Correzione da estratto PPM.")
        reversal.save()

        assert reversal.days == Decimal("-3.5000")
        assert reversal.source == TimesheetSource.STORNO
        assert reversal.reverses == entry
        assert reversal.period == entry.period


class TestAnagrafiche:
    def test_normalizza_cognome_nome(self):
        candidate = normalize_person_name("Ravagli Andrea")
        assert candidate.normalized == "Ravagli Andrea"
        assert not candidate.needs_review
        # La chiave di confronto collide con la forma invertita.
        assert candidate.key == comparison_key("Andrea Ravagli")

    def test_i_nomi_parziali_vanno_in_revisione(self):
        candidate = normalize_person_name("Gianvito")
        assert candidate.needs_review
        assert "conferma" in candidate.reason

    def test_la_chiave_ignora_accenti_e_maiuscole(self):
        assert comparison_key("Niccolò Bianchi") == comparison_key("niccolo bianchi")

    def test_persona_unica_per_organizzazione(self):
        person = PersonFactory(full_name="Andrea Ravagli")
        with pytest.raises(IntegrityError), transaction.atomic():
            PersonFactory(full_name="Ravagli Andrea", organization=person.organization)

    def test_il_titlecase_rispetta_le_particelle(self):
        assert normalize_person_name("MARIO DE LUCA").normalized == "Mario de Luca"


class TestCanone:
    def test_estrae_il_riferimento_redmine_dal_titolo(self):
        subactivity = CanoneSubactivityFactory(title="#300228 [Studio AIL] Identificazione pattern")
        assert subactivity.redmine_ref == "300228"

    def test_estrae_anche_il_prefisso_numerico_nudo(self):
        subactivity = CanoneSubactivityFactory(title="300229 - Mapping scenari target")
        assert subactivity.redmine_ref == "300229"

    def test_senza_riferimento_resta_vuoto(self):
        subactivity = CanoneSubactivityFactory(title="Presidio architetturale")
        assert subactivity.redmine_ref == ""

    def test_semestre_con_formato_errato_rifiutato(self):
        canone = CanoneFactory.build(semester="2026S2")
        with pytest.raises(ValidationError):
            canone.clean()

    def test_estremi_del_semestre(self):
        assert CanoneFactory.build().semester_bounds("2026-S1") == ("2026-01-01", "2026-06-30")
        assert CanoneFactory.build().semester_bounds("2026-S2") == ("2026-07-01", "2026-12-31")

    def test_un_solo_canone_per_progetto_e_semestre(self):
        canone = CanoneFactory(semester="2026-S2")
        with pytest.raises(IntegrityError), transaction.atomic():
            CanoneFactory(project=canone.project, semester="2026-S2")


class TestWallet:
    def test_attivita_progetto_senza_progetto_rifiutata(self):
        activity = WalletActivityFactory.build(kind="PROGETTO", project=None)
        with pytest.raises(ValidationError):
            activity.clean()

    def test_riferimento_di_import_unico(self):
        WalletAllocationFactory(
            external_ref="W26-001",
            activity=WalletActivityFactory(code="ATT-REF-1"),
            wallet_year=WalletYearFactory(year=2026),
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            WalletAllocationFactory(
                external_ref="W26-001",
                activity=WalletActivityFactory(code="ATT-REF-2"),
                wallet_year=WalletYearFactory(year=2026),
            )

    def test_piu_allocazioni_senza_riferimento_sono_ammesse(self):
        year = WalletYearFactory(year=2026)
        WalletAllocationFactory(activity=WalletActivityFactory(code="ATT-A"), wallet_year=year)
        WalletAllocationFactory(activity=WalletActivityFactory(code="ATT-B"), wallet_year=year)
        from wallet.models import WalletAllocation

        assert WalletAllocation.objects.filter(external_ref="").count() == 2

    def test_giornate_allocate_negative_rifiutate(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            WalletAllocationFactory(
                allocated_days=Decimal("-1.0000"),
                activity=WalletActivityFactory(code="ATT-NEG"),
                wallet_year=WalletYearFactory(year=2026),
            )


class TestImpostazioni:
    def test_la_riga_delle_impostazioni_e_unica(self):
        first = AppSettings.get_solo()
        assert AppSettings.get_solo().pk == first.pk
        assert AppSettings.objects.count() == 1

    def test_valori_di_default_allineati_al_seed(self):
        settings_row = AppSettings.get_solo()
        assert settings_row.hours_per_day == Decimal("8.00")
        assert settings_row.ppm_granularity_days == Decimal("0.0625")
        assert settings_row.reconciliation_tolerance_days == Decimal("0.0100")
        assert settings_row.residual_years_after_closure == 1

    def test_ore_per_giornata_non_positive_rifiutate(self):
        settings_row = AppSettings.get_solo()
        settings_row.hours_per_day = Decimal("0.00")
        with pytest.raises(ValidationError):
            settings_row.clean()
