"""Rollback sicuro e atomico dei batch seed JSON applicati."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from anomalies.models import Anomaly
from canone.models import Canone, CanoneSubactivity
from directory.models import Organization, Person
from imports.models import (
    ImportBatch,
    ImportIssue,
    ImportIssueLevel,
    ImportKind,
    ImportStatus,
)
from ppm.models import PpmSnapshot, PpmSnapshotRow
from projects.models import BillingMilestone, Project
from timesheets.models import TimesheetEntry
from timesheets.mutations import allow_ledger_mutation
from wallet.models import WalletActivity, WalletAllocation, WalletYear


class RollbackError(RuntimeError):
    """Il batch non può essere annullato in sicurezza."""


@dataclass(frozen=True)
class RollbackResult:
    """Esito strutturato del rollback, adatto a CLI e API future."""

    batch_id: str
    deleted: dict[str, int]

    @property
    def deleted_total(self) -> int:
        return sum(self.deleted.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": ImportStatus.ROLLED_BACK,
            "deleted": self.deleted,
            "deleted_total": self.deleted_total,
        }


# Figli prima dei rispettivi genitori. QuerySet.delete() resta intenzionalmente esplicito:
# nessun record non appartenente al batch deve essere trascinato da una cascata accidentale.
ROLLBACK_ORDER: tuple[tuple[str, type[models.Model]], ...] = (
    ("anomalie", Anomaly),
    ("consuntivi", TimesheetEntry),
    ("righe_snapshot_ppm", PpmSnapshotRow),
    ("milestone", BillingMilestone),
    ("allocazioni_wallet", WalletAllocation),
    ("sotto_attivita_canone", CanoneSubactivity),
    ("attivita_wallet", WalletActivity),
    ("canoni", Canone),
    ("snapshot_ppm", PpmSnapshot),
    ("progetti", Project),
    ("persone", Person),
    ("organizzazioni", Organization),
    ("wallet_anni", WalletYear),
)


def _reject_later_batches(batch: ImportBatch) -> None:
    """Blocca il rollback se import successivi possono avere aggiornato i suoi record.

    Gli update preservano per contratto ``import_batch``: non è quindi possibile ricostruire
    con certezza quali righe siano state modificate da un batch successivo. La regola sicura è
    consentire il rollback soltanto dell'ultimo batch seed applicato.
    """

    later = (
        ImportBatch.objects.filter(
            Q(applied_at__gt=batch.applied_at)
            | Q(applied_at=batch.applied_at, created_at__gt=batch.created_at),
            kind=ImportKind.SEED_JSON,
            status=ImportStatus.APPLIED,
        )
        .order_by("applied_at")
        .first()
    )
    if later is not None:
        raise RollbackError(
            "Rollback bloccato: esiste un batch seed applicato successivamente "
            f"({later.id}). Annullare prima i batch successivi."
        )


def _external_dependencies(batch: ImportBatch) -> list[str]:
    """Trova record importabili esterni che referenziano righe create dal batch."""

    blockers: list[str] = []
    for label, target_model in ROLLBACK_ORDER:
        target_ids = target_model.objects.filter(import_batch=batch).values("pk")
        if not target_ids.exists():
            continue
        for relation in target_model._meta.related_objects:
            related_model = relation.related_model
            if not hasattr(related_model, "import_batch"):
                continue
            field = relation.field
            external = related_model.objects.filter(**{f"{field.name}__in": target_ids}).exclude(
                import_batch=batch
            )
            count = external.count()
            if count:
                blockers.append(
                    f"{related_model._meta.label} ({count}) dipende da {label} del batch"
                )
    return sorted(set(blockers))


@transaction.atomic
def rollback_seed_batch(batch_id: str) -> RollbackResult:
    """Elimina solo le righe create dal batch e registra l'annullamento.

    Il lock sul batch serializza tentativi concorrenti. Ogni guardia e ogni cancellazione vive
    nella stessa transazione; qualsiasi errore ripristina dati, stato e audit.
    """

    try:
        batch = ImportBatch.objects.select_for_update().get(pk=batch_id)
    except (ImportBatch.DoesNotExist, ValueError) as exc:
        raise RollbackError(f"Batch inesistente: {batch_id}.") from exc

    if batch.kind != ImportKind.SEED_JSON:
        raise RollbackError(f"Il batch {batch.id} non è un import seed JSON.")
    if batch.status == ImportStatus.ROLLED_BACK:
        raise RollbackError(f"Il batch {batch.id} è già stato annullato.")
    if batch.status != ImportStatus.APPLIED or batch.applied_at is None:
        raise RollbackError(
            f"Il batch {batch.id} non è annullabile: stato corrente {batch.status}."
        )

    _reject_later_batches(batch)
    blockers = _external_dependencies(batch)
    if blockers:
        raise RollbackError("Rollback bloccato da dipendenze esterne: " + "; ".join(blockers))

    deleted = {
        label: model.objects.filter(import_batch=batch).count() for label, model in ROLLBACK_ORDER
    }
    reason = f"Rollback batch seed {batch.id}"
    with allow_ledger_mutation(reason, batch=batch):
        for _label, model in ROLLBACK_ORDER:
            model.objects.filter(import_batch=batch).delete()

    rolled_back_at = timezone.now()
    report = dict(batch.report or {})
    report["rollback"] = {
        "at": rolled_back_at.isoformat(),
        "deleted": deleted,
        "deleted_total": sum(deleted.values()),
    }
    batch.status = ImportStatus.ROLLED_BACK
    batch.rolled_back_at = rolled_back_at
    batch.report = report
    batch.error = ""
    batch.save(update_fields=("status", "rolled_back_at", "report", "error", "updated_at"))
    ImportIssue.objects.create(
        batch=batch,
        level=ImportIssueLevel.WARNING,
        entity="ImportBatch",
        key=str(batch.id),
        message=f"Rollback completato: eliminati {sum(deleted.values())} record creati dal batch.",
    )
    return RollbackResult(batch_id=str(batch.id), deleted=deleted)
