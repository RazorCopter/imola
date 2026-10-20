"""Canone semestrale (organico allargato) e sue sotto-attività.

R4: il target progressivo alla data è
    target = min(monte, base_gg + settimane_trascorse * gg_per_settimana)
Il calcolo vive in domain/canone_status.py: qui stanno solo i parametri.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from core.fields import DaysField
from core.models import TrackedModel
from imports.models import ImportedRecordMixin

SEMESTER_RE = re.compile(r"^\d{4}-S[12]$")
REDMINE_RE = re.compile(r"#(\d{4,})")
LEADING_NUMBER_RE = re.compile(r"^\s*(\d{4,})\b")


def extract_redmine_ref(title: str) -> str:
    """Estrae il riferimento Redmine da un titolo di sotto-attività.

    Riconosce sia la forma "#300228 [Studio AIL] ..." sia il prefisso numerico nudo
    "300228 - ...", come appaiono negli estratti PPM.
    """
    if not title:
        return ""
    match = REDMINE_RE.search(title) or LEADING_NUMBER_RE.match(title)
    return match.group(1) if match else ""


class Office(models.TextChoices):
    EA = "EA", "Enterprise Architecture"
    SA = "SA", "Solution Architecture"
    TA = "TA", "Technology Architecture"
    CROSS = "CROSS", "Cross"


class Canone(TrackedModel, ImportedRecordMixin):
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="canoni",
        verbose_name="progetto",
    )
    semester = models.CharField(max_length=7, verbose_name="semestre", help_text="Es. 2026-S2")
    total_days = DaysField(verbose_name="monte giornate")
    target_base_days = DaysField(default=2, verbose_name="giornate base del target")
    target_days_per_week = DaysField(default=0, verbose_name="giornate per settimana")
    weeks_elapsed_at_import = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="settimane trascorse dichiarate",
        help_text="Valore riportato nell'estratto; il target corrente usa le settimane reali.",
    )
    cap_at_total = models.BooleanField(default=True, verbose_name="limita il target al monte")
    start_date = models.DateField(null=True, blank=True, verbose_name="inizio semestre")
    end_date = models.DateField(null=True, blank=True, verbose_name="fine semestre")
    extracted_at = models.DateField(null=True, blank=True, verbose_name="data di estrazione")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "canone"
        verbose_name_plural = "canoni"
        ordering = ("-semester",)
        constraints = [
            models.UniqueConstraint(fields=("project", "semester"), name="canone_unique_semester"),
            models.CheckConstraint(
                condition=models.Q(total_days__gt=0),
                name="canone_total_days_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"Canone {self.semester}"

    def clean(self) -> None:
        if not SEMESTER_RE.match(self.semester or ""):
            raise ValidationError({"semester": "Formato atteso AAAA-S1 o AAAA-S2."})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La fine del semestre precede l'inizio."})

    @staticmethod
    def semester_bounds(semester: str) -> tuple[str, str]:
        """Date di inizio e fine convenzionali di un semestre, in formato ISO."""
        year, half = semester.split("-S")
        if half == "1":
            return f"{year}-01-01", f"{year}-06-30"
        return f"{year}-07-01", f"{year}-12-31"


class CanoneSubactivity(TrackedModel, ImportedRecordMixin):
    canone = models.ForeignKey(
        Canone,
        on_delete=models.CASCADE,
        related_name="subactivities",
        verbose_name="canone",
    )
    office = models.CharField(
        max_length=5,
        choices=Office.choices,
        blank=True,
        verbose_name="ufficio",
    )
    title = models.CharField(max_length=400, verbose_name="titolo")
    redmine_ref = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
        verbose_name="riferimento Redmine",
    )
    quarter_estimate_days = DaysField(
        null=True,
        blank=True,
        verbose_name="stima del trimestre",
    )
    forecast_remaining_days = DaysField(
        null=True,
        blank=True,
        verbose_name="forecast residuo",
    )
    notes = models.TextField(blank=True, verbose_name="note")
    needs_review = models.BooleanField(
        default=False,
        verbose_name="da revisionare",
        help_text="Sotto-attività creata da un import PPM: ufficio da assegnare.",
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "sotto-attività del canone"
        verbose_name_plural = "sotto-attività del canone"
        ordering = ("office", "title")
        indexes = [models.Index(fields=("canone", "office"))]

    def __str__(self) -> str:
        return self.title[:80]

    def save(self, *args, **kwargs) -> None:
        if not self.redmine_ref:
            self.redmine_ref = extract_redmine_ref(self.title)
        super().save(*args, **kwargs)
