"""API dell'importazione settimanale e della sezione Riconciliazione.

Contratto in docs/importazione_plan.md §11. La preview salva staging e report ma non crea
consuntivi; l'apply usa il batch già validato e ricontrolla tutto sotto lock.

Permessi: caricare e analizzare richiede `imports.upload`; confermare richiede
`imports.apply` **e** `timesheets.assign_author`, perché ogni riga è intestata a un
collaboratore diverso dall'operatore. Quest'ultima è riservata all'Admin, quindi in pratica
solo un Admin conferma: vedi §13.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from canone.models import CanoneSubactivity
from core.permissions import CanApplyImports, CanAssignTimesheetAuthor, CanUploadImports
from importers.operational_batch import ApplyError, apply_batch, preview
from importers.operational_excel import WorkbookStructureError, normalize_key
from importers.operational_mapping import semester_of
from imports.models import (
    ImportBatch,
    ImportIssueLevel,
    ImportKind,
    ImportMapping,
    ImportRowStatus,
    ImportStatus,
    MappingKind,
    OperationalImportRow,
)
from projects.models import Project
from wallet.models import WalletAllocation

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class OperationalImportSerializer(serializers.Serializer):
    """Solo per lo schema OpenAPI: la risposta è un dizionario costruito a mano."""

    batch_id = serializers.UUIDField(read_only=True)


class CanConfirmImport(BasePermission):
    """Conferma: serve applicare import **e** poter intestare consuntivi ad altri.

    `timesheets.assign_author` è in `RESERVED_CAPABILITIES`, quindi in pratica confermano
    solo gli Admin. È una conseguenza del modello dei permessi, non una scelta di questa
    vista: cambiarla richiede una decisione esplicita sulla riserva (§13).
    """

    message = (
        "Per confermare l'importazione servono il permesso di applicare gli import e "
        "quello di intestare consuntivi ad altri collaboratori."
    )

    def has_permission(self, request, view) -> bool:
        return CanApplyImports().has_permission(
            request, view
        ) and CanAssignTimesheetAuthor().has_permission(request, view)


def _uploaded(request) -> tuple[Any, bytes]:
    uploaded = request.FILES.get("file")
    if uploaded is None:
        raise serializers.ValidationError({"file": "File mancante."})
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise serializers.ValidationError({"file": "File superiore a 10 MB."})
    if Path(uploaded.name or "").suffix.lower() != ".xlsx":
        raise serializers.ValidationError({"file": "Formato non supportato: usare .xlsx."})
    return uploaded, uploaded.read()


def _row_payload(row: OperationalImportRow) -> dict[str, Any]:
    target = row.resolved_target
    return {
        "id": str(row.pk),
        "sezione": row.section,
        "foglio": row.sheet,
        "riga_excel": row.excel_row,
        "celle": row.cells,
        "destinazione_excel": row.destination_raw,
        "destinazione_risolta": str(target) if target is not None else None,
        "collaboratore_excel": row.collaborator_raw,
        "utente": (row.author.get_full_name() or row.author.username if row.author_id else None),
        "data": row.period.isoformat(),
        "giornate": str(row.days),
        "descrizione": row.note,
        "stato": row.status,
        "motivazione": row.detail,
        "consuntivo": str(row.entry_id) if row.entry_id else None,
    }


def _batch_payload(batch: ImportBatch, *, rows: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(batch.pk),
        "file": batch.source_filename,
        "stato": batch.status,
        "stato_etichetta": batch.get_status_display(),
        "impronta": batch.content_hash,
        "creato_il": batch.created_at.isoformat(),
        "operatore": (
            batch.created_by.get_full_name() or batch.created_by.username
            if batch.created_by_id
            else None
        ),
        "applicato_da": (
            batch.applied_by.get_full_name() or batch.applied_by.username
            if batch.applied_by_id
            else None
        ),
        "applicato_il": batch.applied_at.isoformat() if batch.applied_at else None,
        "errore": batch.error,
        "report": batch.report,
        "confermabile": batch.can_apply and not _blocking_errors(batch),
        "errori_bloccanti": _blocking_messages(batch) if batch.can_apply else [],
    }
    if rows:
        payload["righe"] = [
            _row_payload(row)
            for row in batch.operational_rows.select_related(
                "project", "wallet_allocation", "canone_subactivity", "author", "entry"
            ).all()
        ]
    return payload


def _blocking_errors(batch: ImportBatch) -> bool:
    """Qualunque cosa impedisca alla conferma di andare a buon fine.

    Non bastano le righe non pronte: le capienze sono cumulative sulla destinazione, non
    una proprietà della singola riga (§10), quindi un batch le cui righe sono tutte
    `PRONTA` può ancora sfondare il budget di un progetto. Quegli errori stanno negli
    `ImportIssue` di livello ERROR, che sono gli stessi mostrati nella console dei
    problemi. Ignorarli abilitava il pulsante su un apply che `_recheck_targets` rifiuta
    sotto lock: un clic che non poteva funzionare.
    """
    if batch.operational_rows.exclude(status=ImportRowStatus.PRONTA).exists():
        return True
    return batch.issues.filter(level=ImportIssueLevel.ERROR).exists()


def _blocking_messages(batch: ImportBatch) -> list[str]:
    """Gli errori che bloccano la conferma, per dirlo accanto al pulsante."""
    return list(
        batch.issues.filter(level=ImportIssueLevel.ERROR).values_list("message", flat=True)[:20]
    )


class OperationalImportPreviewView(APIView):
    """POST /imports/operational/preview — analizza il file e prepara l'anteprima."""

    permission_classes = [CanUploadImports]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = OperationalImportSerializer

    @extend_schema(request=None, responses={201: OperationalImportSerializer})
    def post(self, request):
        uploaded, payload = _uploaded(request)
        try:
            result = preview(
                upload=payload,
                filename=uploaded.name or "estratto.xlsx",
                user=request.user,
            )
        except WorkbookStructureError as exc:
            raise serializers.ValidationError({"file": str(exc)}) from exc
        return Response(
            _batch_payload(result.batch, rows=True),
            status=status.HTTP_201_CREATED,
        )


class OperationalImportMappingsView(APIView):
    """PATCH /imports/operational/{id}/mappings — conferma le associazioni e ricalcola."""

    permission_classes = [CanUploadImports]
    serializer_class = OperationalImportSerializer

    @extend_schema(request=None, responses={200: OperationalImportSerializer})
    @transaction.atomic
    def patch(self, request, pk):
        batch = get_object_or_404(
            ImportBatch.objects.select_for_update(),
            pk=pk,
            kind=ImportKind.OPERATIONAL_XLSX,
        )
        if batch.status != ImportStatus.DRY_RUN:
            return Response(
                {"detail": "Batch già applicato: le associazioni non si cambiano."},
                status=status.HTTP_409_CONFLICT,
            )
        entries = request.data.get("associazioni")
        if not isinstance(entries, list) or not entries:
            raise serializers.ValidationError(
                {"associazioni": "Fornire un elenco di associazioni da confermare."}
            )
        for entry in entries:
            _save_mapping(entry, user=request.user)

        # Rieseguire l'analisi è il solo modo onesto di riallineare lo staging: le
        # associazioni appena salvate cambiano anche capienze e sovrapposizioni, non solo
        # la destinazione della riga. Il file è allegato al batch, quindi non serve
        # ricaricarlo.
        if not batch.file:
            return Response(
                {
                    "detail": (
                        "Associazioni salvate, ma il file del batch non è più "
                        "disponibile: ricaricarlo per rigenerare l'anteprima."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        with batch.file.open("rb") as handle:
            result = preview(
                upload=handle.read(),
                filename=batch.source_filename,
                user=request.user,
                batch=batch,
            )
        return Response(_batch_payload(result.batch, rows=True))


def _save_mapping(entry: Any, *, user) -> ImportMapping:
    if not isinstance(entry, dict):
        raise serializers.ValidationError({"associazioni": "Ogni voce deve essere un oggetto."})
    kind = entry.get("tipo")
    raw_value = (entry.get("valore") or "").strip()
    target_id = entry.get("destinazione")
    if kind not in MappingKind.values:
        raise serializers.ValidationError(
            {"tipo": f"Tipo non valido: {kind}. Ammessi: {', '.join(MappingKind.values)}."}
        )
    if not raw_value:
        raise serializers.ValidationError({"valore": "Valore dell'Excel obbligatorio."})
    if not target_id:
        raise serializers.ValidationError({"destinazione": "Destinazione obbligatoria."})

    defaults: dict[str, Any] = {
        "external_value": raw_value[:400],
        "created_by": user,
        "updated_by": user,
        "project": None,
        "wallet_allocation": None,
        "canone_subactivity": None,
        "user": None,
    }
    context_year: int | None = None
    context_semester = ""

    if kind == MappingKind.PROGETTO:
        defaults["project"] = get_object_or_404(Project, pk=target_id)
    elif kind == MappingKind.WALLET_ALLOCATION:
        allocation = get_object_or_404(
            WalletAllocation.objects.select_related("wallet_year"), pk=target_id
        )
        defaults["wallet_allocation"] = allocation
        context_year = entry.get("anno") or allocation.wallet_year.year
    elif kind == MappingKind.CANONE_SUBACTIVITY:
        subactivity = get_object_or_404(
            CanoneSubactivity.objects.select_related("canone"), pk=target_id
        )
        defaults["canone_subactivity"] = subactivity
        context_semester = entry.get("semestre") or subactivity.canone.semester
    else:
        from django.contrib.auth.models import User

        defaults["user"] = get_object_or_404(User, pk=target_id)

    mapping, _ = ImportMapping.objects.update_or_create(
        kind=kind,
        external_key=normalize_key(raw_value)[:400],
        context_year=context_year,
        context_semester=context_semester,
        defaults=defaults,
    )
    return mapping


class OperationalImportApplyView(APIView):
    """POST /imports/operational/{id}/apply — scrive i consuntivi, in modo atomico."""

    permission_classes = [CanConfirmImport]
    serializer_class = OperationalImportSerializer

    @extend_schema(request=None, responses={200: OperationalImportSerializer})
    def post(self, request, pk):
        expected = request.data.get("impronta")
        batch = get_object_or_404(ImportBatch, pk=pk, kind=ImportKind.OPERATIONAL_XLSX)
        if expected and expected != batch.content_hash:
            return Response(
                {
                    "detail": (
                        "L'impronta non coincide con quella dell'anteprima: "
                        "rieseguire l'analisi del file."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        try:
            batch = apply_batch(batch_id=pk, user=request.user)
        except ApplyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(_batch_payload(batch, rows=True))


class OperationalImportListView(APIView):
    """GET /imports/operational — storico delle importazioni."""

    permission_classes = [CanUploadImports]
    serializer_class = OperationalImportSerializer

    def get(self, request):
        batches = ImportBatch.objects.filter(kind=ImportKind.OPERATIONAL_XLSX).select_related(
            "created_by", "applied_by"
        )[:100]
        return Response({"importazioni": [_batch_payload(batch) for batch in batches]})


class OperationalImportDetailView(APIView):
    """GET /imports/operational/{id} — una importazione con le sue righe."""

    permission_classes = [CanUploadImports]
    serializer_class = OperationalImportSerializer

    def get(self, request, pk):
        batch = get_object_or_404(
            ImportBatch.objects.select_related("created_by", "applied_by"),
            pk=pk,
            kind=ImportKind.OPERATIONAL_XLSX,
        )
        return Response(_batch_payload(batch, rows=True))


class ImportMappingListCreateView(APIView):
    """GET/POST /imports/mappings — il registro della Riconciliazione."""

    permission_classes = [CanUploadImports]
    serializer_class = OperationalImportSerializer

    def get(self, request):
        mappings = ImportMapping.objects.select_related(
            "project", "wallet_allocation", "canone_subactivity", "user", "created_by"
        )
        kind = request.query_params.get("tipo")
        if kind:
            mappings = mappings.filter(kind=kind)
        return Response(
            {
                "associazioni": [
                    {
                        "id": str(m.pk),
                        "tipo": m.kind,
                        "tipo_etichetta": m.get_kind_display(),
                        "valore": m.external_value,
                        "destinazione": m.target_label,
                        "anno": m.context_year,
                        "semestre": m.context_semester,
                        "confermata_da": (
                            m.created_by.get_full_name() or m.created_by.username
                            if m.created_by_id
                            else None
                        ),
                        "confermata_il": m.created_at.isoformat(),
                    }
                    for m in mappings
                ]
            }
        )

    @transaction.atomic
    def post(self, request):
        mapping = _save_mapping(request.data, user=request.user)
        return Response(
            {"id": str(mapping.pk), "destinazione": mapping.target_label},
            status=status.HTTP_201_CREATED,
        )


class ImportMappingDetailView(APIView):
    """DELETE /imports/mappings/{id} — un'associazione sbagliata va potuta togliere."""

    permission_classes = [CanUploadImports]
    serializer_class = OperationalImportSerializer

    def delete(self, request, pk):
        mapping = get_object_or_404(ImportMapping, pk=pk)
        mapping.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CanoneSemesterHintView(APIView):
    """GET /imports/operational/semestre?data=… — il semestre dedotto da una data.

    Serve alla pagina per spiegare *perché* una riga finisce su un canone invece che su
    un altro, quando lo stesso titolo esiste in due semestri.
    """

    permission_classes = [CanUploadImports]
    serializer_class = OperationalImportSerializer

    def get(self, request):
        from datetime import date

        raw = request.query_params.get("data", "")
        try:
            period = date.fromisoformat(raw)
        except ValueError as exc:
            raise serializers.ValidationError({"data": "Data non valida (aaaa-mm-gg)."}) from exc
        return Response({"data": raw, "semestre": semester_of(period)})
