"""Importa un seed JSON validato, in simulazione oppure applicandolo."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from importers.batch import ImportConflictError, ImportExecutionError, orchestrate_seed
from importers.schema import SeedValidationError


class Command(BaseCommand):
    help = "Valida e importa un seed JSON (default: apply; usare --dry-run per simulare)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("file", help="Percorso del file seed JSON.")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--dry-run",
            action="store_true",
            help="Esegue l'import e annulla ogni scrittura, mostrando il report.",
        )
        mode.add_argument(
            "--apply",
            action="store_true",
            help="Applica esplicitamente l'import (comportamento predefinito).",
        )
        parser.add_argument(
            "--schema",
            default=None,
            help="Percorso alternativo di seed_schema_v1.json.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Emette il report strutturato JSON invece di quello testuale.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            result = orchestrate_seed(
                options["file"],
                dry_run=options["dry_run"],
                schema_path=options["schema"],
            )
        except FileNotFoundError as exc:
            raise CommandError(f"File non trovato: {exc.filename or options['file']}") from exc
        except PermissionError as exc:
            raise CommandError(f"File non leggibile: {exc.filename or options['file']}") from exc
        except UnicodeError as exc:
            raise CommandError(str(exc)) from exc
        except SeedValidationError as exc:
            details = "\n".join(f"  - {problem}" for problem in exc.problems)
            message = str(exc) if not details else f"{exc}\n{details}"
            raise CommandError(message) from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        except ImportConflictError as exc:
            raise CommandError(f"Conflitto di import: {exc}") from exc
        except ImportExecutionError as exc:
            raise CommandError(f"Import fallito (batch {exc.batch.pk}): {exc}") from exc

        if options["json_output"]:
            self.stdout.write(json.dumps(result.report.as_dict(), ensure_ascii=False, indent=2))
        else:
            self.stdout.write(result.report.render_text())
        status_output = self.stderr if options["json_output"] else self.stdout
        if result.batch is not None:
            status_output.write(self.style.SUCCESS(f"Batch applicato: {result.batch.pk}"))
        elif options["dry_run"]:
            status_output.write(
                self.style.WARNING("Simulazione completata: nessun dato persistito.")
            )
