from django.db import migrations

SUPPLIER_OPERATIONAL_CAPABILITIES = (
    "projects.create",
    "timesheets.create",
    "timesheets.edit",
    "wallet.edit",
    "canone.manage",
)


def enable_supplier_operations(apps, schema_editor):
    overrides = apps.get_model("core", "RoleCapabilityOverride")
    for capability in SUPPLIER_OPERATIONAL_CAPABILITIES:
        overrides.objects.using(schema_editor.connection.alias).update_or_create(
            role="fornitore", capability=capability, defaults={"enabled": True}
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0005_appsettings_canone_fixed_cost")]
    # These are persistent role settings, not disposable rows on schema rollback.
    operations = [migrations.RunPython(enable_supplier_operations, migrations.RunPython.noop)]
