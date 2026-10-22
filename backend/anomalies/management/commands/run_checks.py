from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from anomalies.runner import run_checks
from domain.checks import RULES


class Command(BaseCommand):
    help = "Esegue le regole automatiche di controllo e aggiorna l'inbox anomalie."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--rule", action="append", choices=sorted(RULES))

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            report = run_checks(options.get("rule"))
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        )
