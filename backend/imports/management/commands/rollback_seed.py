"""Annulla in sicurezza un batch seed JSON applicato."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from importers.rollback import RollbackError, rollback_seed_batch


class Command(BaseCommand):
    help = "Annulla un batch seed applicato, eliminando solo i record creati dal batch."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("batch_id", help="UUID del batch seed da annullare.")
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Conferma esplicitamente l'operazione distruttiva.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Emette l'esito strutturato JSON invece di quello testuale.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["confirm"]:
            raise CommandError(
                "Rollback non eseguito: ripetere il comando con --confirm per confermare."
            )
        try:
            result = rollback_seed_batch(options["batch_id"])
        except RollbackError as exc:
            raise CommandError(str(exc)) from exc

        if options["json_output"]:
            self.stdout.write(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True))
            return

        self.stdout.write(self.style.SUCCESS(f"Batch {result.batch_id} annullato."))
        self.stdout.write(f"Record eliminati: {result.deleted_total}")
        for entity, count in result.deleted.items():
            self.stdout.write(f"- {entity}: {count}")
