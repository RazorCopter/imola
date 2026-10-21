"""Test specifici per la decisione D-14: limitazione eccezioni al solo SEED_JSON.

1. Rifiuto cancellazione e mutazione diretta del ledger per batch non-seed (es. PPM).
2. Rifiuto stato CHIUSO senza data per progetti privi di batch seed (DB trigger e validazione).
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from importers.rollback import RollbackError, rollback_seed_batch
from imports.models import ImportBatch, ImportKind, ImportStatus
from projects.models import OfferStatus, TimesheetStatus
from tests.factories import ProjectFactory, TimesheetEntryFactory
from timesheets.models import TimesheetEntry, TimesheetSource
from timesheets.mutations import allow_ledger_mutation


@pytest.mark.django_db
class TestD14LedgerMutationProtection:
    """I batch non-seed (es. PPM) non possono usare la mutazione diretta del ledger."""

    def test_allow_ledger_mutation_rifiuta_batch_ppm(self):
        batch_ppm = ImportBatch.objects.create(
            kind=ImportKind.PPM_XLSX,
            source_filename="export_ppm_2026_10.xlsx",
            status=ImportStatus.APPLIED,
        )

        with transaction.atomic():
            with pytest.raises(PermissionError) as exc_info:
                with allow_ledger_mutation("tentativo di cancellazione PPM", batch=batch_ppm):
                    pass

        assert "solo i batch SEED_JSON ammettono mutazioni dirette del ledger" in str(
            exc_info.value
        )
        assert "D-14" in str(exc_info.value)

    def test_rollback_seed_batch_rifiuta_batch_ppm(self):
        batch_ppm = ImportBatch.objects.create(
            kind=ImportKind.PPM_XLSX,
            source_filename="export_ppm_2026_10.xlsx",
            status=ImportStatus.APPLIED,
        )

        with pytest.raises(RollbackError) as exc_info:
            rollback_seed_batch(str(batch_ppm.id))

        assert "non è un import seed JSON" in str(exc_info.value)

    def test_allow_ledger_mutation_consente_batch_seed_json(self):
        batch_seed = ImportBatch.objects.create(
            kind=ImportKind.SEED_JSON,
            source_filename="seed_test.json",
            status=ImportStatus.APPLIED,
        )
        project = ProjectFactory(
            code="IM26-TEST-CONSUNTIVO-D14",
            offer_status=OfferStatus.ACCETTATA,
            timesheet_status=TimesheetStatus.ATTIVO,
            import_batch=batch_seed,
        )
        entry = TimesheetEntryFactory(
            project=project,
            source=TimesheetSource.SEED_INIZIALE,
            import_batch=batch_seed,
        )

        with transaction.atomic():
            with allow_ledger_mutation("rollback seed autorizzato", batch=batch_seed):
                TimesheetEntry.objects.filter(pk=entry.pk).delete()

        assert not TimesheetEntry.objects.filter(pk=entry.pk).exists()


@pytest.mark.django_db
class TestD14ProjectClosedRequiresDate:
    """Lo stato CHIUSO senza data è consentito SOLO per batch SEED_JSON (D-03 / D-14)."""

    def test_progetto_chiuso_senza_data_rifiutato_a_livello_db_se_batch_ppm(self):
        batch_ppm = ImportBatch.objects.create(
            kind=ImportKind.PPM_XLSX,
            source_filename="export_ppm_2026_10.xlsx",
            status=ImportStatus.APPLIED,
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectFactory(
                code="IM26-PPM-CHIUSO-SENZA-DATA",
                timesheet_status=TimesheetStatus.CHIUSO,
                actual_closure_date=None,
                import_batch=batch_ppm,
            )

    def test_progetto_chiuso_senza_data_rifiutato_dalla_validazione_se_batch_ppm(self):
        batch_ppm = ImportBatch.objects.create(
            kind=ImportKind.PPM_XLSX,
            source_filename="export_ppm_2026_10.xlsx",
            status=ImportStatus.APPLIED,
        )
        project = ProjectFactory.build(
            code="IM26-PPM-CHIUSO-VALIDATION",
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=None,
            import_batch=batch_ppm,
        )

        with pytest.raises(ValidationError) as exc_info:
            project.full_clean()

        assert "actual_closure_date" in exc_info.value.message_dict
        msg = str(exc_info.value.message_dict["actual_closure_date"])
        assert "D-14" in msg or "D-03" in msg

    def test_progetto_chiuso_senza_data_rifiutato_se_senza_batch(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectFactory(
                code="IM26-NO-BATCH-CHIUSO",
                timesheet_status=TimesheetStatus.CHIUSO,
                actual_closure_date=None,
                import_batch=None,
            )

        project = ProjectFactory.build(
            code="IM26-NO-BATCH-VALIDATION",
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=None,
            import_batch=None,
        )
        with pytest.raises(ValidationError) as exc_info:
            project.full_clean()
        assert "actual_closure_date" in exc_info.value.message_dict

    def test_progetto_chiuso_senza_data_ammesso_solo_per_batch_seed_json(self):
        batch_seed = ImportBatch.objects.create(
            kind=ImportKind.SEED_JSON,
            source_filename="seed_imola.json",
            status=ImportStatus.APPLIED,
        )
        project = ProjectFactory(
            code="IM26-SEED-CHIUSO-SENZA-DATA",
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date=None,
            import_batch=batch_seed,
            declared_residual_year=2026,
        )
        # Sia a livello di DB che di full_clean deve essere valido
        project.full_clean()
        project.refresh_from_db()
        assert project.timesheet_status == TimesheetStatus.CHIUSO
        assert project.actual_closure_date is None
        assert project.residual_reference_year is None
