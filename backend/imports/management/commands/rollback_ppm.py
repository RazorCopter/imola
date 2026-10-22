from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from importers.ppm import rollback_ppm


class Command(BaseCommand):
    help = "Rollback append-only di un batch PPM tramite movimenti di storno."

    def add_arguments(self, parser) -> None:
        parser.add_argument("batch_id")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["confirm"]:
            raise CommandError("Rollback non eseguito: ripetere con --confirm.")
        try:
            result = rollback_ppm(options["batch_id"])
        except (ValueError, LookupError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
