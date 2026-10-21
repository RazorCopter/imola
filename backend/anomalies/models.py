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
    external_ref = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name="riferimento esterno",
    )
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

    def extract_covered_entities(self) -> set[str]:
        """Estrae i codici entità coperti da questa anomalia (progetto, context, ecc.)."""
        entities: set[str] = set()
        project = getattr(self, "project", None)
        if project is not None and getattr(project, "code", None):
            entities.add(project.code)
        if self.context and isinstance(self.context, dict):
            keys = (
                "project_code",
                "codice_progetto",
                "entity",
                "entita",
                "ref",
                "reference",
                "code",
            )
            for key in keys:
                val = self.context.get(key)
                if val and isinstance(val, str):
                    entities.add(val)
            for list_key in ("entities", "entita_coinvolte", "projects", "progetti"):
                val = self.context.get(list_key)
                if isinstance(val, (list, tuple, set)):
                    for item in val:
                        if isinstance(item, str):
                            entities.add(item)
        return entities

    def mark_superseded(
        self,
        replacement: Anomaly | list[Anomaly] | tuple[Anomaly, ...],
        expected_entities: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> None:
        """Chiude un'anomalia del seed coperta da una o più regole automatiche (D-05).

        Se sono specificate `expected_entities`, l'anomalia si chiude SOLO se tutte
        le entità attese risultano coperte dall'insieme delle anomalie sostitutive.
        """
        if isinstance(replacement, Anomaly):
            replacements = [replacement]
        elif isinstance(replacement, (list, tuple)) and replacement:
            replacements = list(replacement)
        else:
            raise ValidationError({"superseded_by": "L'anomalia sostitutiva non è valida."})

        for rep in replacements:
            if not isinstance(rep, Anomaly):
                raise ValidationError({"superseded_by": "L'anomalia sostitutiva non è valida."})
            if rep == self or (self.pk and rep.pk and self.pk == rep.pk):
                raise ValidationError(
                    {"superseded_by": "Un'anomalia non può sostituire se stessa."}
                )
            if rep._state.adding or not rep.pk:
                raise ValidationError(
                    {"superseded_by": "L'anomalia sostitutiva deve essere prima salvata."}
                )

        if expected_entities:
            covered: set[str] = set()
            for rep in replacements:
                covered.update(rep.extract_covered_entities())
            missing = set(expected_entities) - covered
            if missing:
                raise ValidationError(
                    {
                        "superseded_by": (
                            f"Copertura incompleta: mancano le entità {sorted(missing)}."
                        )
                    }
                )

        from django.utils import timezone

        self.superseded_by = replacements[0]
        self.status = AnomalyStatus.RISOLTA
        self.resolved_at = timezone.now()

        if len(replacements) == 1:
            self.resolution_note = (
                f"Sostituita dal controllo automatico {replacements[0].rule_code} "
                f"(anomalia {replacements[0].id})."
            )
        else:
            rule_codes = ", ".join(sorted({r.rule_code for r in replacements}))
            ids_str = ", ".join(str(r.id) for r in replacements)
            entities_str = (
                ", ".join(expected_entities) if expected_entities else ", ".join(sorted(covered))
            )
            self.resolution_note = (
                f"Sostituita dai controlli automatici {rule_codes} (anomalie: {ids_str}) "
                f"coprendo tutte le entità: {entities_str}."
            )
            if not isinstance(self.context, dict):
                self.context = {}
            self.context["superseded_by_ids"] = [str(r.id) for r in replacements]
