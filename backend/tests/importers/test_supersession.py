"""Test mirati sulla decisione D-05: mappa di supersessione, reimport e rollback."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from anomalies.models import (
    SEED_RULE_CODE,
    Anomaly,
    AnomalyStatus,
    Scope,
    Severity,
    build_fingerprint,
)
from importers.report import ImportReport
from importers.rollback import RollbackError, rollback_seed_batch
from importers.seed_json import SEED_SUPERSESSION_MAP, import_foundation
from imports.models import ImportBatch, ImportKind, ImportStatus
from tests.factories import AnomalyFactory, ImportBatchFactory
from tests.importers.test_seed_json import foundation_payload


def make_report() -> ImportReport:
    return ImportReport(kind=ImportKind.SEED_JSON, source_filename="seed_test.json", dry_run=False)


def seed_anomaly_payload(external_ref: str = "AN-003", **overrides) -> dict:
    payload = foundation_payload()
    row = {
        "id_import": external_ref,
        "severita": "MEDIA",
        "ambito": Scope.PROGETTO,
        "descrizione": "Anomalia seed di prova",
        "stato": "APERTA",
    }
    row.update(overrides)
    payload["anomalie_aperte"] = [row]
    return payload


@pytest.mark.django_db
class TestD05SupersessionMap:
    def test_seed_supersession_map_completeness_and_structure(self):
        """Verifica che la mappa copra le 11 anomalie con i codici regola stabiliti."""
        expected_keys = {f"AN-{index:03d}" for index in range(1, 12)}
        assert set(SEED_SUPERSESSION_MAP.keys()) == expected_keys

        # Anomalie 1-a-1 e 1-a-molti coperte da controlli automatici di Fase 4
        assert SEED_SUPERSESSION_MAP["AN-003"] == (
            "CHK_RESIDUAL_UNALLOCATED_CLOSED",
            (
                "IM25188",
                "IM25151",
                "IM25255",
                "IM25270",
                "IM25206",
                "IM25075",
                "IM25026",
                "IM24517",
                "IM25236",
            ),
        )
        assert SEED_SUPERSESSION_MAP["AN-004"] == ("CHK_OVERRUN_PROJECT", "IM26292")
        assert SEED_SUPERSESSION_MAP["AN-005"] == (
            "CHK_DOUBLE_COUNT",
            ("RM-300228", "RM-300229"),
        )
        assert SEED_SUPERSESSION_MAP["AN-006"] == ("CHK_MISSING_IN_PPM", "IM25379")
        assert SEED_SUPERSESSION_MAP["AN-007"] == (
            "CHK_RECON_DELTA",
            (
                "IM24133",
                "IM25244",
                "IM25306",
                "IM26022",
                "IM25198",
                "IM25197",
                "IM25216",
            ),
        )
        assert SEED_SUPERSESSION_MAP["AN-008"] == ("CHK_CANONE_UNDERUSE", "IM26179")

        # Le 5 anomalie non mappate (difetti dell'Excel superati/risolti all'import)
        assert SEED_SUPERSESSION_MAP["AN-001"] is None
        assert SEED_SUPERSESSION_MAP["AN-002"] is None
        assert SEED_SUPERSESSION_MAP["AN-009"] is None
        assert SEED_SUPERSESSION_MAP["AN-010"] is None
        assert SEED_SUPERSESSION_MAP["AN-011"] is None

    def test_anomalie_difetti_excel_risolte_all_import(self):
        """AN-001, AN-002, AN-009, AN-010, AN-011 devono nascere RISOLTE con nota specifica."""
        excel_defect_ids = ["AN-001", "AN-002", "AN-009", "AN-010", "AN-011"]
        for external_ref in excel_defect_ids:
            payload = seed_anomaly_payload(external_ref, stato="APERTA")
            batch = ImportBatchFactory()
            report = make_report()
            import_foundation(payload, batch=batch, report=report)

            anomaly = Anomaly.objects.get(
                fingerprint=build_fingerprint(SEED_RULE_CODE, external_ref)
            )
            assert anomaly.status == AnomalyStatus.RISOLTA
            assert (
                anomaly.resolution_note
                == "superata dalla migrazione (difetto del file Excel di origine)"
            )
            assert anomaly.resolved_at is not None


@pytest.mark.django_db
class TestAnomalySupersessionModel:
    def test_mark_superseded_imposta_campi_e_storicizza(self):
        seed_anomaly = AnomalyFactory(
            rule_code=SEED_RULE_CODE,
            status=AnomalyStatus.APERTA,
            fingerprint=build_fingerprint(SEED_RULE_CODE, "AN-003"),
        )
        replacement = AnomalyFactory(
            rule_code="CHK_RESIDUAL_UNALLOCATED_CLOSED",
            status=AnomalyStatus.APERTA,
        )

        seed_anomaly.mark_superseded(replacement)
        seed_anomaly.save()

        seed_anomaly.refresh_from_db()
        assert seed_anomaly.status == AnomalyStatus.RISOLTA
        assert seed_anomaly.superseded_by == replacement
        assert seed_anomaly.resolved_at is not None
        expected_note = (
            f"Sostituita dal controllo automatico {replacement.rule_code} "
            f"(anomalia {replacement.id})."
        )
        assert seed_anomaly.resolution_note == expected_note
        assert list(replacement.supersedes.all()) == [seed_anomaly]

    def test_mark_superseded_rifiuta_riferimenti_invalidi(self):
        anomaly = AnomalyFactory()

        with pytest.raises(ValidationError) as exc_none:
            anomaly.mark_superseded(None)  # type: ignore[arg-type]
        assert "L'anomalia sostitutiva non è valida" in str(exc_none.value)

        with pytest.raises(ValidationError) as exc_self:
            anomaly.mark_superseded(anomaly)
        assert "non può sostituire se stessa" in str(exc_self.value)

        unsaved_replacement = Anomaly(
            rule_code="CHK_TEST",
            severity=Severity.BASSA,
            scope=Scope.PROGETTO,
            fingerprint="unsaved-fp",
        )
        with pytest.raises(ValidationError) as exc_unsaved:
            anomaly.mark_superseded(unsaved_replacement)
        assert "deve essere prima salvata" in str(exc_unsaved.value)

    def test_catena_di_supersessione_multi_livello(self):
        """Verifica la navigazione diretta e inversa lungo una catena A -> B -> C."""
        anomaly_a = AnomalyFactory(rule_code=SEED_RULE_CODE)
        anomaly_b = AnomalyFactory(rule_code="CHK_STEP_ONE")
        anomaly_c = AnomalyFactory(rule_code="CHK_STEP_TWO")

        anomaly_a.mark_superseded(anomaly_b)
        anomaly_a.save()
        anomaly_b.mark_superseded(anomaly_c)
        anomaly_b.save()

        anomaly_a.refresh_from_db()
        anomaly_b.refresh_from_db()
        anomaly_c.refresh_from_db()

        assert anomaly_a.superseded_by == anomaly_b
        assert anomaly_b.superseded_by == anomaly_c
        assert anomaly_c.superseded_by is None

        assert list(anomaly_c.supersedes.all()) == [anomaly_b]
        assert list(anomaly_b.supersedes.all()) == [anomaly_a]
        assert list(anomaly_a.supersedes.all()) == []

    def test_cancellazione_sostituta_esegue_set_null_senza_cancellare_originale(self):
        seed_anomaly = AnomalyFactory(rule_code=SEED_RULE_CODE)
        replacement = AnomalyFactory(rule_code="CHK_OVERRUN_PROJECT")

        seed_anomaly.mark_superseded(replacement)
        seed_anomaly.save()

        replacement.delete()

        seed_anomaly.refresh_from_db()
        assert seed_anomaly.superseded_by is None
        assert seed_anomaly.status == AnomalyStatus.RISOLTA
        assert (
            "Sostituita dal controllo automatico CHK_OVERRUN_PROJECT"
            in seed_anomaly.resolution_note
        )

    def test_supersessione_uno_a_molti_an003_richiede_tutte_le_entita(self):
        """AN-003 deve chiudersi solo se tutte le 9 entità sono coperte dalle anomalie."""
        rule_code, expected_entities = SEED_SUPERSESSION_MAP["AN-003"]
        seed_anomaly = AnomalyFactory(
            rule_code=SEED_RULE_CODE,
            status=AnomalyStatus.APERTA,
            fingerprint=build_fingerprint(SEED_RULE_CODE, "AN-003"),
        )

        # Copertura parziale (solo 2 progetti su 9)
        parziali = [
            AnomalyFactory(
                rule_code=rule_code,
                context={"codice_progetto": expected_entities[0]},
            ),
            AnomalyFactory(
                rule_code=rule_code,
                context={"codice_progetto": expected_entities[1]},
            ),
        ]
        with pytest.raises(ValidationError) as exc:
            seed_anomaly.mark_superseded(parziali, expected_entities=expected_entities)
        assert "Copertura incompleta" in str(exc.value)
        assert seed_anomaly.status == AnomalyStatus.APERTA
        assert seed_anomaly.superseded_by is None

        # Copertura completa (tutte le 9 entità coperte)
        tutte = [
            AnomalyFactory(
                rule_code=rule_code,
                context={"codice_progetto": code},
            )
            for code in expected_entities
        ]
        seed_anomaly.mark_superseded(tutte, expected_entities=expected_entities)
        seed_anomaly.save()

        seed_anomaly.refresh_from_db()
        assert seed_anomaly.status == AnomalyStatus.RISOLTA
        assert seed_anomaly.superseded_by == tutte[0]
        assert seed_anomaly.resolved_at is not None
        assert "coprendo tutte le entità" in seed_anomaly.resolution_note
        assert len(seed_anomaly.context["superseded_by_ids"]) == 9

    def test_supersessione_uno_a_molti_an007_richiede_tutte_le_entita(self):
        """AN-007 deve chiudersi solo se tutte le 7 entità sono coperte."""
        rule_code, expected_entities = SEED_SUPERSESSION_MAP["AN-007"]
        seed_anomaly = AnomalyFactory(
            rule_code=SEED_RULE_CODE,
            status=AnomalyStatus.APERTA,
            fingerprint=build_fingerprint(SEED_RULE_CODE, "AN-007"),
        )

        # Copertura completa tramite entità coperte nei context
        tutte = [
            AnomalyFactory(
                rule_code=rule_code,
                context={"entity": code},
            )
            for code in expected_entities
        ]
        seed_anomaly.mark_superseded(tutte, expected_entities=expected_entities)
        seed_anomaly.save()

        seed_anomaly.refresh_from_db()
        assert seed_anomaly.status == AnomalyStatus.RISOLTA
        assert seed_anomaly.superseded_by == tutte[0]
        assert len(seed_anomaly.context["superseded_by_ids"]) == 7


@pytest.mark.django_db
class TestSupersessionReimport:
    def test_reimport_preserva_stato_risolta_e_collegamento_superseded(self):
        """Un'anomalia già sostituita non deve tornare APERTA con il reimport del seed."""
        payload = seed_anomaly_payload("AN-003", stato="APERTA")
        first_batch = ImportBatchFactory()
        import_foundation(payload, batch=first_batch, report=make_report())

        seed_anomaly = Anomaly.objects.get(fingerprint=build_fingerprint(SEED_RULE_CODE, "AN-003"))
        assert seed_anomaly.status == AnomalyStatus.APERTA

        replacement = AnomalyFactory(rule_code="CHK_RESIDUAL_UNALLOCATED_CLOSED")
        seed_anomaly.mark_superseded(replacement)
        seed_anomaly.save()

        # Secondo import identico del seed (nel seed è ancora APERTA)
        report_reimport = make_report()
        second_batch = ImportBatchFactory()
        import_foundation(payload, batch=second_batch, report=report_reimport)

        seed_anomaly.refresh_from_db()
        assert seed_anomaly.status == AnomalyStatus.RISOLTA
        assert seed_anomaly.superseded_by == replacement
        assert seed_anomaly.import_batch == first_batch
        assert report_reimport.entity("anomalie_seed").unchanged == 1

    def test_reimport_aggiorna_altri_campi_preservando_la_supersessione(self):
        """Se il seed cambia la descrizione, viene aggiornata ma lo stato RISOLTA resta."""
        payload = seed_anomaly_payload("AN-004", stato="APERTA", descrizione="Descrizione iniziale")
        first_batch = ImportBatchFactory()
        import_foundation(payload, batch=first_batch, report=make_report())

        seed_anomaly = Anomaly.objects.get(fingerprint=build_fingerprint(SEED_RULE_CODE, "AN-004"))
        replacement = AnomalyFactory(rule_code="CHK_OVERRUN_PROJECT")
        seed_anomaly.mark_superseded(replacement)
        seed_anomaly.save()

        # Aggiornamento descrizione nel file seed
        payload["anomalie_aperte"][0]["descrizione"] = "Descrizione corretta da Imola"
        report_update = make_report()
        second_batch = ImportBatchFactory()
        import_foundation(payload, batch=second_batch, report=report_update)

        seed_anomaly.refresh_from_db()
        assert seed_anomaly.description == "Descrizione corretta da Imola"
        assert seed_anomaly.status == AnomalyStatus.RISOLTA
        assert seed_anomaly.superseded_by == replacement
        assert report_update.entity("anomalie_seed").updated == 1


def applied_batch(**kwargs) -> ImportBatch:
    return ImportBatch.objects.create(
        kind=kwargs.pop("kind", ImportKind.SEED_JSON),
        status=kwargs.pop("status", ImportStatus.APPLIED),
        applied_at=kwargs.pop("applied_at", timezone.now()),
        source_filename=kwargs.pop("source_filename", "seed.json"),
        report=kwargs.pop("report", {"esito": "ok"}),
        **kwargs,
    )


@pytest.mark.django_db
class TestSupersessionRollback:
    def test_rollback_stesso_batch_elimina_pulitamente_catena_di_anomalie(self):
        """Anomalie collegate appartenenti allo stesso batch vengono eliminate entrambe."""
        batch = applied_batch()
        anomaly_a = Anomaly.objects.create(
            rule_code=SEED_RULE_CODE,
            severity=Severity.MEDIA,
            scope=Scope.PROGETTO,
            fingerprint="chain-fp-a",
            import_batch=batch,
        )
        anomaly_b = Anomaly.objects.create(
            rule_code="CHK_CHAIN",
            severity=Severity.MEDIA,
            scope=Scope.PROGETTO,
            fingerprint="chain-fp-b",
            import_batch=batch,
        )
        anomaly_a.mark_superseded(anomaly_b)
        anomaly_a.save()

        result = rollback_seed_batch(str(batch.id))

        assert result.batch_id == str(batch.id)
        assert result.deleted.get("anomalie") == 2
        batch.refresh_from_db()
        assert batch.status == ImportStatus.ROLLED_BACK
        assert not Anomaly.objects.filter(id__in=[anomaly_a.id, anomaly_b.id]).exists()

    def test_rollback_batch_recente_bloccato_se_anomalia_esterna_dipende_dalla_sostituta(self):
        """Blocca il rollback se un'anomalia esterna dipende dalla sostituta creata dal batch."""
        now = timezone.now()
        batch1 = applied_batch(
            applied_at=now - timedelta(minutes=9),
        )
        seed_anomaly = Anomaly.objects.create(
            rule_code=SEED_RULE_CODE,
            severity=Severity.MEDIA,
            scope=Scope.PROGETTO,
            fingerprint="seed-fp-1",
            import_batch=batch1,
        )

        batch2 = applied_batch(
            applied_at=now - timedelta(minutes=4),
        )
        replacement = Anomaly.objects.create(
            rule_code="CHK_AUTO",
            severity=Severity.MEDIA,
            scope=Scope.PROGETTO,
            fingerprint="auto-fp-2",
            import_batch=batch2,
        )

        # L'anomalia di batch1 dipende da quella di batch2
        seed_anomaly.mark_superseded(replacement)
        seed_anomaly.save()

        # Tentativo di rollback del batch più recente (batch2)
        with pytest.raises(RollbackError) as exc:
            rollback_seed_batch(str(batch2.id))

        assert "dipende da anomalie del batch" in str(exc.value)
        assert Anomaly.objects.filter(id=replacement.id).exists()

    def test_rollback_batch_precedente_bloccato_da_presenza_batch_successivo_applicato(self):
        """La guardia sui batch applicati successivi impedisce di annullare il batch precedente."""
        now = timezone.now()
        batch1 = applied_batch(
            applied_at=now - timedelta(minutes=9),
        )
        batch2 = applied_batch(
            applied_at=now - timedelta(minutes=4),
        )

        with pytest.raises(RollbackError) as exc:
            rollback_seed_batch(str(batch1.id))

        assert "esiste un batch seed applicato successivamente" in str(exc.value)
        assert str(batch2.id) in str(exc.value)

    def test_rollback_batch_con_anomalia_seed_non_danneggia_la_sostituta_indipendente(self):
        """Se un'anomalia seed viene rollbacckata, l'anomalia sostitutiva esterna resta intatta."""
        batch1 = applied_batch()
        seed_anomaly = Anomaly.objects.create(
            rule_code=SEED_RULE_CODE,
            severity=Severity.MEDIA,
            scope=Scope.PROGETTO,
            fingerprint="seed-fp-isolated",
            import_batch=batch1,
        )

        # Sostituta esterna senza batch o appartenente a un altro contesto indipendente
        replacement = Anomaly.objects.create(
            rule_code="CHK_STANDALONE",
            severity=Severity.MEDIA,
            scope=Scope.PROGETTO,
            fingerprint="auto-fp-standalone",
        )
        seed_anomaly.mark_superseded(replacement)
        seed_anomaly.save()

        result = rollback_seed_batch(str(batch1.id))

        assert result.batch_id == str(batch1.id)
        assert result.deleted.get("anomalie") == 1
        assert not Anomaly.objects.filter(id=seed_anomaly.id).exists()
        replacement.refresh_from_db()
        assert replacement.supersedes.count() == 0
