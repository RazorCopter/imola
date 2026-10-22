"""Ripristino esplicito di un dump PostgreSQL compresso creato da manage.py backup."""

from __future__ import annotations

import gzip
import os
import subprocess
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Ripristina un dump .sql.gz su un database vuoto o dedicato."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("dump", type=Path)
        parser.add_argument(
            "--database", default=None, help="Database target (default configurazione)."
        )
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["confirm"]:
            raise CommandError("Specificare --confirm per eseguire il ripristino.")
        dump_path: Path = options["dump"]
        if not dump_path.is_file():
            raise CommandError(f"Dump non trovato: {dump_path}")
        db = settings.DATABASES["default"]
        target = options["database"] or db["NAME"]
        env = {**os.environ, "PGPASSWORD": str(db["PASSWORD"])}
        cmd = [
            "psql",
            "-h",
            str(db["HOST"]),
            "-p",
            str(db["PORT"]),
            "-U",
            str(db["USER"]),
            "-d",
            str(target),
            "-v",
            "ON_ERROR_STOP=1",
        ]
        self.stdout.write(f"Ripristino {dump_path} -> {target}")
        # Decomprimere interamente evita incompatibilità tra GzipFile seekable e
        # subprocess stdin su alcuni runtime/container.
        sql_bytes = gzip.decompress(dump_path.read_bytes())
        sql_text = sql_bytes.decode("utf-8")
        sql_text = "\n".join(
            line for line in sql_text.splitlines() if not line.startswith("SET transaction_timeout")
        )
        proc = subprocess.run(cmd, input=sql_text.encode("utf-8"), env=env, check=False)
        if proc.returncode != 0:
            raise CommandError(f"Ripristino fallito (exit code {proc.returncode}).")
        self.stdout.write(self.style.SUCCESS(f"Ripristino completato su {target}"))
