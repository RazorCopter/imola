from django.db import migrations, models
from django.db.models import Sum

import core.fields


def backfill_reserved_days(apps, schema_editor):
    Subactivity = apps.get_model("canone", "CanoneSubactivity")
    for row in Subactivity.objects.all():
        consumed = row.timesheet_entries.aggregate(total=Sum("days"))["total"] or 0
        row.reserved_days = max(row.quarter_estimate_days or 0, consumed)
        row.save(update_fields=["reserved_days"])


class Migration(migrations.Migration):
    dependencies = [("canone", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="canone",
            name="periodicity",
            field=models.CharField(
                choices=[("TRIMESTRALE", "Trimestrale"), ("SEMESTRALE", "Semestrale")],
                default="SEMESTRALE",
                max_length=12,
                verbose_name="periodicità",
            ),
        ),
        migrations.AddField(
            model_name="historicalcanone",
            name="periodicity",
            field=models.CharField(
                choices=[("TRIMESTRALE", "Trimestrale"), ("SEMESTRALE", "Semestrale")],
                default="SEMESTRALE",
                max_length=12,
                verbose_name="periodicità",
            ),
        ),
        migrations.AddField(
            model_name="canonesubactivity",
            name="reserved_days",
            field=core.fields.DaysField(default=0, verbose_name="giornate riservate"),
        ),
        migrations.AddField(
            model_name="historicalcanonesubactivity",
            name="reserved_days",
            field=core.fields.DaysField(default=0, verbose_name="giornate riservate"),
        ),
        migrations.RunPython(backfill_reserved_days, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="canonesubactivity",
            constraint=models.CheckConstraint(
                condition=models.Q(reserved_days__gte=0),
                name="canone_subactivity_reserved_nonnegative",
            ),
        ),
    ]
