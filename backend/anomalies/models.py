"""Anomalie rilevate dal motore controlli (o importate dal seed).

La deduplica usa il fingerprint: hash di codice regola + riferimenti alle entità, senza i
valori. Così un valore che cambia aggiorna la descrizione invece di creare un doppione.
"""

from __future__ import annotations

import hashlib

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from core.models import TrackedModel
from imports.models import ImportedRecordMixin

SEED_RULE_CODE = "SEED_MANUALE"


class Severity(models.TextChoices):
    ALTA = "ALTA", "Alta"
    MEDIA = "MEDIA", "Media"
    BASSA = "BASSA", "Bassa"


class Scope(models.TextChoices):
    WALLET = "WALLET", "Wallet"
    PROGETTO = "PROGETTO", "Progetto"
    CANONE = "CANONE", "Canone"
    RICONCILIAZIONE = "RICONCILIAZIONE", "Riconciliazione"
    DOPPIO_CONTEGGIO = "DOPPIO_CONTEGGIO", "Doppio conteggio"
    ANAGRAFICA = "ANAGRAFICA", "Anagrafica"


class AnomalyStatus(models.TextChoices):
    APERTA = "APERTA", "Aperta"
    IN_VERIFICA = "IN_VERIFICA", "In verifica"
    RISOLTA = "RISOLTA", "Risolta"
    ACCETTATA = "ACCETTATA", "Accettata come eccezione"


def build_fingerprint(rule_code: str, *refs: object) -> str:
    """Impronta stabile dell'anomalia: regola + entità coinvolte, mai i valori."""
    payload = "|".join([rule_code, *(str(ref) for ref in refs if ref is not None)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Anomaly(TrackedModel, ImportedRecordMixin):
    rule_code = models.CharField(max_length=40, db_index=True, verbose_name="codice regola")
    severity = models.CharField(max_length=6, choices=Severity.choices, verbose_name="severità")
    scope = models.CharField(max_length=20, choices=Scope.choices, verbose_name="ambito")
    description = models.TextField(verbose_name="descrizione")
    suggested_action = models.TextField(blank=True, verbose_name="azione suggerita")
    context = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="dati del calcolo",
        help_text="Valori che hanno fatto scattare la regola, per spiegare il numero.",
    )

    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="anomalies",
        verbose_name="progetto",
    )
    allocation = models.ForeignKey(
        "wallet.WalletAllocation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="anomalies",
        verbose_name="allocazione",
    )
    subactivity = models.ForeignKey(
        "canone.CanoneSubactivity",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="anomalies",
        verbose_name="sotto-attività",
    )
    canone = models.ForeignKey(
        "canone.Canone",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="anomalies",
        verbose_name="canone",
    )
    snapshot_row = models.ForeignKey(
        "ppm.PpmSnapshotRow",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="anomalies",
        verbose_name="riga di snapshot",
    )
    person = models.ForeignKey(
        "directory.Person",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="anomalies",
        verbose_name="persona",
    )
    milestone = models.ForeignKey(
        "projects.BillingMilestone",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="anomalies",
        verbose_name="milestone",
    )

    status = models.CharField(
        max_length=12,
        choices=AnomalyStatus.choices,
        default=AnomalyStatus.APERTA,
        verbose_name="stato",
    )
    resolution_note = models.TextField(blank=True, verbose_name="nota di risoluzione")
    accepted_until = models.DateField(
        null=True,
        blank=True,
        verbose_name="deroga valida fino al",
    )
    assigned_to = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="in carico a",
    )
    detected_at = models.DateTimeField(auto_now_add=True, verbose_name="rilevata il")
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="ultima rilevazione",
    )
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="risolta il")
    fingerprint = models.CharField(max_length=64, unique=True, verbose_name="impronta")
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supersedes",
        verbose_name="sostituita da",
        help_text="Anomalia automatica che copre la stessa situazione (vedi D-05).",
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "anomalia"
        verbose_name_plural = "anomalie"
        ordering = ("severity", "-detected_at")
        indexes = [
            models.Index(fields=("status", "severity")),
            models.Index(fields=("scope", "status")),
        ]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.rule_code}"

    @property
    def is_open(self) -> bool:
        return self.status in {AnomalyStatus.APERTA, AnomalyStatus.IN_VERIFICA}

    @property
    def is_from_seed(self) -> bool:
        return self.rule_code == SEED_RULE_CODE

    def resolve(self, note: str, user=None) -> None:
        if not note or not note.strip():
            raise ValidationError({"resolution_note": "La nota di risoluzione è obbligatoria."})
        from django.utils import timezone

        self.status = AnomalyStatus.RISOLTA
        self.resolution_note = note.strip()
        self.resolved_at = timezone.now()
        if user is not None:
            self.assigned_to = user

    def accept(self, note: str, until=None, user=None) -> None:
        if not note or not note.strip():
            raise ValidationError(
                {"resolution_note": "La motivazione della deroga è obbligatoria."}
            )
        from django.utils import timezone

        self.status = AnomalyStatus.ACCETTATA
        self.resolution_note = note.strip()
        self.accepted_until = until
        self.resolved_at = timezone.now()
        if user is not None:
            self.assigned_to = user

    def mark_superseded(self, replacement: Anomaly) -> None:
        """Chiude un'anomalia del seed coperta da una regola automatica (D-05)."""
        from django.utils import timezone

        self.superseded_by = replacement
        self.status = AnomalyStatus.RISOLTA
        self.resolution_note = (
            f"Sostituita dal controllo automatico {replacement.rule_code} "
            f"(anomalia {replacement.id})."
        )
        self.resolved_at = timezone.now()
