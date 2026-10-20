"""Snapshot degli estratti PPM e profili di import.

R6: il PPM è la fonte di verità dei consuntivi. Ogni estratto importato resta archiviato
come snapshot immutabile, così la riconciliazione è sempre ripetibile.
"""

from __future__ import annotations

import re

from django.db import models
from simple_history.models import HistoricalRecords

from core.fields import DaysField
from core.models import TrackedModel
from imports.models import ImportedRecordMixin

_NORMALIZE_STRIP = re.compile(r"[\s_]+")


def normalize_project_code(code: str) -> str:
    """Chiave di confronto tollerante fra codici progetto.

    Gli estratti PPM a volte omettono il segmento BMED- e usano spazi o minuscole.
    """
    value = _NORMALIZE_STRIP.sub("", (code or "").upper())
    return value.replace("BMED-", "").replace("-BMED", "")


class SnapshotKind(models.TextChoices):
    PPM_WALLET = "PPM_WALLET", "Estratto wallet"
    PPM_CANONE = "PPM_CANONE", "Estratto canone"
    PPM_PROGETTI = "PPM_PROGETTI", "Estratto progetti"


class PpmSnapshot(TrackedModel, ImportedRecordMixin):
    kind = models.CharField(max_length=15, choices=SnapshotKind.choices, verbose_name="tipo")
    title = models.CharField(max_length=300, blank=True, verbose_name="titolo")
    extracted_at = models.DateTimeField(verbose_name="estratto il")
    source_filename = models.CharField(max_length=255, blank=True, verbose_name="file di origine")
    file = models.FileField(upload_to="ppm/%Y/%m/", null=True, blank=True, verbose_name="file")
    imported_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="importato da",
    )
    row_count = models.PositiveIntegerField(default=0, verbose_name="numero di righe")
    totals = models.JSONField(default=dict, blank=True, verbose_name="totali dichiarati")
    balanced = models.BooleanField(
        default=True,
        verbose_name="quadratura verificata",
        help_text="Somma delle righe uguale alla riga dei totali entro 0,01 gg.",
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "snapshot PPM"
        verbose_name_plural = "snapshot PPM"
        ordering = ("-extracted_at",)
        indexes = [models.Index(fields=("kind", "-extracted_at"))]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.extracted_at:%d/%m/%Y %H:%M}"


class PpmSnapshotRow(TrackedModel, ImportedRecordMixin):
    snapshot = models.ForeignKey(
        PpmSnapshot,
        on_delete=models.CASCADE,
        related_name="rows",
        verbose_name="snapshot",
    )
    project_code = models.CharField(max_length=200, verbose_name="codice progetto")
    normalized_code = models.CharField(
        max_length=200,
        editable=False,
        db_index=True,
        verbose_name="codice normalizzato",
    )
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ppm_rows",
        verbose_name="progetto associato",
    )
    canone_subactivity = models.ForeignKey(
        "canone.CanoneSubactivity",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ppm_rows",
        verbose_name="sotto-attività associata",
    )
    supplier_owner_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="responsabile Imola",
    )
    ppm_status = models.CharField(max_length=50, blank=True, verbose_name="stato PPM")
    planned_days = DaysField(null=True, blank=True, verbose_name="giornate previste")
    residual_days = DaysField(null=True, blank=True, verbose_name="giornate residue")
    total_days = DaysField(null=True, blank=True, verbose_name="giornate totali")
    raw = models.JSONField(default=dict, blank=True, verbose_name="riga originale")
    unmatched_reason = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="motivo del mancato abbinamento",
    )

    class Meta:
        verbose_name = "riga di snapshot PPM"
        verbose_name_plural = "righe di snapshot PPM"
        ordering = ("project_code",)
        indexes = [models.Index(fields=("snapshot", "project"))]

    def __str__(self) -> str:
        return self.project_code

    def save(self, *args, **kwargs) -> None:
        self.normalized_code = normalize_project_code(self.project_code)
        super().save(*args, **kwargs)


class ImportProfile(TrackedModel):
    """Mappatura delle colonne di un estratto PPM, modificabile da interfaccia.

    Serve quando Imola cambia il formato: si aggiorna il profilo senza toccare il codice.
    """

    name = models.CharField(max_length=100, unique=True, verbose_name="nome")
    kind = models.CharField(max_length=15, choices=SnapshotKind.choices, verbose_name="tipo")
    column_map = models.JSONField(
        default=dict,
        verbose_name="mappatura delle colonne",
        help_text='Es. {"progetto": "Progetto", "gg_totali": "gg tot"}',
    )
    header_hints = models.JSONField(
        default=list,
        blank=True,
        verbose_name="parole chiave dell'intestazione",
    )
    is_default = models.BooleanField(default=False, verbose_name="predefinito")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "profilo di import"
        verbose_name_plural = "profili di import"
        ordering = ("kind", "name")

    def __str__(self) -> str:
        return self.name
