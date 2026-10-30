"""Crea i lotti wallet mancanti per i progetti gia chiusi. Idempotente.

Serve una volta sola, sui database nati prima che la chiusura di un progetto creasse il
lotto: senza lotto la capienza del wallet appare nel bilancio ma `reserve_fifo` non trova
fonti da cui prelevare e ogni nuovo utilizzo viene rifiutato.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from projects.models import ContractType, Project, TimesheetStatus
from wallet.services import ensure_source_lot, wallet_capacity_of


class Command(BaseCommand):
    help = "Materializza i lotti wallet dei progetti chiusi con residuo ancora spendibile."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Elenca i lotti che verrebbero creati senza scrivere nulla.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        projects = (
            Project.objects.filter(
                timesheet_status=TimesheetStatus.CHIUSO,
                actual_closure_date__isnull=False,
            )
            .exclude(contract_type=ContractType.CANONE)
            .order_by("actual_closure_date", "code")
        )
        created = 0
        skipped = 0
        with transaction.atomic():
            for project in projects:
                had_lot = project.wallet_source_lots.exists()
                if dry_run:
                    capacity = wallet_capacity_of(project)
                    if had_lot or capacity <= 0:
                        skipped += 1
                        continue
                    created += 1
                    self.stdout.write(f"{project.code}: creerebbe un lotto di {capacity} gg")
                    continue
                lot = ensure_source_lot(project)
                if lot is None or had_lot:
                    skipped += 1
                    continue
                created += 1
                self.stdout.write(f"{project.code}: lotto di {lot.capacity_days} gg")
            if dry_run:
                transaction.set_rollback(True)
        suffix = " (dry-run, niente scritto)" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(f"Lotti creati: {created}; invariati: {skipped}{suffix}")
        )
