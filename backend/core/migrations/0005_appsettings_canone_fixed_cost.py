from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0004_appsettings_daily_person_cost")]

    operations = [
        migrations.AddField(
            model_name=model_name,
            name="canone_fixed_cost",
            field=models.DecimalField(
                max_digits=12,
                decimal_places=2,
                default=Decimal("0.00"),
                verbose_name="costo forfettario per canone",
                help_text="Importo intero pagato all'attivazione di ciascun canone, indipendente dai consuntivi.",
            ),
        )
        for model_name in ("appsettings", "historicalappsettings")
    ]
