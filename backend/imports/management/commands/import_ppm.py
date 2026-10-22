from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from importers.ppm import PpmParseError, apply_ppm, dry_run_ppm


class Command(BaseCommand):
    help = "Esegue dry-run o applicazione append-only di un estratto PPM Excel/PDF."

    def add_arguments(self, parser) -> None:
        parser.add_argument("file", type=Path)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            report = (
                apply_ppm(options["file"]) if options["apply"] else dry_run_ppm(options["file"])
            )
        except (PpmParseError, ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        )
