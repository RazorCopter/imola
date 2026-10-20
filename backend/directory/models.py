"""Organizzazioni e persone."""

from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from core.models import TrackedModel
from directory.normalization import comparison_key, normalize_person_name
from imports.models import ImportedRecordMixin


class OrganizationKind(models.TextChoices):
    CLIENT = "CLIENT", "Cliente"
    SUPPLIER = "SUPPLIER", "Fornitore"


class Organization(TrackedModel, ImportedRecordMixin):
    code = models.CharField(max_length=20, unique=True, verbose_name="codice")
    name = models.CharField(max_length=200, verbose_name="ragione sociale")
    kind = models.CharField(max_length=10, choices=OrganizationKind.choices, verbose_name="tipo")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "organizzazione"
        verbose_name_plural = "organizzazioni"
        ordering = ("code",)

    def __str__(self) -> str:
        return self.code


class PersonQuerySet(models.QuerySet):
    def by_name(self, name: str, organization: Organization | None = None):
        qs = self.filter(name_key=comparison_key(name))
        if organization is not None:
            qs = qs.filter(organization=organization)
        return qs


class Person(TrackedModel, ImportedRecordMixin):
    full_name = models.CharField(max_length=200, verbose_name="nome e cognome")
    name_key = models.CharField(max_length=200, editable=False, db_index=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="people",
        verbose_name="organizzazione",
    )
    # null distinto da stringa vuota: nel seed le email sono tutte assenti (D-07),
    # e serve poter dire "mai fornita" invece di "fornita vuota".
    email = models.EmailField(null=True, blank=True)  # noqa: DJ001
    is_active = models.BooleanField(default=True, verbose_name="attiva")
    needs_review = models.BooleanField(
        default=False,
        verbose_name="da normalizzare",
        help_text="Nome parziale o ambiguo: da confermare nella coda di revisione.",
    )
    review_note = models.TextField(blank=True, verbose_name="nota di revisione")
    history = HistoricalRecords()

    objects = PersonQuerySet.as_manager()

    class Meta:
        verbose_name = "persona"
        verbose_name_plural = "persone"
        ordering = ("full_name",)
        constraints = [
            models.UniqueConstraint(
                fields=("full_name", "organization"), name="person_unique_name_per_org"
            ),
            models.UniqueConstraint(
                fields=("name_key", "organization"), name="person_unique_key_per_org"
            ),
        ]

    def __str__(self) -> str:
        return self.full_name

    def save(self, *args, **kwargs) -> None:
        candidate = normalize_person_name(self.full_name)
        self.full_name = candidate.normalized or self.full_name
        self.name_key = candidate.key
        super().save(*args, **kwargs)
