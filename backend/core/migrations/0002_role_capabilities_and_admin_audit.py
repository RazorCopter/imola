from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RoleCapabilityOverride",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("role", models.CharField(max_length=64)),
                ("capability", models.CharField(max_length=64)),
                ("enabled", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("role", "capability")},
        ),
        migrations.CreateModel(
            name="AdminAuditEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("actor_username", models.CharField(blank=True, max_length=150)),
                ("action", models.CharField(max_length=64)),
                ("target_type", models.CharField(max_length=32)),
                ("target_id", models.CharField(blank=True, max_length=128)),
                ("target_label", models.CharField(blank=True, max_length=150)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="admin_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddConstraint(
            model_name="rolecapabilityoverride",
            constraint=models.UniqueConstraint(
                fields=("role", "capability"), name="core_unique_role_capability"
            ),
        ),
    ]
