"""Modelli di base: tracciatura, concorrenza ottimistica, impostazioni globali."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from core.current_user import get_current_user


class RoleCapabilityOverride(models.Model):
    """Fonte persistente delle capability effettive per i ruoli applicativi."""

    role = models.CharField(max_length=64)
    capability = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("role", "capability"), name="core_unique_role_capability"
            )
        ]
        ordering = ("role", "capability")

    def __str__(self) -> str:
        return f"{self.role}: {self.capability}={self.enabled}"


class AdminAuditEvent(models.Model):
    """Audit minimale delle operazioni amministrative, senza dati segreti."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_audit_events",
    )
    actor_username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=32)
    target_id = models.CharField(max_length=128, blank=True)
    target_label = models.CharField(max_length=150, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.created_at.isoformat()} {self.actor_username or '-'} {self.action}"


class Reliability(models.TextChoices):
    CERTO = "CERTO", "Certo"
    DA_VERIFICARE = "DA_VERIFICARE", "Da verificare"


class TrackedModel(models.Model):
    """Base di tutte le entità: UUID, timestamp, autore, versione per il locking."""

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="creato da",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="modificato da",
    )
    version = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        user = get_current_user()
        if self.id is None:
            self.id = uuid.uuid4()
        if self._state.adding:
            if user is not None and self.created_by_id is None:
                self.created_by = user
        else:
            self.version = (self.version or 0) + 1
        if user is not None:
            self.updated_by = user
        super().save(*args, **kwargs)


class AppSettings(TrackedModel):
    """Parametri globali configurabili (riga singola)."""

    singleton = models.BooleanField(default=True, unique=True, editable=False)
    hours_per_day = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("8.00"),
        verbose_name="ore per giornata",
    )
    ppm_granularity_days = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal("0.0625"),
        verbose_name="granularità PPM (gg)",
    )
    reconciliation_tolerance_days = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal("0.0100"),
        verbose_name="tolleranza di riconciliazione (gg)",
    )
    daily_person_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="costo globale per giornata uomo",
        help_text="Valore globale corrente; non è storicizzato per periodo o fornitore.",
    )
    canone_fixed_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="costo forfettario per canone",
        help_text="Importo intero pagato all'attivazione di ciascun canone, indipendente dai consuntivi.",
    )
    residual_years_after_closure = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="anni di validità del residuo dopo la chiusura",
    )
    residual_expiring_window_days = models.PositiveSmallIntegerField(
        default=90,
        verbose_name="finestra in giorni per i residui in scadenza",
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "impostazioni"
        verbose_name_plural = "impostazioni"

    def __str__(self) -> str:
        return "Impostazioni globali"

    def clean(self) -> None:
        if self.hours_per_day <= 0:
            raise ValidationError({"hours_per_day": "Deve essere maggiore di zero."})
        if self.daily_person_cost is None or self.daily_person_cost < 0:
            raise ValidationError({"daily_person_cost": "Deve essere maggiore o uguale a zero."})
        if self.canone_fixed_cost is None or self.canone_fixed_cost < 0:
            raise ValidationError({"canone_fixed_cost": "Deve essere maggiore o uguale a zero."})

    @classmethod
    def get_solo(cls) -> AppSettings:
        obj, _ = cls.objects.get_or_create(singleton=True)
        return obj


class VerificationPointStatus(models.TextChoices):
    APERTO = "APERTO", "Aperto"
    VERIFICATO = "VERIFICATO", "Verificato"


def verification_point(text: str) -> dict[str, Any]:
    """Struttura di un punto da verificare importato."""
    return {
        "testo": text,
        "stato": VerificationPointStatus.APERTO.value,
        "nota": "",
        "verificato_da": None,
        "verificato_il": None,
    }


class VerifiableMixin(models.Model):
    """Affidabilità del dato e punti da verificare, chiudibili uno a uno con nota."""

    reliability = models.CharField(
        max_length=15,
        choices=Reliability.choices,
        default=Reliability.CERTO,
        verbose_name="affidabilità",
    )
    verification_points = models.JSONField(
        default=list,
        blank=True,
        verbose_name="punti da verificare",
    )

    class Meta:
        abstract = True

    @property
    def open_verification_points(self) -> list[dict[str, Any]]:
        return [
            point
            for point in (self.verification_points or [])
            if point.get("stato") != VerificationPointStatus.VERIFICATO.value
        ]

    @property
    def has_open_verifications(self) -> bool:
        return bool(self.open_verification_points)

    def mark_verification_point(self, index: int, note: str, user: Any | None = None) -> None:
        """Chiude un punto da verificare. La nota è obbligatoria (tracciata da history)."""
        if not note or not note.strip():
            raise ValidationError({"nota": "La nota di verifica è obbligatoria."})
        points = list(self.verification_points or [])
        if index < 0 or index >= len(points):
            raise ValidationError({"indice": "Punto da verificare inesistente."})
        from django.utils import timezone

        points[index] = {
            **points[index],
            "stato": VerificationPointStatus.VERIFICATO.value,
            "nota": note.strip(),
            "verificato_da": getattr(user, "username", None),
            "verificato_il": timezone.now().isoformat(),
        }
        self.verification_points = points
        if not any(
            point.get("stato") != VerificationPointStatus.VERIFICATO.value for point in points
        ):
            self.reliability = Reliability.CERTO
