from django.db import migrations, models
import django.db.models.deletion


def populate_names(apps, schema_editor):
    Canone = apps.get_model("canone", "Canone")
    for canone in Canone.objects.select_related("project"):
        base = (canone.project.title or canone.project.code) if canone.project_id else "Organico Allargato"
        canone.name = base[:200]
        canone.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [("canone", "0002_canone_periodicity_subactivity_reserved_days")]
    operations = [
        migrations.AddField(model_name="canone", name="name", field=models.CharField(blank=True, max_length=200, verbose_name="nome canone")),
        migrations.AddField(model_name="historicalcanone", name="name", field=models.CharField(blank=True, max_length=200, verbose_name="nome canone")),
        migrations.AddField(model_name="canonesubactivity", name="start_date", field=models.DateField(blank=True, null=True, verbose_name="data inizio")),
        migrations.AddField(model_name="canonesubactivity", name="end_date", field=models.DateField(blank=True, null=True, verbose_name="data fine")),
        migrations.AddField(model_name="historicalcanonesubactivity", name="start_date", field=models.DateField(blank=True, null=True, verbose_name="data inizio")),
        migrations.AddField(model_name="historicalcanonesubactivity", name="end_date", field=models.DateField(blank=True, null=True, verbose_name="data fine")),
        migrations.RunPython(populate_names, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="canone", name="canone_unique_semester"),
        migrations.AlterField(model_name="canone", name="project", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="canoni", to="projects.project", verbose_name="progetto")),
        migrations.AlterField(model_name="historicalcanone", name="project", field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name="+", to="projects.project", verbose_name="progetto")),
        migrations.AddConstraint(model_name="canone", constraint=models.UniqueConstraint(fields=("name", "semester"), name="canone_unique_name_period")),
    ]
