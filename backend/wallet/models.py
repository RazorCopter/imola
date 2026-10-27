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


class AllocationClosureReason(models.TextChoices):
    ESAURITA = "ESAURITA", "Completamente erosa"
    CON_RESIDUO = "CON_RESIDUO", "Chiusa con residuo rilasciato"


class SourceLotStatus(models.TextChoices):
    DISPONIBILE = "DISPONIBILE", "Disponibile"
    IMPEGNATO = "IMPEGNATO", "Impegnato"
    CHIUSURA_DA_VALIDARE = "CHIUSURA_DA_VALIDARE", "Chiusura da validare"
    CHIUSO = "CHIUSO", "Chiuso"


class WalletYear(TrackedModel, ImportedRecordMixin):
    year = models.PositiveSmallIntegerField(unique=True, verbose_name="anno")
    notes = models.TextField(blank=True, verbose_name="note")
    reconciliation_adjustment_days = DaysField(
        default=0,
        verbose_name="rettifica di riconciliazione Excel",
        help_text="Scarto esplicito tra KPI del workbook e somma delle righe arrotondate.",
    )
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


class WalletSourceLot(TrackedModel, ImportedRecordMixin):
    """Residuo di un progetto che alimenta il wallet e conserva la provenienza."""

    wallet_year = models.ForeignKey(
        WalletYear, on_delete=models.PROTECT, related_name="source_lots", verbose_name="wallet"
    )
    source_project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="wallet_source_lots",
        verbose_name="progetto di origine",
    )
    source_year = models.PositiveSmallIntegerField(verbose_name="anno di provenienza")
    capacity_days = DaysField(verbose_name="giornate conferite")
    effective_date = models.DateField(null=True, blank=True, verbose_name="data di conferimento")
    status = models.CharField(
        max_length=24,
        choices=SourceLotStatus.choices,
        default=SourceLotStatus.DISPONIBILE,
        verbose_name="stato lotto",
    )
    external_ref = models.CharField(max_length=100, unique=True, verbose_name="riferimento import")
    notes = models.TextField(blank=True, verbose_name="note")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "lotto sorgente wallet"
        verbose_name_plural = "lotti sorgente wallet"
        ordering = ("source_year", "effective_date", "source_project__code")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(capacity_days__gte=0), name="wallet_source_capacity_non_negative"
            ),
            models.UniqueConstraint(
                fields=("wallet_year", "source_project"), name="wallet_source_project_per_year"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_project.code}: {self.capacity_days} gg"


class WalletAllocation(TrackedModel, VerifiableMixin, ImportedRecordMixin):
    """Utilizzo del wallet; le fonti sono nelle relative tranche FIFO."""
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
    assignee = models.ForeignKey(
        "directory.Person",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wallet_allocations",
        verbose_name="architetto assegnatario",
        help_text="Obbligatorio per le nuove allocazioni create dall'interfaccia.",
    )
    allocated_days = DaysField(verbose_name="giornate allocate")
    initial_allocated_days = DaysField(
        default=0, verbose_name="giornate originariamente riservate"
    )
    status = models.CharField(
        max_length=10,
        choices=AllocationStatus.choices,
        default=AllocationStatus.APERTA,
        verbose_name="stato",
    )
    closure_reason = models.CharField(  # noqa: DJ001
        max_length=20,
        choices=AllocationClosureReason.choices,
        null=True,
        blank=True,
        verbose_name="motivo chiusura",
    )
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="chiusa il")
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
        if self.initial_allocated_days == 0 and self.allocated_days > 0:
            self.initial_allocated_days = self.allocated_days
        has_funding = bool(self.pk and self.funding_tranches.exists())
        self.requires_source_attribution = False if has_funding else self.source_project_id is None
        super().save(*args, **kwargs)


class WalletFundingTranche(TrackedModel, ImportedRecordMixin):
    """Quota di un utilizzo finanziata da uno specifico lotto sorgente."""

    allocation = models.ForeignKey(
        WalletAllocation,
        on_delete=models.CASCADE,
        related_name="funding_tranches",
        verbose_name="utilizzo wallet",
    )
    source_lot = models.ForeignKey(
        WalletSourceLot,
        on_delete=models.PROTECT,
        related_name="funding_tranches",
        verbose_name="lotto sorgente",
    )
    sequence = models.PositiveSmallIntegerField(verbose_name="ordine FIFO")
    initial_reserved_days = DaysField(verbose_name="giornate inizialmente riservate")
    committed_days = DaysField(verbose_name="giornate attualmente impegnate")
    consumed_days = DaysField(default=0, verbose_name="giornate erose")
    external_ref = models.CharField(max_length=100, unique=True, verbose_name="riferimento import")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "tranche di finanziamento wallet"
        verbose_name_plural = "tranche di finanziamento wallet"
        ordering = ("allocation", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("allocation", "sequence"), name="wallet_funding_sequence_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(initial_reserved_days__gte=0),
                name="wallet_funding_initial_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(committed_days__gte=0),
                name="wallet_funding_committed_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(consumed_days__gte=0),
                name="wallet_funding_consumed_non_negative",
            ),
        ]

    def clean(self) -> None:
        if self.committed_days > self.initial_reserved_days:
            raise ValidationError({"committed_days": "Non può superare la riserva iniziale."})
        if self.consumed_days > self.committed_days:
            raise ValidationError({"consumed_days": "Non può superare le giornate impegnate."})
