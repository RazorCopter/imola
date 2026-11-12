from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import connections
from django.http import FileResponse
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from core.roles import is_admin

logger = logging.getLogger(__name__)


class AdministratorOnly(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_admin(request.user))


def _versione(strumento: str) -> str:
    try:
        esito = subprocess.run(
            [strumento, "--version"], capture_output=True, check=True, timeout=10
        )
        return esito.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f"non disponibile ({type(exc).__name__})"


def migrazioni_pendenti() -> list[str]:
    """Migrazioni che il database ripristinato non ha ancora.

    Un backup piu' vecchio del codice riporta indietro lo schema, e l'applicazione si
    rompe dove si aspetta tabelle o colonne che non esistono piu' — con errori che non
    nominano mai il ripristino come causa. Meglio dirlo subito, nella risposta.
    """
    from django.db.migrations.executor import MigrationExecutor

    try:
        executor = MigrationExecutor(connections["default"])
        piano = executor.migration_plan(executor.loader.graph.leaf_nodes())
        return [f"{migrazione.app_label}.{migrazione.name}" for migrazione, _ in piano]
    except Exception as exc:
        logger.warning("Impossibile verificare le migrazioni pendenti: %s", exc)
        return []


def ambiente_diagnostico(backup_dir: Path) -> dict[str, object]:
    """Fotografia dell'ambiente, da registrare quando un ripristino fallisce.

    Le cadute di backup e ripristino hanno due cause ricorrenti e invisibili dall'esterno:
    la cartella dei backup non scrivibile, perche' e' un bind mount di proprieta' di root
    mentre il processo gira con un utente non privilegiato, e lo scarto fra la versione dei
    client PostgreSQL nell'immagine e quella del server. Registrarle qui evita di dover
    chiedere all'operatore di eseguire comandi dentro il container.
    """
    dati: dict[str, object] = {
        "pg_dump": _versione("pg_dump"),
        "pg_restore": _versione("pg_restore"),
        "psql": _versione("psql"),
        "backup_dir": str(backup_dir),
        "backup_dir_esiste": backup_dir.exists(),
    }
    try:
        dati["utente_processo"] = f"uid={os.getuid()} gid={os.getgid()}"  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - su Windows getuid non esiste
        dati["utente_processo"] = "non disponibile su questa piattaforma"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        prova = backup_dir / f".scrittura-{uuid4().hex}"
        prova.touch()
        prova.unlink()
        dati["backup_dir_scrivibile"] = True
    except OSError as exc:
        dati["backup_dir_scrivibile"] = False
        dati["backup_dir_errore"] = f"{type(exc).__name__}: {exc.strerror or exc}"
    try:
        db = settings.DATABASES["default"]
        with connections["default"].cursor() as cursor:
            cursor.execute("SHOW server_version")
            dati["server_version"] = cursor.fetchone()[0]
        dati["database"] = f"{db['HOST']}:{db['PORT'] or 5432}/{db['NAME']}"
    except Exception as exc:
        dati["server_version"] = f"non interrogabile ({type(exc).__name__})"
    return dati


def describe_failure(exc: Exception) -> str:
    """Traduce in una riga il motivo per cui pg_dump, pg_restore o psql hanno ceduto.

    Senza questo l'errore restava invisibile: la vista catturava l'eccezione e rispondeva
    "Ripristino non riuscito" senza lo stderr dello strumento, che è il solo posto dove
    sta la causa. Le due cadute tipiche sono i permessi sulla cartella dei backup, che è
    un bind mount di proprietà di root mentre il processo gira con un utente non
    privilegiato, e lo scarto di versione fra client e server PostgreSQL.
    """
    if isinstance(exc, subprocess.CalledProcessError):
        stderr = exc.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        comando = exc.cmd[0] if isinstance(exc.cmd, (list, tuple)) and exc.cmd else "comando"
        dettaglio = " ".join((stderr or "").split())[:400] or "nessun dettaglio"
        return f"{comando} è terminato con codice {exc.returncode}: {dettaglio}"
    if isinstance(exc, FileNotFoundError):
        return (
            f"{exc.filename or 'strumento'} non trovato: nell'immagine manca il client "
            "PostgreSQL (pacchetto postgresql-client)."
        )
    if isinstance(exc, PermissionError):
        return (
            f"permesso negato su {exc.filename or 'un percorso'}: la cartella dei backup "
            "non è scrivibile dall'utente del processo."
        )
    if isinstance(exc, OSError):
        return f"errore di sistema su {exc.filename or 'un percorso'}: {exc.strerror or exc}"
    return str(exc)


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


class EmptyRestoreError(RuntimeError):
    """pg_restore non ha prodotto istruzioni: lo schema non va distrutto."""


def restore_dump(path, database=None):
    """Riscrive il database con il contenuto del dump, in una sola transazione.

    Due accortezze che non sono dettagli:

    `--file` punta a un percorso reale e non a `/dev/stdout`. Su Linux i due casi si
    equivalgono, su Windows no: `pg_restore.exe` non conosce `/dev/stdout` e scrive in un
    file chiamato così, lasciando vuoto il flusso. Siccome subito dopo si esegue
    `DROP SCHEMA public CASCADE`, il risultato era un database svuotato e non ripristinato.

    Di qui il secondo controllo: se l'SQL generato non contiene istruzioni, si solleva
    `EmptyRestoreError` **prima** di toccare lo schema. Un ripristino che non ripristina
    deve fallire, non cancellare.
    """
    args, env = database_config(database)
    with tempfile.TemporaryDirectory() as temporary:
        generato = Path(temporary) / "restore.sql"
        filtrato = Path(temporary) / "apply.sql"
        subprocess.run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(generato),
                str(path),
            ],
            stderr=subprocess.PIPE,
            check=True,
        )
        with generato.open("rb") as raw, filtrato.open("wb") as sql:
            sql.write(b"DROP SCHEMA public CASCADE;\nCREATE SCHEMA public;\n")
            istruzioni = 0
            for line in raw:
                # `transaction_timeout` esiste solo da PostgreSQL 17: un dump preso con
                # un client 17 non si applica a un server precedente senza togliere questa.
                if line.startswith(b"SET transaction_timeout"):
                    continue
                sql.write(line)
                spogliata = line.strip()
                if spogliata and not spogliata.startswith(b"--"):
                    istruzioni += 1
        if istruzioni == 0:
            raise EmptyRestoreError(
                "pg_restore non ha prodotto alcuna istruzione dal backup: "
                "ripristino interrotto senza toccare il database."
            )
        with filtrato.open("rb") as sql:
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
        except (OSError, subprocess.SubprocessError) as exc:
            file.close()
            motivo = describe_failure(exc)
            logger.error(
                "Backup del database non riuscito: %s | ambiente: %s",
                motivo,
                ambiente_diagnostico(Path(os.environ.get("BACKUP_DIR", "backups"))),
                exc_info=True,
            )
            return Response({"detail": f"Creazione del backup non riuscita: {motivo}"}, status=500)


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
        fase = "preparazione"
        try:
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "upload.dump"
                with path.open("wb") as handle:
                    for chunk in uploaded.chunks():
                        handle.write(chunk)
                fase = "lettura del backup caricato"
                validate_dump(path)
                fase = f"copia preventiva in {backup_dir}"
                backup_dir.mkdir(parents=True, exist_ok=True)
                previous = backup_dir / f"pre-restore-{uuid4().hex}.dump"
                create_dump(previous)
                fase = "ripristino"
                restore_dump(path)
        except (OSError, subprocess.SubprocessError, EmptyRestoreError) as exc:
            motivo = describe_failure(exc)
            logger.error(
                "Ripristino del database non riuscito durante %s: %s | ambiente: %s",
                fase,
                motivo,
                ambiente_diagnostico(backup_dir),
                exc_info=True,
            )
            return Response(
                {
                    "detail": (
                        f"Ripristino non riuscito durante {fase}: {motivo} "
                        "Le modifiche sono state annullate; se creata, la copia preventiva "
                        "resta sul server."
                    )
                },
                status=400,
            )
        pendenti = migrazioni_pendenti()
        detail = (
            "Database ripristinato. Potrebbe essere necessario effettuare " "di nuovo l'accesso."
        )
        if pendenti:
            logger.warning(
                "Il backup ripristinato precede %d migrazioni: %s",
                len(pendenti),
                ", ".join(pendenti),
            )
            detail += (
                f" Attenzione: il backup precede {len(pendenti)} migrazioni "
                f"({', '.join(pendenti)}). Lo schema e' tornato indietro e "
                "l'applicazione non funziona correttamente finche' non si esegue "
                "'manage.py migrate'."
            )
        return Response(
            {
                "detail": detail,
                "backup_preventivo": previous.name,
                "migrazioni_da_applicare": pendenti,
            }
        )
