"""Progetti e milestone di fatturazione.

R1: lo stato della consuntivazione e lo stato della fatturazione sono indipendenti.
R2: l'anno di riferimento del residuo deriva dalla data di chiusura della consuntivazione.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import ExtractYear
from simple_history.models import HistoricalRecords

from core.fields import DaysField
from core.models import TrackedModel, VerifiableMixin
from imports.models import ImportedRecordMixin, ImportKind


class ContractType(models.TextChoices):
    CANONE = "CANONE", "Canone (organico allargato)"
    AQL = "AQL", "AQL (progetto a giornate)"
    CORPO = "CORPO", "A corpo"
    PPM = "PPM", "Attività su PPM interno"
    ATTIVITA = "ATTIVITA", "Attività"


class OfferStatus(models.TextChoices):
    INVIATA = "INVIATA", "Inviata"
    ACCETTATA = "ACCETTATA", "Accettata"
    SCADUTA = "SCADUTA", "Scaduta"
    NON_ACCETTATA = "NON_ACCETTATA", "Non accettata"


class TimesheetStatus(models.TextChoices):
    NON_AVVIATO = "NON_AVVIATO", "Non avviato"
    ATTIVO = "ATTIVO", "Attivo"
    CHIUSO = "CHIUSO", "Chiuso"
    DA_VERIFICARE = "DA_VERIFICARE", "Da verificare"


class BillingStatus(models.TextChoices):
    DA_FATTURARE = "DA_FATTURARE", "Da fatturare"
    PARZIALE = "PARZIALE", "Parziale"
    TOTALE = "TOTALE", "Totale"
    NON_FATTURABILE = "NON_FATTURABILE", "Non fatturabile"
    DA_VERIFICARE = "DA_VERIFICARE", "Da verificare"


class MilestoneStatus(models.TextChoices):
    PIANIFICATA = "PIANIFICATA", "Pianificata"
    FATTURATA = "FATTURATA", "Fatturata"
    SPOSTATA = "SPOSTATA", "Spostata"
    ANNULLATA = "ANNULLATA", "Annullata"
    DA_VERIFICARE = "DA_VERIFICARE", "Da verificare"


class Project(TrackedModel, VerifiableMixin, ImportedRecordMixin):
    code = models.CharField(max_length=120, unique=True, verbose_name="codice")
    title = models.CharField(max_length=300, verbose_name="titolo")
    contract_type = models.CharField(
        max_length=10,
        choices=ContractType.choices,
        verbose_name="tipo di contratto",
    )
    aro_code = models.CharField(max_length=50, blank=True, verbose_name="codice ARO")
    rda_code = models.CharField(max_length=50, blank=True, verbose_name="codice RDA")
    deliverable = models.CharField(max_length=100, blank=True, verbose_name="deliverable")

    client_owner = models.ForeignKey(
        "directory.Person",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_projects",
        verbose_name="referente BMED",
    )
    supplier_owner = models.ForeignKey(
        "directory.Person",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplied_projects",
        verbose_name="referente Imola",
    )

    budget_days = DaysField(verbose_name="giornate di budget")

    start_date = models.DateField(null=True, blank=True, verbose_name="data di inizio")
    planned_end_date = models.DateField(null=True, blank=True, verbose_name="fine prevista")
    actual_closure_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="chiusura consuntivazione",
    )

    offer_status = models.CharField(
        max_length=15,
        choices=OfferStatus.choices,
        default=OfferStatus.INVIATA,
        verbose_name="stato offerta",
    )
    timesheet_status = models.CharField(
        max_length=15,
        choices=TimesheetStatus.choices,
        default=TimesheetStatus.NON_AVVIATO,
        verbose_name="stato consuntivazione",
    )
    billing_status = models.CharField(
        max_length=20,
        choices=BillingStatus.choices,
        default=BillingStatus.DA_FATTURARE,
        verbose_name="stato fatturazione",
    )

    # Derivato in database dalla data di chiusura: non scrivibile (R2).
    residual_reference_year = models.GeneratedField(
        expression=ExtractYear("actual_closure_date"),
        output_field=models.IntegerField(null=True),
        db_persist=True,
        verbose_name="anno di riferimento del residuo",
    )
    declared_residual_year = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="anno residuo dichiarato nel seed",
        help_text="Solo informativo: valore importato, non usato nei calcoli (vedi D-03).",
    )

    notes = models.TextField(blank=True, verbose_name="note")
    legacy_excel_status = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="stato nell'Excel originale",
    )
    external_ref = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name="riferimento esterno",
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "progetto"
        verbose_name_plural = "progetti"
        ordering = ("code",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(budget_days__gte=0),
                name="project_budget_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(planned_end_date__isnull=True)
                | models.Q(start_date__isnull=True)
                | models.Q(planned_end_date__gte=models.F("start_date")),
                name="project_end_after_start",
            ),
            # I progetti CHIUSO senza data sono ammessi SOLO se provengono da un import SEED_JSON
            # (D-03, D-14): vincolo a livello DB raffinato dal trigger
            # trg_project_closed_requires_seed_batch e validato a livello di modello in clean().
            models.CheckConstraint(
                condition=~models.Q(timesheet_status=TimesheetStatus.CHIUSO)
                | models.Q(actual_closure_date__isnull=False)
                | models.Q(import_batch__isnull=False),
                name="project_closed_requires_date",
            ),
        ]
        indexes = [
            models.Index(fields=("timesheet_status",)),
            models.Index(fields=("billing_status",)),
            models.Index(fields=("contract_type",)),
        ]

    def __str__(self) -> str:
        return self.code

    @property
    def is_closed(self) -> bool:
        return self.timesheet_status == TimesheetStatus.CHIUSO

    @property
    def is_unverified(self) -> bool:
        return self.timesheet_status == TimesheetStatus.DA_VERIFICARE

    def clean(self) -> None:
        errors: dict[str, Any] = {}
        if self.timesheet_status == TimesheetStatus.ATTIVO and (
            self.offer_status != OfferStatus.ACCETTATA
        ):
            errors["timesheet_status"] = (
                "Il progetto non può passare ad ATTIVO se l'offerta non è ACCETTATA."
            )
        if self.timesheet_status == TimesheetStatus.CHIUSO and self.actual_closure_date is None:
            is_seed = False
            if self.import_batch_id:
                try:
                    is_seed = (
                        self.import_batch is not None
                        and self.import_batch.kind == ImportKind.SEED_JSON
                    )
                except Exception:
                    is_seed = False
            if not is_seed:
                errors["actual_closure_date"] = (
                    "La data di chiusura è obbligatoria per un progetto CHIUSO "
                    "(l'eccezione è riservata al solo import seed JSON, vedi D-03/D-14)."
                )
        if (
            self.actual_closure_date
            and self.start_date
            and (self.actual_closure_date < self.start_date)
        ):
            errors["actual_closure_date"] = "La chiusura non può precedere l'inizio."
        if errors:
            raise ValidationError(errors)


class BillingMilestone(TrackedModel, ImportedRecordMixin):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="milestones",
        verbose_name="progetto",
    )
    planned_date = models.DateField(null=True, blank=True, verbose_name="data prevista")
    actual_date = models.DateField(null=True, blank=True, verbose_name="data effettiva")
    amount_days = DaysField(null=True, blank=True, verbose_name="giornate")
    status = models.CharField(
        max_length=15,
        choices=MilestoneStatus.choices,
        default=MilestoneStatus.PIANIFICATA,
        verbose_name="stato",
    )
    move_count = models.PositiveSmallIntegerField(default=0, verbose_name="numero di spostamenti")
    moves = models.JSONField(default=list, blank=True, verbose_name="storico degli spostamenti")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "milestone di fatturazione"
        verbose_name_plural = "milestone di fatturazione"
        ordering = ("planned_date", "created_at")

    def __str__(self) -> str:
        when = self.planned_date.isoformat() if self.planned_date else "senza data"
        return f"{self.project.code} - {when}"

    def move_to(self, new_date, reason: str, user: Any | None = None) -> None:
        """Sposta la milestone registrando la motivazione, che è obbligatoria."""
        if not reason or not reason.strip():
            raise ValidationError({"reason": "La motivazione dello spostamento è obbligatoria."})
        from django.utils import timezone

        self.moves = [
            *(self.moves or []),
            {
                "da": self.planned_date.isoformat() if self.planned_date else None,
                "a": new_date.isoformat() if new_date else None,
                "motivazione": reason.strip(),
                "spostata_da": getattr(user, "username", None),
                "spostata_il": timezone.now().isoformat(),
            },
        ]
        self.planned_date = new_date
        self.move_count = (self.move_count or 0) + 1
        self.status = MilestoneStatus.SPOSTATA
