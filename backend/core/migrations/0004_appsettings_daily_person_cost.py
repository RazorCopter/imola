from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0003_canone_manage_capability")]

    operations = [
        migrations.AddField(
            model_name="appsettings",
            name="daily_person_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Valore globale corrente; non è storicizzato per periodo o fornitore.",
                max_digits=12,
                verbose_name="costo globale per giornata uomo",
            ),
        ),
        migrations.AddField(
            model_name="historicalappsettings",
            name="daily_person_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Valore globale corrente; non è storicizzato per periodo o fornitore.",
                max_digits=12,
                verbose_name="costo globale per giornata uomo",
            ),
        ),
    ]
