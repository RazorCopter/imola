"""Consuntivi: registro append-only delle giornate.

Niente update e niente delete sui movimenti: una correzione è una nuova riga di storno che
punta alla riga stornata (campo reverses). Esattamente uno fra project, canone_subactivity e
wallet_allocation è valorizzato, garantito da un check constraint.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from core.fields import DaysField
from core.models import TrackedModel
from imports.models import ImportedRecordMixin


class TimesheetSource(models.TextChoices):
    PPM_IMPORT = "PPM_IMPORT", "Import PPM"
    MANUALE = "MANUALE", "Inserimento manuale"
    SEED_INIZIALE = "SEED_INIZIALE", "Seed iniziale"
    STORNO = "STORNO", "Storno"


def month_start(value: date) -> date:
    return value.replace(day=1)


class TimesheetEntry(TrackedModel, ImportedRecordMixin):
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="timesheet_entries",
        verbose_name="progetto",
    )
    canone_subactivity = models.ForeignKey(
        "canone.CanoneSubactivity",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="timesheet_entries",
        verbose_name="sotto-attività del canone",
    )
    wallet_allocation = models.ForeignKey(
        "wallet.WalletAllocation",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="timesheet_entries",
        verbose_name="allocazione wallet",
    )

    period = models.DateField(
        verbose_name="data",
        help_text="Data di competenza del consuntivo.",
    )
    days = DaysField(verbose_name="giornate")
    source = models.CharField(
        max_length=15,
        choices=TimesheetSource.choices,
        verbose_name="origine del dato",
    )
    ppm_snapshot = models.ForeignKey(
        "ppm.PpmSnapshot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="timesheet_entries",
        verbose_name="snapshot PPM",
    )
    reverses = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversals",
        verbose_name="storna la riga",
    )
    note = models.CharField(max_length=300, blank=True, verbose_name="nota")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "consuntivo"
        verbose_name_plural = "consuntivi"
        ordering = ("-period", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        project__isnull=False,
                        canone_subactivity__isnull=True,
                        wallet_allocation__isnull=True,
                    )
                    | models.Q(
                        project__isnull=True,
                        canone_subactivity__isnull=False,
                        wallet_allocation__isnull=True,
                    )
                    | models.Q(
                        project__isnull=True,
                        canone_subactivity__isnull=True,
                        wallet_allocation__isnull=False,
                    )
                ),
                name="timesheet_exactly_one_target",
            ),
            models.CheckConstraint(
                condition=~models.Q(days=0),
                name="timesheet_days_not_zero",
            ),
        ]
        indexes = [
            models.Index(fields=("period",)),
            models.Index(fields=("project", "period")),
            models.Index(fields=("wallet_allocation", "period")),
            models.Index(fields=("canone_subactivity", "period")),
        ]

    def __str__(self) -> str:
        return f"{self.target_label} {self.period:%Y-%m} {self.days} gg"

    @property
    def target_label(self) -> str:
        if self.project is not None:
            return self.project.code
        if self.canone_subactivity_id:
            return f"canone/{self.canone_subactivity}"
        return f"wallet/{self.wallet_allocation}"

    def clean(self) -> None:
        targets = [self.project_id, self.canone_subactivity_id, self.wallet_allocation_id]
        if sum(1 for target in targets if target) != 1:
            raise ValidationError(
                "Indicare esattamente un bersaglio: progetto, sotto-attività o allocazione."
            )
        if self.days is not None and Decimal(self.days) == 0:
            raise ValidationError({"days": "Le giornate non possono essere zero."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError(
                "I consuntivi sono append-only: per correggere, registrare uno storno."
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise ValidationError(
            "I consuntivi non si cancellano: registrare una riga di storno (reverses)."
        )

    def build_reversal(self, note: str = "") -> TimesheetEntry:
        """Crea (senza salvare) la riga che annulla questa."""
        return TimesheetEntry(
            project=self.project,
            canone_subactivity=self.canone_subactivity,
            wallet_allocation=self.wallet_allocation,
            period=self.period,
            days=-Decimal(self.days),
            source=TimesheetSource.STORNO,
            reverses=self,
            note=note or f"Storno di {self.id}",
        )
