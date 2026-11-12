"""Tracciamento dei batch di import, per diff, applicazione e rollback."""

from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from core.fields import DaysField
from core.models import TrackedModel


class ImportKind(models.TextChoices):
    SEED_JSON = "SEED_JSON", "Seed JSON"
    WORKBOOK_JSON = "WORKBOOK_JSON", "Workbook JSON completo"
    PPM_XLSX = "PPM_XLSX", "Estratto PPM (Excel)"
    PPM_PDF = "PPM_PDF", "Estratto PPM (PDF)"
    EXCEL_LEGACY = "EXCEL_LEGACY", "Excel storico"
    OPERATIONAL_XLSX = "OPERATIONAL_XLSX", "Estratto operativo settimanale (Excel)"


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


class MappingKind(models.TextChoices):
    """Che cosa un'associazione di riconciliazione mette in corrispondenza."""

    PROGETTO = "PROGETTO", "Codice progetto"
    WALLET_ALLOCATION = "WALLET_ALLOCATION", "Sottoprogetto wallet"
    CANONE_SUBACTIVITY = "CANONE_SUBACTIVITY", "Attività dell'organico allargato"
    COLLABORATORE = "COLLABORATORE", "Collaboratore"


class ImportMapping(TrackedModel):
    """Associazione fra un valore dell'Excel e una voce dell'applicativo.

    È il registro della sezione Riconciliazione: ciò che una volta è stato agganciato a
    mano non va più riagganciato nelle settimane successive. `created_by` e `created_at` di
    `TrackedModel` conservano chi ha confermato l'associazione e quando.

    Il contesto serve perché lo stesso testo può puntare a voci diverse secondo il periodo:
    un titolo di attività esiste sia nel canone 2026-S1 sia nel 2026-S2.
    """

    kind = models.CharField(max_length=20, choices=MappingKind.choices, verbose_name="tipo")
    external_value = models.CharField(
        max_length=400,
        verbose_name="valore nell'Excel",
        help_text="Il testo come appare nel foglio, conservato per mostrarlo all'utente.",
    )
    external_key = models.CharField(
        max_length=400,
        db_index=True,
        verbose_name="chiave normalizzata",
        help_text="Valore senza spazi, accenti e maiuscole: è su questa che si confronta.",
    )
    context_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="anno di contesto",
        help_text="Anno del wallet, quando il tipo lo richiede.",
    )
    context_semester = models.CharField(
        max_length=7,
        blank=True,
        verbose_name="semestre di contesto",
        help_text="Semestre del canone, es. 2026-S2.",
    )
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="import_mappings",
        verbose_name="progetto",
    )
    wallet_allocation = models.ForeignKey(
        "wallet.WalletAllocation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="import_mappings",
        verbose_name="allocazione wallet",
    )
    canone_subactivity = models.ForeignKey(
        "canone.CanoneSubactivity",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="import_mappings",
        verbose_name="sotto-attività del canone",
    )
    user = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="import_mappings",
        verbose_name="utente",
    )
    note = models.TextField(blank=True, verbose_name="nota")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "associazione di riconciliazione"
        verbose_name_plural = "associazioni di riconciliazione"
        ordering = ("kind", "external_value")
        constraints = [
            models.UniqueConstraint(
                fields=("kind", "external_key", "context_year", "context_semester"),
                name="import_mapping_unique_per_context",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="PROGETTO",
                        project__isnull=False,
                        wallet_allocation__isnull=True,
                        canone_subactivity__isnull=True,
                        user__isnull=True,
                    )
                    | models.Q(
                        kind="WALLET_ALLOCATION",
                        project__isnull=True,
                        wallet_allocation__isnull=False,
                        canone_subactivity__isnull=True,
                        user__isnull=True,
                    )
                    | models.Q(
                        kind="CANONE_SUBACTIVITY",
                        project__isnull=True,
                        wallet_allocation__isnull=True,
                        canone_subactivity__isnull=False,
                        user__isnull=True,
                    )
                    | models.Q(
                        kind="COLLABORATORE",
                        project__isnull=True,
                        wallet_allocation__isnull=True,
                        canone_subactivity__isnull=True,
                        user__isnull=False,
                    )
                ),
                name="import_mapping_target_matches_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.external_value} → {self.target_label}"

    @property
    def target_label(self) -> str:
        if (project := self.project) is not None:
            return project.code
        if (allocation := self.wallet_allocation) is not None:
            return str(allocation)
        if (subactivity := self.canone_subactivity) is not None:
            return str(subactivity)
        if (user := self.user) is not None:
            return user.get_full_name() or user.username
        return "—"


class ImportRowSection(models.TextChoices):
    """Sezione alimentata dalla riga, determinata dal foglio di provenienza."""

    PROGETTI = "PROGETTI", "Progetti"
    WALLET = "WALLET", "Wallet"
    ORGANICO = "ORGANICO", "Organico allargato"


class ImportRowStatus(models.TextChoices):
    PRONTA = "PRONTA", "Pronta"
    DA_ASSOCIARE = "DA_ASSOCIARE", "Da associare"
    ERRORE = "ERRORE", "Errore"


class OperationalImportRow(TrackedModel):
    """Riga dell'estratto operativo, come letta e come risolta.

    Conserva sia il dato grezzo dell'Excel sia la destinazione risolta, così che ogni
    movimento creato resti riconducibile al batch e alla cella di origine. Lo staging esiste
    anche prima della conferma: la preview lo salva, senza creare consuntivi.
    """

    batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name="operational_rows",
        verbose_name="batch",
    )
    section = models.CharField(
        max_length=10, choices=ImportRowSection.choices, verbose_name="sezione"
    )
    sheet = models.CharField(max_length=255, verbose_name="foglio")
    excel_row = models.PositiveIntegerField(verbose_name="riga Excel")
    cells = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="riferimenti di cella",
        help_text="Campo → cella in notazione Excel, per ancorare i problemi della console.",
    )

    project_raw = models.CharField(max_length=400, blank=True, verbose_name="progetto nell'Excel")
    subproject_raw = models.CharField(
        max_length=400, blank=True, verbose_name="sottoprogetto nell'Excel"
    )
    collaborator_raw = models.CharField(
        max_length=200, blank=True, verbose_name="collaboratore nell'Excel"
    )
    period = models.DateField(verbose_name="data")
    days = DaysField(verbose_name="giornate")
    note = models.CharField(max_length=300, blank=True, verbose_name="descrizione")

    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="progetto risolto",
    )
    wallet_allocation = models.ForeignKey(
        "wallet.WalletAllocation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="allocazione risolta",
    )
    canone_subactivity = models.ForeignKey(
        "canone.CanoneSubactivity",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="sotto-attività risolta",
    )
    author = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="autore risolto",
    )
    entry = models.ForeignKey(
        "timesheets.TimesheetEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="import_rows",
        verbose_name="consuntivo creato",
    )

    status = models.CharField(
        max_length=12,
        choices=ImportRowStatus.choices,
        default=ImportRowStatus.DA_ASSOCIARE,
        verbose_name="stato",
    )
    detail = models.TextField(blank=True, verbose_name="motivazione")

    class Meta:
        verbose_name = "riga di estratto operativo"
        verbose_name_plural = "righe di estratto operativo"
        ordering = ("section", "excel_row")
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "sheet", "excel_row"),
                name="operational_row_unique_per_batch",
            ),
            models.CheckConstraint(
                condition=models.Q(days__gt=0),
                name="operational_row_days_positive",
            ),
        ]
        indexes = [
            models.Index(fields=("batch", "status")),
            models.Index(fields=("batch", "section")),
        ]

    def __str__(self) -> str:
        return f"{self.sheet}!{self.excel_row} {self.days} gg"

    @property
    def destination_raw(self) -> str:
        """La destinazione come si legge nell'Excel."""
        if self.section == ImportRowSection.PROGETTI:
            return self.project_raw
        if self.section == ImportRowSection.WALLET:
            return f"{self.project_raw} / {self.subproject_raw}".strip(" /")
        return self.subproject_raw

    @property
    def resolved_target(self):
        return self.project or self.wallet_allocation or self.canone_subactivity


class WorkbookSheetSnapshot(TrackedModel):
    """Copia lossless di un foglio contenuto in un seed workbook v2."""

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="workbook_sheets")
    name = models.CharField(max_length=255)
    position = models.PositiveSmallIntegerField()
    state = models.CharField(max_length=20, blank=True)
    dimensions = models.CharField(max_length=50, blank=True)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ("position",)
        constraints = [
            models.UniqueConstraint(fields=("batch", "name"), name="uniq_workbook_sheet_batch")
        ]


class WorkbookDatasetSnapshot(TrackedModel):
    """Dataset tabellare v2, interrogabile senza perdere righe o formule."""

    batch = models.ForeignKey(
        ImportBatch, on_delete=models.CASCADE, related_name="workbook_datasets"
    )
    dataset_id = models.CharField(max_length=255)
    sheet_name = models.CharField(max_length=255)
    source_range = models.CharField(max_length=50)
    row_count = models.PositiveIntegerField()
    column_count = models.PositiveIntegerField()
    columns = models.JSONField(default=list)
    rows = models.JSONField(default=list)

    class Meta:
        ordering = ("dataset_id",)
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "dataset_id"), name="uniq_workbook_dataset_batch"
            )
        ]
