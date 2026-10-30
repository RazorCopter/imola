"""Allinea i lotti wallet dei progetti gia chiusi. Idempotente.

Serve sui database nati prima che la chiusura di un progetto creasse il lotto: senza lotto
la capienza del wallet appare nel bilancio ma `reserve_fifo` non trova fonti da cui
prelevare e ogni nuovo utilizzo viene rifiutato.

Il dry-run esegue la stessa logica della scrittura e poi annulla la transazione, quindi
elenca davvero tutto quello che cambierebbe: lotti da creare, ma anche lotti da spostare
nell'anno wallet che li spende o da riallineare in capienza. Riportare solo le creazioni
farebbe passare per "invariato" un lotto finito nell'anno sbagliato, cioe invisibile.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from projects.models import ContractType, Project, TimesheetStatus
from wallet.services import ensure_source_lot, wallet_capacity_of


class Command(BaseCommand):
    help = "Allinea i lotti wallet dei progetti chiusi con residuo ancora spendibile."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Elenca le modifiche senza scrivere nulla.",
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
        changed = 0
        unchanged = 0
        with transaction.atomic():
            for project in projects:
                before = project.wallet_source_lots.select_related("wallet_year").first()
                snapshot = (
                    None
                    if before is None
                    else (before.wallet_year.year, before.capacity_days, before.status)
                )
                lot = ensure_source_lot(project)
                if lot is None:
                    unchanged += 1
                    capacity = wallet_capacity_of(project)
                    if capacity > 0:
                        # Residuo spendibile che non diventa capienza: di norma e scaduto.
                        self.stdout.write(
                            f"{project.code}: {capacity} gg non conferibili "
                            f"(chiuso il {project.actual_closure_date}, residuo non piu valido)"
                        )
                    continue
                if snapshot is None:
                    created += 1
                    self.stdout.write(
                        f"{project.code}: nuovo lotto di {lot.capacity_days} gg "
                        f"nel wallet {lot.wallet_year.year}"
                    )
                    continue
                lot.refresh_from_db()
                notes = []
                if snapshot[0] != lot.wallet_year.year:
                    notes.append(f"spostato dal wallet {snapshot[0]} al {lot.wallet_year.year}")
                if snapshot[1] != lot.capacity_days:
                    notes.append(f"capienza da {snapshot[1]} a {lot.capacity_days} gg")
                if notes:
                    changed += 1
                    self.stdout.write(f"{project.code}: " + "; ".join(notes))
                else:
                    unchanged += 1
                    self.stdout.write(
                        f"{project.code}: gia a posto "
                        f"({lot.capacity_days} gg nel wallet {lot.wallet_year.year})"
                    )
            if dry_run:
                transaction.set_rollback(True)
        suffix = " (dry-run, niente scritto)" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Lotti creati: {created}; corretti: {changed}; invariati: {unchanged}{suffix}"
            )
        )
