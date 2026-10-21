"""Tracciamento dei batch di import, per diff, applicazione e rollback."""

from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from core.models import TrackedModel


class ImportKind(models.TextChoices):
    SEED_JSON = "SEED_JSON", "Seed JSON"
    PPM_XLSX = "PPM_XLSX", "Estratto PPM (Excel)"
    PPM_PDF = "PPM_PDF", "Estratto PPM (PDF)"
    EXCEL_LEGACY = "EXCEL_LEGACY", "Excel storico"


class ImportStatus(models.TextChoices):
    DRY_RUN = "DRY_RUN", "Simulazione"
    APPLIED = "APPLIED", "Applicato"
    ROLLED_BACK = "ROLLED_BACK", "Annullato"
    FAILED = "FAILED", "Errore"


class ImportIssueLevel(models.TextChoices):
    WARNING = "WARNING", "Avviso"
    ERROR = "ERROR", "Errore"


class ImportBatch(TrackedModel):
    kind = models.CharField(max_length=20, choices=ImportKind.choices, verbose_name="tipo")
    status = models.CharField(
        max_length=20,
        choices=ImportStatus.choices,
        default=ImportStatus.DRY_RUN,
        verbose_name="stato",
    )
    file = models.FileField(upload_to="imports/%Y/%m/", null=True, blank=True)
    source_filename = models.CharField(max_length=255, blank=True, verbose_name="nome file")
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        verbose_name="hash SHA-256 del contenuto",
    )
    report = models.JSONField(default=dict, blank=True, verbose_name="report")
    applied_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="applicato da",
    )
    applied_at = models.DateTimeField(null=True, blank=True, verbose_name="applicato il")
    rolled_back_at = models.DateTimeField(null=True, blank=True, verbose_name="annullato il")
    error = models.TextField(blank=True, verbose_name="errore")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "batch di import"
        verbose_name_plural = "batch di import"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.source_filename or self.id} [{self.status}]"

    @property
    def can_apply(self) -> bool:
        return self.status == ImportStatus.DRY_RUN

    @property
    def can_rollback(self) -> bool:
        return self.status == ImportStatus.APPLIED


class ImportIssue(TrackedModel):
    """Avviso o errore strutturato emerso durante l'applicazione di un batch."""

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="issues")
    level = models.CharField(max_length=10, choices=ImportIssueLevel.choices)
    entity = models.CharField(max_length=100, blank=True)
    key = models.CharField(max_length=255, blank=True)
    message = models.TextField()

    class Meta:
        verbose_name = "problema di import"
        verbose_name_plural = "problemi di import"
        ordering = ("created_at",)

    def __str__(self) -> str:
        location = f" [{self.entity}:{self.key}]" if self.entity or self.key else ""
        return f"{self.get_level_display()}{location}: {self.message}"


class ImportedRecordMixin(models.Model):
    """Ogni record creato da un import ricorda il batch, per il rollback completo."""

    import_batch = models.ForeignKey(
        ImportBatch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_records",
        verbose_name="batch di import",
    )

    class Meta:
        abstract = True
