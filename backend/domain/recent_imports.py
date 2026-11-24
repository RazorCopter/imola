"""Evidenza dei progetti toccati da un'importazione Excel recente.

L'estratto operativo settimanale non crea né modifica progetti: aggiunge consuntivi
(append-only) su progetti e allocazioni wallet esistenti. Un progetto è quindi
"nuovo inserimento" se ha ricevuto consuntivi da un batch OPERATIONAL_XLSX applicato
nelle ultime 24 ore, direttamente o tramite le allocazioni wallet che finanzia.
I consuntivi poi stornati e i batch annullati non contano.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import models
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone

RECENT_IMPORT_WINDOW = timedelta(hours=24)


def imported_entries() -> models.QuerySet:
    """Consuntivi vivi arrivati da un estratto operativo effettivamente applicato."""
    from imports.models import ImportKind, ImportStatus
    from timesheets.models import TimesheetEntry, TimesheetSource

    return TimesheetEntry.objects.filter(
        source=TimesheetSource.EXCEL_IMPORT,
        import_batch__kind=ImportKind.OPERATIONAL_XLSX,
        import_batch__status=ImportStatus.APPLIED,
        import_batch__applied_at__isnull=False,
        reversals__isnull=True,
    )


def annotate_last_excel_import(queryset: models.QuerySet) -> models.QuerySet:
    """Annota `last_excel_import_at` sui progetti: istante dell'ultimo import che li ha toccati."""

    def latest(lookup: str) -> models.Subquery:
        return models.Subquery(
            imported_entries()
            .filter(**{lookup: models.OuterRef("pk")})
            .order_by("-import_batch__applied_at")
            .values("import_batch__applied_at")[:1],
            output_field=models.DateTimeField(),
        )

    direct = latest("project")
    via_wallet = latest("wallet_allocation__source_project")
    # Greatest restituisce NULL se un argomento è NULL su alcuni backend: si normalizza.
    return queryset.annotate(
        last_excel_import_at=Greatest(
            Coalesce(direct, via_wallet),
            Coalesce(via_wallet, direct),
        )
    )


def is_recent_import(applied_at: datetime | None, now: datetime | None = None) -> bool:
    if applied_at is None:
        return False
    return applied_at >= (now or timezone.now()) - RECENT_IMPORT_WINDOW
