from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("timesheets", "0002_append_only_trigger")]

    operations = [
        migrations.AlterField(
            model_name="timesheetentry",
            name="period",
            field=models.DateField(
                help_text="Data di competenza del consuntivo.", verbose_name="data"
            ),
        ),
        migrations.AlterField(
            model_name="historicaltimesheetentry",
            name="period",
            field=models.DateField(
                help_text="Data di competenza del consuntivo.", verbose_name="data"
            ),
        ),
    ]
