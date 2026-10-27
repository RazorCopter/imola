from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0004_project_closed_workbook_seed_trigger")]

    operations = [
        migrations.AddField(
            model_name="billingmilestone",
            name="schedule_slot",
            field=models.CharField(
                blank=True,
                choices=[("START", "Avvio progetto"), ("END", "Fine progetto")],
                max_length=10,
                verbose_name="posizione nel piano automatico",
            ),
        ),
        migrations.AddField(
            model_name="historicalbillingmilestone",
            name="schedule_slot",
            field=models.CharField(
                blank=True,
                choices=[("START", "Avvio progetto"), ("END", "Fine progetto")],
                max_length=10,
                verbose_name="posizione nel piano automatico",
            ),
        ),
        migrations.AddConstraint(
            model_name="billingmilestone",
            constraint=models.UniqueConstraint(
                condition=~models.Q(schedule_slot=""),
                fields=("project", "schedule_slot"),
                name="unique_project_billing_schedule_slot",
            ),
        ),
    ]
