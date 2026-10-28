from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.http import FileResponse
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from core.roles import is_admin


class AdministratorOnly(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_admin(request.user))


def database_config(database=None):
    db = settings.DATABASES["default"]
    args = [
        "-h",
        str(db["HOST"]),
        "-p",
        str(db["PORT"] or 5432),
        "-U",
        str(db["USER"]),
        "-d",
        str(database or db["NAME"]),
    ]
    return args, {**os.environ, "PGPASSWORD": str(db["PASSWORD"])}


def create_dump(path, database=None):
    args, env = database_config(database)
    subprocess.run(
        ["pg_dump", *args, "--format=custom", "--no-owner", "--no-privileges", "--file", str(path)],
        env=env,
        check=True,
        capture_output=True,
    )


def validate_dump(path):
    subprocess.run(["pg_restore", "--list", str(path)], check=True, capture_output=True)


def restore_dump(path, database=None):
    args, env = database_config(database)
    with tempfile.TemporaryFile(mode="w+b") as raw, tempfile.TemporaryFile(mode="w+b") as sql:
        subprocess.run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--file",
                "/dev/stdout",
                str(path),
            ],
            stdout=raw,
            stderr=subprocess.PIPE,
            check=True,
        )
        raw.seek(0)
        sql.write(b"DROP SCHEMA public CASCADE;\nCREATE SCHEMA public;\n")
        for line in raw:
            if not line.startswith(b"SET transaction_timeout"):
                sql.write(line)
        sql.seek(0)
        subprocess.run(
            ["psql", *args, "--single-transaction", "--set", "ON_ERROR_STOP=1"],
            stdin=sql,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )


class DatabaseBackupView(APIView):
    permission_classes = [AdministratorOnly]

    def get(self, request):
        file = tempfile.TemporaryFile(mode="w+b")
        try:
            args, env = database_config()
            subprocess.run(
                ["pg_dump", *args, "--format=custom", "--no-owner", "--no-privileges"],
                stdout=file,
                stderr=subprocess.PIPE,
                env=env,
                check=True,
            )
            file.seek(0)
            return FileResponse(
                file,
                as_attachment=True,
                filename="imola-database.dump",
                content_type="application/octet-stream",
            )
        except (OSError, subprocess.SubprocessError):
            file.close()
            return Response({"detail": "Creazione del backup non riuscita."}, status=500)


class DatabaseRestoreView(APIView):
    permission_classes = [AdministratorOnly]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded or uploaded.size > 28 * 1024 * 1024:
            return Response({"detail": "Seleziona un backup valido di massimo 28 MB."}, status=400)
        if request.data.get("confirm") != "RIPRISTINA":
            return Response({"detail": "Scrivi RIPRISTINA per confermare."}, status=400)
        backup_dir = Path(os.environ.get("BACKUP_DIR", "backups"))
        try:
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "upload.dump"
                with path.open("wb") as handle:
                    for chunk in uploaded.chunks():
                        handle.write(chunk)
                validate_dump(path)
                backup_dir.mkdir(parents=True, exist_ok=True)
                previous = backup_dir / f"pre-restore-{uuid4().hex}.dump"
                create_dump(previous)
                restore_dump(path)
        except (OSError, subprocess.SubprocessError):
            return Response(
                {
                    "detail": "Ripristino non riuscito. Le modifiche sono state annullate. "
                    "Se creata, la copia preventiva resta sul server."
                },
                status=400,
            )
        return Response(
            {
                "detail": "Database ripristinato. Potrebbe essere necessario "
                "effettuare nuovamente l'accesso.",
                "backup_preventivo": previous.name,
            }
        )
