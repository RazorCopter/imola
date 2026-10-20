"""Crea i gruppi dei ruoli e la riga delle impostazioni globali. Idempotente."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from core import roles
from core.models import AppSettings


class Command(BaseCommand):
    help = "Crea i gruppi dei ruoli applicativi e le impostazioni globali se mancanti."

    def handle(self, *args: Any, **options: Any) -> None:
        groups = roles.ensure_groups()
        self.stdout.write(f"Gruppi disponibili: {', '.join(group.name for group in groups)}")
        settings_obj = AppSettings.get_solo()
        self.stdout.write(
            "Impostazioni: "
            f"ore/giornata={settings_obj.hours_per_day}, "
            f"tolleranza={settings_obj.reconciliation_tolerance_days} gg, "
            f"validita residuo={settings_obj.residual_years_after_closure} anno/i"
        )
        self.stdout.write(self.style.SUCCESS("Bootstrap completato."))
