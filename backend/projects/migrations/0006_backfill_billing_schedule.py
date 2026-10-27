from calendar import monthrange

from django.db import migrations


def backfill_billing_schedule(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    BillingMilestone = apps.get_model("projects", "BillingMilestone")
    statuses = {
        "DA_FATTURARE": ("PIANIFICATA", "PIANIFICATA"),
        "PARZIALE": ("FATTURATA", "PIANIFICATA"),
        "TOTALE": ("FATTURATA", "FATTURATA"),
        "NON_FATTURABILE": ("ANNULLATA", "ANNULLATA"),
        "DA_VERIFICARE": ("DA_VERIFICARE", "DA_VERIFICARE"),
    }
    for project in Project.objects.exclude(start_date=None).exclude(planned_end_date=None):
        start_status, end_status = statuses[project.billing_status]
        for slot, source_date, status in (
            ("START", project.start_date, start_status),
            ("END", project.planned_end_date, end_status),
        ):
            planned_date = source_date.replace(
                day=monthrange(source_date.year, source_date.month)[1]
            )
            BillingMilestone.objects.update_or_create(
                project=project,
                schedule_slot=slot,
                defaults={
                    "planned_date": planned_date,
                    "actual_date": planned_date if status == "FATTURATA" else None,
                    "status": status,
                },
            )


def remove_backfilled_schedule(apps, schema_editor):
    BillingMilestone = apps.get_model("projects", "BillingMilestone")
    BillingMilestone.objects.exclude(schedule_slot="").delete()


class Migration(migrations.Migration):
    dependencies = [("projects", "0005_billingmilestone_schedule_slot")]

    operations = [
        migrations.RunPython(backfill_billing_schedule, remove_backfilled_schedule),
    ]
