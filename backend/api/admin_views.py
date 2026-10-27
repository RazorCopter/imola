"""API amministrative per import, storico e gestione ruoli."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from django.apps import apps
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import models, transaction
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core import capabilities, roles
from core.models import AdminAuditEvent, RoleCapabilityOverride
from core.permissions import CanManagePrivileges, CanManageUsers, CanResetData, IsAdmin
from importers.batch import apply_seed, dry_run_seed, schema_paths
from importers.ppm import apply_ppm, dry_run_ppm
from importers.schema import validate_seed_auto
from imports.models import ImportBatch, WorkbookDatasetSnapshot

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
            raise serializers.ValidationError("File JSON mancante o superiore a 10 MB.")
        try:
            source_filename = uploaded.name or "seed.json"
            text = raw.decode("utf-8")
            payload = validate_seed_auto(text, schema_paths())
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
            raise serializers.ValidationError(str(exc))
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
            raise serializers.ValidationError("File PPM mancante o superiore a 10 MB.")
        suffix = Path(uploaded.name or "upload").suffix.lower()
        if suffix not in {".xlsx", ".pdf"}:
            raise serializers.ValidationError("Formato PPM non supportato: usare .xlsx o .pdf.")
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
            raise serializers.ValidationError(str(exc))
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


class WorkbookDatasetListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, batch_id):
        batch = ImportBatch.objects.filter(pk=batch_id).first()
        if batch is None:
            return Response({"detail": "Batch inesistente."}, status=status.HTTP_404_NOT_FOUND)
        rows = batch.workbook_datasets.order_by("dataset_id")
        return Response(
            {
                "batch_id": batch.id,
                "source_filename": batch.source_filename,
                "schema_version": batch.report.get("schema_version"),
                "results": [
                    {
                        "id": row.id,
                        "dataset_id": row.dataset_id,
                        "sheet": row.sheet_name,
                        "range": row.source_range,
                        "row_count": row.row_count,
                        "column_count": row.column_count,
                        "columns": row.columns,
                    }
                    for row in rows
                ],
            }
        )


class WorkbookDatasetDetailView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, batch_id, dataset_pk):
        dataset = WorkbookDatasetSnapshot.objects.filter(
            pk=dataset_pk, batch_id=batch_id
        ).first()
        if dataset is None:
            return Response({"detail": "Dataset inesistente."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "id": dataset.id,
                "dataset_id": dataset.dataset_id,
                "sheet": dataset.sheet_name,
                "range": dataset.source_range,
                "row_count": dataset.row_count,
                "column_count": dataset.column_count,
                "columns": dataset.columns,
                "rows": dataset.rows,
            }
        )


class UserWriteSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=roles.ALL_ROLES), required=False
    )
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    def validate_username(self, value):
        queryset = User.objects.filter(username__iexact=value)
        instance = self.context.get("instance")
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Username già utilizzato.")
        return value

    def validate_password(self, value):
        try:
            validate_password(value, user=self.context.get("instance"))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate_roles(self, value):
        return list(dict.fromkeys(value))


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_password(self, value):
        try:
            validate_password(value, user=self.context.get("instance"))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "roles": sorted(roles.roles_of(user)),
        "last_login": user.last_login,
        "date_joined": user.date_joined,
    }


def _audit(request, action: str, target_type: str, target, details=None) -> None:
    AdminAuditEvent.objects.create(
        actor=request.user,
        actor_username=request.user.username,
        action=action,
        target_type=target_type,
        target_id=str(getattr(target, "pk", target)),
        target_label=str(getattr(target, "username", target)),
        details=details or {},
    )


def _active_admin_count(exclude_user_id=None) -> int:
    queryset = User.objects.filter(is_active=True).filter(
        models.Q(is_superuser=True) | models.Q(groups__name=roles.ADMIN)
    )
    if exclude_user_id is not None:
        queryset = queryset.exclude(pk=exclude_user_id)
    return queryset.distinct().count()


def _would_remove_last_admin(user: User, new_roles: list[str], is_active: bool) -> bool:
    currently_admin = roles.is_admin(user) and user.is_active
    remains_admin = is_active and (user.is_superuser or roles.ADMIN in new_roles)
    return currently_admin and not remains_admin and _active_admin_count(user.pk) == 0


def _has_domain_references(user: User) -> bool:
    """Conta anche FK con related_name='+' e SET_NULL: sono comunque riferimenti storici."""
    for model in apps.get_models():
        if model in {User, Group, AdminAuditEvent}:
            continue
        for field in model._meta.fields:
            if field.is_relation and field.related_model is User:
                if model._default_manager.filter(**{field.name: user}).exists():
                    return True
    return False


class UserRolesView(APIView):
    permission_classes = [CanManageUsers]

    def get(self, request):
        return Response(
            {
                "roles": [{"key": role, "label": roles.LABELS[role]} for role in roles.ALL_ROLES],
                "results": [
                    _user_payload(user)
                    for user in User.objects.prefetch_related("groups").order_by("username")
                ],
            }
        )

    @transaction.atomic
    def post(self, request):
        serializer = UserWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data.get("username") or not data.get("password"):
            return Response(
                {"detail": "Username e password iniziale sono obbligatori."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        selected_roles = data.pop("roles", [])
        password = data.pop("password")
        user = User(**data)
        user.set_password(password)
        user.save()
        roles.ensure_groups()
        user.groups.set(Group.objects.filter(name__in=selected_roles))
        _audit(request, "user.created", "user", user, {"roles": selected_roles})
        return Response(_user_payload(user), status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    permission_classes = [CanManageUsers]

    def _get_user(self, pk):
        return User.objects.prefetch_related("groups").filter(pk=pk).first()

    @transaction.atomic
    def patch(self, request, pk):
        user = self._get_user(pk)
        if user is None:
            return Response({"detail": "Utente inesistente."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserWriteSerializer(
            data=request.data, partial=True, context={"instance": user}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        data.pop("password", None)
        selected_roles = data.pop("roles", sorted(roles.roles_of(user)))
        new_active = data.get("is_active", user.is_active)
        if user.pk == request.user.pk and not new_active:
            return Response(
                {"detail": "Non puoi disattivare il tuo account."},
                status=status.HTTP_409_CONFLICT,
            )
        if _would_remove_last_admin(user, selected_roles, new_active):
            return Response(
                {"detail": "L'ultimo amministratore attivo non può perdere i privilegi."},
                status=status.HTTP_409_CONFLICT,
            )
        for field, value in data.items():
            setattr(user, field, value)
        user.save(update_fields=[*data.keys()] if data else None)
        roles.ensure_groups()
        user.groups.set(Group.objects.filter(name__in=selected_roles))
        _audit(request, "user.updated", "user", user, {"roles": selected_roles})
        return Response(_user_payload(user))

    @transaction.atomic
    def delete(self, request, pk):
        user = self._get_user(pk)
        if user is None:
            return Response({"detail": "Utente inesistente."}, status=status.HTTP_404_NOT_FOUND)
        if user.pk == request.user.pk:
            return Response(
                {"detail": "Non puoi eliminare il tuo account; usa la disattivazione."},
                status=status.HTTP_409_CONFLICT,
            )
        if user.is_active and roles.is_admin(user) and _active_admin_count(user.pk) == 0:
            return Response(
                {"detail": "L'ultimo amministratore attivo non può essere eliminato."},
                status=status.HTTP_409_CONFLICT,
            )
        if _has_domain_references(user):
            return Response(
                {"detail": "Utente referenziato: disattivalo invece di eliminarlo."},
                status=status.HTTP_409_CONFLICT,
            )
        target = {"id": user.pk, "username": user.username}
        user.delete()
        _audit(request, "user.deleted", "user", target["id"], {"username": target["username"]})
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserPasswordView(APIView):
    permission_classes = [CanManageUsers]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).first()
        if user is None:
            return Response({"detail": "Utente inesistente."}, status=status.HTTP_404_NOT_FOUND)
        serializer = PasswordSerializer(data=request.data, context={"instance": user})
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])
        _audit(request, "user.password_set", "user", user)
        return Response({"detail": "Password aggiornata."})


class RoleCapabilitiesView(APIView):
    permission_classes = [CanManagePrivileges]

    def get(self, request):
        return Response(
            {
                "capabilities": sorted(capabilities.ALL_CAPABILITIES),
                "reserved": sorted(capabilities.RESERVED_CAPABILITIES),
                "roles": [
                    {
                        "key": role,
                        "label": roles.LABELS[role],
                        "capabilities": sorted(capabilities.capabilities_for_role(role)),
                    }
                    for role in roles.ALL_ROLES
                ],
            }
        )

    @transaction.atomic
    def put(self, request):
        role = str(request.data.get("role", ""))
        selected = set(request.data.get("capabilities", []))
        if role not in roles.ALL_ROLES or not selected <= set(capabilities.ALL_CAPABILITIES):
            return Response({"detail": "Ruolo o capability non validi."}, status=400)
        if role == roles.ADMIN:
            return Response({"detail": "I privilegi Admin non sono riducibili."}, status=409)
        if selected & set(capabilities.RESERVED_CAPABILITIES):
            return Response({"detail": "Capability riservata ad Admin."}, status=400)
        RoleCapabilityOverride.objects.filter(role=role).delete()
        RoleCapabilityOverride.objects.bulk_create(
            [
                RoleCapabilityOverride(
                    role=role,
                    capability=capability,
                    enabled=capability in selected,
                )
                for capability in capabilities.ALL_CAPABILITIES
                if capability not in capabilities.RESERVED_CAPABILITIES
                and (capability in selected) != (capability in capabilities.ROLE_DEFAULTS[role])
            ]
        )
        _audit(
            request,
            "role.capabilities_updated",
            "role",
            role,
            {"capabilities": sorted(selected)},
        )
        return Response(
            {"role": role, "capabilities": sorted(capabilities.capabilities_for_role(role))}
        )


class AdminDataResetView(APIView):
    """Reset sicuro e transazionale di tutti i dati applicativi operativi (Tranche 6).

    Preserva gli account utente, i gruppi, i ruoli e la configurazione di sistema.
    Richiede la capability 'data.reset', token effimero e conferma con 'ELIMINA'.
    """

    permission_classes = [CanResetData]

    def get(self, request):
        from anomalies.models import Anomaly
        from canone.models import Canone, CanoneSubactivity
        from imports.models import (
            ImportBatch,
            ImportIssue,
            WorkbookDatasetSnapshot,
            WorkbookSheetSnapshot,
        )
        from ppm.models import PpmSnapshot, PpmSnapshotRow
        from projects.models import BillingMilestone, Project
        from timesheets.models import TimesheetEntry
        from wallet.models import WalletActivity, WalletAllocation, WalletYear

        signer = TimestampSigner()
        token = signer.sign(f"{request.user.id}:data.reset")

        preview = {
            "progetti": Project.objects.count(),
            "milestone": BillingMilestone.objects.count(),
            "consuntivi": TimesheetEntry.objects.count(),
            "allocazioni_wallet": WalletAllocation.objects.count(),
            "attivita_wallet": WalletActivity.objects.count(),
            "anni_wallet": WalletYear.objects.count(),
            "canoni": Canone.objects.count(),
            "sottoattivita_canone": CanoneSubactivity.objects.count(),
            "snapshot_ppm": PpmSnapshot.objects.count(),
            "righe_snapshot_ppm": PpmSnapshotRow.objects.count(),
            "anomalie": Anomaly.objects.count(),
            "batch_import": ImportBatch.objects.count(),
            "issues_import": ImportIssue.objects.count(),
            "fogli_workbook": WorkbookSheetSnapshot.objects.count(),
            "dataset_workbook": WorkbookDatasetSnapshot.objects.count(),
        }
        total = sum(preview.values())
        return Response(
            {
                "preview": preview,
                "total_records": total,
                "confirmation_keyword": "ELIMINA",
                "token": token,
            }
        )

    def post(self, request):
        from anomalies.models import Anomaly
        from canone.models import Canone, CanoneSubactivity
        from imports.models import (
            ImportBatch,
            ImportIssue,
            WorkbookDatasetSnapshot,
            WorkbookSheetSnapshot,
        )
        from ppm.models import PpmSnapshot, PpmSnapshotRow
        from projects.models import BillingMilestone, Project
        from timesheets.models import TimesheetEntry
        from timesheets.mutations import allow_ledger_mutation
        from wallet.models import WalletActivity, WalletAllocation, WalletYear

        confirmation = str(request.data.get("confirmation", "")).strip()
        if confirmation != "ELIMINA":
            return Response(
                {
                    "detail": (
                        "Per confermare l'eliminazione dei dati è necessario digitare "
                        "esattamente 'ELIMINA'."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = request.data.get("token")
        if not token:
            return Response(
                {"detail": "Token di sicurezza mancante. Ricarica la preview e riprova."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        signer = TimestampSigner()
        try:
            val = signer.unsign(token, max_age=300)
            expected = f"{request.user.id}:data.reset"
            if val != expected:
                return Response(
                    {"detail": "Token non valido per questa sessione."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except SignatureExpired:
            return Response(
                {"detail": "Token di conferma scaduto. Ricarica la preview e riprova."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except BadSignature:
            return Response(
                {"detail": "Firma del token non valida."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleted_counts: dict[str, int] = {}
        with transaction.atomic():
            with allow_ledger_mutation(
                reason=f"Reset operativo totale autorizzato da {request.user.username}"
            ):
                deleted_counts["anomalie"] = Anomaly.objects.all().delete()[0]
                deleted_counts["righe_snapshot_ppm"] = PpmSnapshotRow.objects.all().delete()[0]
                deleted_counts["snapshot_ppm"] = PpmSnapshot.objects.all().delete()[0]
                deleted_counts["consuntivi"] = TimesheetEntry.objects.all().delete()[0]
                deleted_counts["allocazioni_wallet"] = WalletAllocation.objects.all().delete()[0]
                deleted_counts["attivita_wallet"] = WalletActivity.objects.all().delete()[0]
                deleted_counts["anni_wallet"] = WalletYear.objects.all().delete()[0]
                deleted_counts["sottoattivita_canone"] = CanoneSubactivity.objects.all().delete()[0]
                deleted_counts["canoni"] = Canone.objects.all().delete()[0]
                deleted_counts["milestone"] = BillingMilestone.objects.all().delete()[0]
                deleted_counts["progetti"] = Project.objects.all().delete()[0]
                deleted_counts["dataset_workbook"] = (
                    WorkbookDatasetSnapshot.objects.all().delete()[0]
                )
                deleted_counts["fogli_workbook"] = WorkbookSheetSnapshot.objects.all().delete()[0]
                deleted_counts["issues_import"] = ImportIssue.objects.all().delete()[0]
                deleted_counts["batch_import"] = ImportBatch.objects.all().delete()[0]

            _audit(
                request,
                "data.reset",
                "database",
                "operational_data",
                {"deleted": deleted_counts, "executed_by": request.user.username},
            )

        return Response(
            {
                "status": "success",
                "detail": "Tutti i dati operativi sono stati eliminati con successo.",
                "deleted": deleted_counts,
            }
        )
