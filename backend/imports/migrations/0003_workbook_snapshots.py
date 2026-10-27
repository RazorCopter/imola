import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("imports", "0002_historicalimportbatch_content_hash_and_more")]

    operations = [
        migrations.AlterField(
            model_name="importbatch",
            name="kind",
            field=models.CharField(
                choices=[
                    ("SEED_JSON", "Seed JSON"),
                    ("WORKBOOK_JSON", "Workbook JSON completo"),
                    ("PPM_XLSX", "Estratto PPM (Excel)"),
                    ("PPM_PDF", "Estratto PPM (PDF)"),
                    ("EXCEL_LEGACY", "Excel storico"),
                ],
                max_length=20,
                verbose_name="tipo",
            ),
        ),
        migrations.AlterField(
            model_name="historicalimportbatch",
            name="kind",
            field=models.CharField(
                choices=[
                    ("SEED_JSON", "Seed JSON"),
                    ("WORKBOOK_JSON", "Workbook JSON completo"),
                    ("PPM_XLSX", "Estratto PPM (Excel)"),
                    ("PPM_PDF", "Estratto PPM (PDF)"),
                    ("EXCEL_LEGACY", "Excel storico"),
                ],
                max_length=20,
                verbose_name="tipo",
            ),
        ),
        migrations.CreateModel(
            name="WorkbookSheetSnapshot",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField(default=1, editable=False)),
                ("name", models.CharField(max_length=255)),
                ("position", models.PositiveSmallIntegerField()),
                ("state", models.CharField(blank=True, max_length=20)),
                ("dimensions", models.CharField(blank=True, max_length=50)),
                ("payload", models.JSONField(default=dict)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="auth.user",
                        verbose_name="creato da",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="auth.user",
                        verbose_name="modificato da",
                    ),
                ),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workbook_sheets",
                        to="imports.importbatch",
                    ),
                ),
            ],
            options={"ordering": ("position",)},
        ),
        migrations.CreateModel(
            name="WorkbookDatasetSnapshot",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField(default=1, editable=False)),
                ("dataset_id", models.CharField(max_length=255)),
                ("sheet_name", models.CharField(max_length=255)),
                ("source_range", models.CharField(max_length=50)),
                ("row_count", models.PositiveIntegerField()),
                ("column_count", models.PositiveIntegerField()),
                ("columns", models.JSONField(default=list)),
                ("rows", models.JSONField(default=list)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="auth.user",
                        verbose_name="creato da",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="auth.user",
                        verbose_name="modificato da",
                    ),
                ),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workbook_datasets",
                        to="imports.importbatch",
                    ),
                ),
            ],
            options={"ordering": ("dataset_id",)},
        ),
        migrations.AddConstraint(
            model_name="workbooksheetsnapshot",
            constraint=models.UniqueConstraint(
                fields=("batch", "name"), name="uniq_workbook_sheet_batch"
            ),
        ),
        migrations.AddConstraint(
            model_name="workbookdatasetsnapshot",
            constraint=models.UniqueConstraint(
                fields=("batch", "dataset_id"), name="uniq_workbook_dataset_batch"
            ),
        ),
    ]
