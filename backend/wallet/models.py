"""Wallet annuale: contenitore delle giornate non consuntivate dei progetti.

R3: il disponibile non è mai un numero scritto a mano. Qui stanno solo le allocazioni;
i totali si calcolano in domain/wallet_balance.py.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from core.fields import DaysField
from core.models import TrackedModel, VerifiableMixin
from imports.models import ImportedRecordMixin

HISTORY_PREFIX = "STORICO-"


class ActivityKind(models.TextChoices):
    PROGETTO = "PROGETTO", "Progetto"
    ATTIVITA = "ATTIVITA", "Attività"
    REDMINE = "REDMINE", "Ticket Redmine"


class AllocationStatus(models.TextChoices):
    APERTA = "APERTA", "Aperta"
    CHIUSA = "CHIUSA", "Chiusa"


class WalletYear(TrackedModel, ImportedRecordMixin):
    year = models.PositiveSmallIntegerField(unique=True, verbose_name="anno")
    notes = models.TextField(blank=True, verbose_name="note")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "wallet annuale"
        verbose_name_plural = "wallet annuali"
        ordering = ("-year",)

    def __str__(self) -> str:
        return f"Wallet {self.year}"


class WalletActivity(TrackedModel, ImportedRecordMixin):
    """Destinazione di una allocazione: un progetto, un ticket o un'attività libera."""

    code = models.CharField(max_length=120, unique=True, verbose_name="codice")
    title = models.CharField(max_length=300, verbose_name="titolo")
    kind = models.CharField(max_length=10, choices=ActivityKind.choices, verbose_name="tipo")
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wallet_activities",
        verbose_name="progetto collegato",
    )
    redmine_ref = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
        verbose_name="riferimento Redmine",
    )
    client_owner = models.ForeignKey(
        "directory.Person",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_activities",
        verbose_name="referente BMED",
    )
    supplier_owner = models.ForeignKey(
        "directory.Person",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplied_activities",
        verbose_name="referente Imola",
    )
    notes = models.TextField(blank=True, verbose_name="note")
    is_technical = models.BooleanField(
        default=False,
        verbose_name="tecnica",
        help_text="Creata dall'import per tracciare giornate wallet storiche (vedi D-04).",
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "attività wallet"
        verbose_name_plural = "attività wallet"
        ordering = ("code",)

    def __str__(self) -> str:
        return self.code

    def clean(self) -> None:
        if self.kind == ActivityKind.PROGETTO and self.project_id is None:
            raise ValidationError(
                {"project": "Un'attività di tipo PROGETTO deve puntare a un progetto."}
            )


class WalletAllocation(TrackedModel, VerifiableMixin, ImportedRecordMixin):
    wallet_year = models.ForeignKey(
        WalletYear,
        on_delete=models.PROTECT,
        related_name="allocations",
        verbose_name="anno",
    )
    source_project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wallet_allocations",
        verbose_name="progetto di origine",
    )
    activity = models.ForeignKey(
        WalletActivity,
        on_delete=models.PROTECT,
        related_name="allocations",
        verbose_name="attività",
    )
    allocated_days = DaysField(verbose_name="giornate allocate")
    status = models.CharField(
        max_length=10,
        choices=AllocationStatus.choices,
        default=AllocationStatus.APERTA,
        verbose_name="stato",
    )
    notes = models.TextField(blank=True, verbose_name="note")
    external_ref = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name="riferimento di import",
    )
    requires_source_attribution = models.BooleanField(
        default=False,
        verbose_name="origine da attribuire",
        help_text="Allocazione dal wallet generale, senza progetto di origine.",
    )
    override_reason = models.TextField(
        blank=True,
        verbose_name="motivazione dello sforamento autorizzato",
    )
    override_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="autorizzato da",
    )
    is_technical = models.BooleanField(default=False, verbose_name="tecnica")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "allocazione wallet"
        verbose_name_plural = "allocazioni wallet"
        ordering = ("-wallet_year__year", "activity__code")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(allocated_days__gte=0),
                name="allocation_days_non_negative",
            ),
            models.UniqueConstraint(
                fields=("external_ref",),
                condition=~models.Q(external_ref=""),
                name="allocation_unique_external_ref",
            ),
        ]
        indexes = [
            models.Index(fields=("wallet_year", "status")),
            models.Index(fields=("source_project",)),
        ]

    def __str__(self) -> str:
        origin = self.source_project.code if self.source_project is not None else "wallet generale"
        return f"{origin} -> {self.activity.code}"

    def save(self, *args, **kwargs) -> None:
        self.requires_source_attribution = self.source_project_id is None
        super().save(*args, **kwargs)
