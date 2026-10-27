from django.db import migrations

CANONE_MANAGER_ROLES = ("admin", "responsabile_bmed")


def add_canone_manage(apps, schema_editor):
    RoleCapabilityOverride = apps.get_model("core", "RoleCapabilityOverride")
    for role in CANONE_MANAGER_ROLES:
        RoleCapabilityOverride.objects.update_or_create(
            role=role,
            capability="canone.manage",
            defaults={"enabled": True},
        )


def remove_canone_manage(apps, schema_editor):
    RoleCapabilityOverride = apps.get_model("core", "RoleCapabilityOverride")
    RoleCapabilityOverride.objects.filter(
        role__in=CANONE_MANAGER_ROLES,
        capability="canone.manage",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0002_role_capabilities_and_admin_audit")]
    operations = [migrations.RunPython(add_canone_manage, remove_canone_manage)]
