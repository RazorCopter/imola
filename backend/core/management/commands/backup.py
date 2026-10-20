"""Dump del database e dei media, pensato per il cron di Synology."""

from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Esegue il backup di PostgreSQL (pg_dump) e della cartella media."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--output-dir",
            default=None,
            help="Cartella di destinazione (default BACKUP_DIR o ./backups).",
        )
        parser.add_argument(
            "--keep", type=int, default=14, help="Numero di backup da conservare (default 14)."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        import os

        out_dir = Path(options["output_dir"] or os.environ.get("BACKUP_DIR", "backups"))
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        db = settings.DATABASES["default"]

        dump_path = out_dir / f"db-{stamp}.sql.gz"
        env = {**os.environ, "PGPASSWORD": str(db["PASSWORD"])}
        self.stdout.write(f"pg_dump -> {dump_path}")
        with dump_path.open("wb") as handle:
            pg = subprocess.Popen(
                [
                    "pg_dump",
                    "-h",
                    str(db["HOST"]),
                    "-p",
                    str(db["PORT"]),
                    "-U",
                    str(db["USER"]),
                    "-d",
                    str(db["NAME"]),
                    "--no-owner",
                ],
                stdout=subprocess.PIPE,
                env=env,
            )
            gzip_proc = subprocess.Popen(["gzip", "-9"], stdin=pg.stdout, stdout=handle)
            if pg.stdout:
                pg.stdout.close()
            gzip_proc.communicate()
            if pg.wait() != 0 or gzip_proc.returncode != 0:
                raise CommandError("pg_dump non è andato a buon fine.")

        media_root = Path(settings.MEDIA_ROOT)
        if media_root.is_dir():
            media_path = out_dir / f"media-{stamp}.tar.gz"
            self.stdout.write(f"media -> {media_path}")
            with tarfile.open(media_path, "w:gz") as tar:
                tar.add(media_root, arcname="media")

        keep = options["keep"]
        for prefix in ("db-", "media-"):
            files = sorted(out_dir.glob(f"{prefix}*"), reverse=True)
            for stale in files[keep:]:
                stale.unlink(missing_ok=True)
                self.stdout.write(f"rimosso vecchio backup: {stale.name}")

        self.stdout.write(self.style.SUCCESS(f"Backup completato in {out_dir}"))
