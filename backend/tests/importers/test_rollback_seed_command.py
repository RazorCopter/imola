"""Test del rollback sicuro dei batch seed JSON."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command
from django.db import DatabaseError
from django.utils import timezone

from directory.models import Organization
from importers.rollback import ROLLBACK_ORDER, RollbackError, rollback_seed_batch
from imports.models import ImportBatch, ImportIssue, ImportKind, ImportStatus
from projects.models import BillingMilestone, Project
from tests.factories import (
    AnomalyFactory,
    CanoneFactory,
    CanoneSubactivityFactory,
    OrganizationFactory,
    PersonFactory,
    PpmSnapshotFactory,
    PpmSnapshotRowFactory,
    ProjectFactory,
    TimesheetEntryFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)
from timesheets.models import TimesheetEntry

pytestmark = pytest.mark.django_db(transaction=True)


def applied_batch(**kwargs) -> ImportBatch:
    return ImportBatch.objects.create(
        kind=kwargs.pop("kind", ImportKind.SEED_JSON),
        status=kwargs.pop("status", ImportStatus.APPLIED),
        applied_at=kwargs.pop("applied_at", timezone.now()),
        source_filename=kwargs.pop("source_filename", "seed.json"),
        report=kwargs.pop("report", {"esito": "ok"}),
        **kwargs,
    )


def create_complete_graph(batch: ImportBatch) -> None:
    organization = OrganizationFactory(code="ROLLBACK-ORG", import_batch=batch)
    person = PersonFactory(organization=organization, import_batch=batch)
    project = ProjectFactory(
        code="ROLLBACK-PROJECT",
        client_owner=person,
        supplier_owner=None,
        import_batch=batch,
    )
    milestone = BillingMilestone.objects.create(
        project=project,
        amount_days=1,
        planned_date="2026-12-01",
        status="PIANIFICATA",
        import_batch=batch,
    )
    canone = CanoneFactory(project=project, semester="2026-S2", import_batch=batch)
    subactivity = CanoneSubactivityFactory(canone=canone, import_batch=batch)
    wallet_year = WalletYearFactory(year=2099, import_batch=batch)
    activity = WalletActivityFactory(code="ROLLBACK-ACTIVITY", project=project, import_batch=batch)
    allocation = WalletAllocationFactory(
        external_ref="ROLLBACK-ALLOCATION",
        wallet_year=wallet_year,
        source_project=project,
        activity=activity,
        import_batch=batch,
    )
    snapshot = PpmSnapshotFactory(import_batch=batch)
    row = PpmSnapshotRowFactory(snapshot=snapshot, project=project, import_batch=batch)
    entry = TimesheetEntryFactory(project=project, import_batch=batch)
    anomaly = AnomalyFactory(project=project, import_batch=batch)
    assert all((milestone, subactivity, allocation, row, entry, anomaly))


def test_rollback_completo_elimina_tutte_le_famiglie_e_registra_audit():
    batch = applied_batch()
    create_complete_graph(batch)

    result = rollback_seed_batch(str(batch.id))

    expected_models = [model for _label, model in ROLLBACK_ORDER]
    assert result.deleted_total == len(expected_models)
    assert all(model.objects.count() == 0 for model in expected_models)
    batch.refresh_from_db()
    assert batch.status == ImportStatus.ROLLED_BACK
    assert batch.rolled_back_at is not None
    assert batch.report["rollback"]["deleted_total"] == len(expected_models)
    issue = ImportIssue.objects.get(batch=batch)
    assert "Rollback completato" in issue.message


def test_preserva_record_preesistente_aggiornato_e_senza_import_batch():
    batch = applied_batch()
    existing = OrganizationFactory(code="PREEXISTING", name="Nome aggiornato", import_batch=None)
    created = OrganizationFactory(code="CREATED", import_batch=batch)

    rollback_seed_batch(str(batch.id))

    existing.refresh_from_db()
    assert existing.name == "Nome aggiornato"
    assert existing.import_batch is None
    assert not Organization.objects.filter(pk=created.pk).exists()


def test_ordine_elimina_consuntivo_append_only_prima_del_progetto():
    batch = applied_batch()
    project = ProjectFactory(code="LEDGER-ORDER", import_batch=batch)
    entry = TimesheetEntryFactory(project=project, import_batch=batch)

    rollback_seed_batch(str(batch.id))

    assert not TimesheetEntry.objects.filter(pk=entry.pk).exists()
    assert not Project.objects.filter(pk=project.pk).exists()


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (ImportStatus.DRY_RUN, "non è annullabile"),
        (ImportStatus.FAILED, "non è annullabile"),
        (ImportStatus.ROLLED_BACK, "già stato annullato"),
    ],
)
def test_rifiuta_batch_non_idoneo_o_gia_annullato(status, message):
    batch = applied_batch(
        status=status, applied_at=None if status != ImportStatus.APPLIED else timezone.now()
    )

    with pytest.raises(RollbackError, match=message):
        rollback_seed_batch(str(batch.id))


def test_rifiuta_batch_inesistente_e_tipo_non_seed():
    with pytest.raises(RollbackError, match="Batch inesistente"):
        rollback_seed_batch("00000000-0000-0000-0000-000000000000")
    batch = applied_batch(kind=ImportKind.PPM_XLSX)
    with pytest.raises(RollbackError, match="non è un import seed JSON"):
        rollback_seed_batch(str(batch.id))


def test_blocca_se_esiste_batch_seed_applicato_successivo():
    first = applied_batch(applied_at=timezone.now() - timezone.timedelta(minutes=1))
    OrganizationFactory(code="FIRST", import_batch=first)
    later = applied_batch()

    with pytest.raises(RollbackError, match=str(later.id)):
        rollback_seed_batch(str(first.id))

    assert Organization.objects.filter(code="FIRST").exists()
    first.refresh_from_db()
    assert first.status == ImportStatus.APPLIED


def test_blocca_dipendenza_esterna_da_batch_successivo_anche_se_non_applicato():
    batch = applied_batch()
    project = ProjectFactory(code="TARGET", import_batch=batch)
    external_batch = applied_batch(status=ImportStatus.ROLLED_BACK, applied_at=None)
    WalletActivityFactory(code="EXTERNAL", project=project, import_batch=external_batch)

    with pytest.raises(RollbackError, match="dipendenze esterne"):
        rollback_seed_batch(str(batch.id))


def test_atomicita_ripristina_cancellazioni_stato_e_audit_su_errore():
    batch = applied_batch()
    organization = OrganizationFactory(code="ATOMIC", import_batch=batch)
    organization_qs_class = type(Organization.objects.all())
    real_delete = organization_qs_class.delete

    def conditional_delete(queryset, *args, **kwargs):
        if queryset.model is Organization:
            real_delete(queryset, *args, **kwargs)
            raise DatabaseError("errore simulato")
        return real_delete(queryset, *args, **kwargs)

    with patch.object(organization_qs_class, "delete", conditional_delete):
        with pytest.raises(DatabaseError, match="errore simulato"):
            rollback_seed_batch(str(batch.id))

    assert Organization.objects.filter(pk=organization.pk).exists()
    batch.refresh_from_db()
    assert batch.status == ImportStatus.APPLIED
    assert batch.rolled_back_at is None
    assert not ImportIssue.objects.filter(batch=batch).exists()


def test_command_richiede_conferma_e_produce_output_testuale():
    batch = applied_batch()
    OrganizationFactory(code="CLI-TEXT", import_batch=batch)

    with pytest.raises(CommandError, match="--confirm"):
        call_command("rollback_seed", str(batch.id))

    stdout = StringIO()
    call_command("rollback_seed", str(batch.id), "--confirm", stdout=stdout)
    assert "annullato" in stdout.getvalue()
    assert "Record eliminati: 1" in stdout.getvalue()


def test_command_json_e_codice_errore_principale():
    batch = applied_batch()
    WalletYearFactory(year=2098, import_batch=batch)
    stdout = StringIO()

    call_command("rollback_seed", str(batch.id), "--confirm", "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert payload["batch_id"] == str(batch.id)
    assert payload["status"] == ImportStatus.ROLLED_BACK
    assert payload["deleted_total"] == 1
    with pytest.raises(CommandError, match="già stato annullato"):
        call_command("rollback_seed", str(batch.id), "--confirm")
