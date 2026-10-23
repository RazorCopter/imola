"""API amministrative per import, storico e gestione ruoli."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import UploadedFile
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core import roles
from core.permissions import IsAdmin
from importers.batch import apply_seed, default_schema_path, dry_run_seed
from importers.ppm import apply_ppm, dry_run_ppm
from importers.schema import load_schema, validate_seed
from imports.models import ImportBatch

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _report_payload(report) -> dict:
    if hasattr(report, "as_dict"):
        return report.as_dict()
    return {
        "source_filename": report.source_filename,
        "recognized": report.recognized,
        "unmatched": report.unmatched,
        "totals": report.totals,
        "balanced": report.balanced,
        "entries_created": report.entries_created,
        "rows": report.rows,
    }


def _uploaded_bytes(request) -> tuple[UploadedFile, bytes] | tuple[None, None]:
    uploaded = request.FILES.get("file")
    if uploaded is None or uploaded.size > MAX_UPLOAD_BYTES:
        return None, None
    return uploaded, uploaded.read()


class SeedImportView(APIView):
    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded, raw = _uploaded_bytes(request)
        if uploaded is None or raw is None:
            return Response(
                {"detail": "File JSON mancante o superiore a 10 MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            source_filename = uploaded.name or "seed.json"
            text = raw.decode("utf-8")
            payload = validate_seed(text, load_schema(default_schema_path()))
            content_hash = hashlib.sha256(raw).hexdigest()
            if request.data.get("apply") == "true":
                if request.data.get("confirmation_hash") != content_hash:
                    return Response(
                        {"detail": "Conferma non valida: ripetere il dry-run sullo stesso file."},
                        status=status.HTTP_409_CONFLICT,
                    )
                result = apply_seed(
                    payload,
                    source_filename=source_filename,
                    content_hash=content_hash,
                )
            else:
                result = dry_run_seed(payload, source_filename=source_filename)
        except (UnicodeDecodeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "mode": "apply" if request.data.get("apply") == "true" else "dry-run",
                "confirmation_hash": content_hash,
                "batch_id": result.batch.id if result.batch else None,
                "report": _report_payload(result.report),
            }
        )


class PpmImportView(APIView):
    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded, raw = _uploaded_bytes(request)
        if uploaded is None or raw is None:
            return Response(
                {"detail": "File PPM mancante o superiore a 10 MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        suffix = Path(uploaded.name or "upload").suffix.lower()
        if suffix not in {".xlsx", ".pdf"}:
            return Response(
                {"detail": "Formato PPM non supportato: usare .xlsx o .pdf."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content_hash = hashlib.sha256(raw).hexdigest()
        if (
            request.data.get("apply") == "true"
            and request.data.get("confirmation_hash") != content_hash
        ):
            return Response(
                {"detail": "Conferma non valida: ripetere il dry-run sullo stesso file."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix) as temporary:
                temporary.write(raw)
                temporary.flush()
                report = (
                    apply_ppm(temporary.name, user=request.user)
                    if request.data.get("apply") == "true"
                    else dry_run_ppm(temporary.name)
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "mode": "apply" if request.data.get("apply") == "true" else "dry-run",
                "confirmation_hash": content_hash,
                "report": _report_payload(report),
            }
        )


class ImportHistoryView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        rows = ImportBatch.objects.order_by("-created_at")[:100]
        return Response(
            {
                "results": [
                    {
                        "id": row.id,
                        "kind": row.kind,
                        "status": row.status,
                        "source_filename": row.source_filename,
                        "created_at": row.created_at,
                        "report": row.report,
                    }
                    for row in rows
                ]
            }
        )


class UserRolesView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(
            {
                "roles": list(roles.ALL_ROLES),
                "results": [
                    {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "roles": list(user.groups.values_list("name", flat=True)),
                    }
                    for user in User.objects.prefetch_related("groups").order_by("username")
                ],
            }
        )

    def post(self, request):
        user = User.objects.filter(pk=request.data.get("user_id")).first()
        role = str(request.data.get("role", ""))
        if user is None or role not in roles.ALL_ROLES:
            return Response({"detail": "Utente o ruolo non valido."}, status=400)
        roles.ensure_groups()
        user.groups.set([Group.objects.get(name=role)])
        return Response({"id": user.id, "roles": [role]})
