"""Endpoint delle viste calcolate: residui, wallet, canone, riconciliazione.

Qui non si scrive nulla: tutti i numeri arrivano dai builder in domain/, mai da colonne
salvate. Ogni risposta porta con sé la spiegazione del calcolo, che la UI mostra in tooltip.
"""

from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, DecimalField, Max, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.canone_serializers import CanoneSubactivityWriteSerializer, CanoneWriteSerializer
from api.concurrency import etag_matches, make_etag
from api.project_serializers import (
    PROJECT_ANNOTATION_FIELDS,
    PROJECT_CONTROL_FIELDS,
    PROJECT_EDITABLE_FIELDS,
    ProjectUpdateSerializer,
)
from api.timesheet_authors import resolve_author
from api.wallet_timesheets import active_entries, entry_payload
from canone.models import Canone, CanoneSubactivity
from core import capabilities
from core.exceptions import DomainError, PreconditionRequired, StaleResource
from core.models import AdminAuditEvent, AppSettings
from core.permissions import (
    CanCreateTimesheets,
    CanEditProjects,
    CanEditTimesheets,
    CanEditWallet,
    CanExport,
    CanResolveAnomalies,
    CanUploadImports,
    CanValidateProjectClosure,
    IsAdmin,
    ReadOnlyOrCanCreateProjects,
    ReadOnlyOrCanManageCanone,
    ReadOnlyOrLedgerWriter,
    ReferentCanAnnotate,
)
from domain.canone_status import canone_burndown, canone_status
from domain.cost_analysis import build_cost_analysis
from domain.dashboard import dashboard_summary
from domain.reconciliation import reconcile, reconciliation_summary
from domain.residuals import residual_explanation, residual_validity
from domain.wallet_balance import wallet_by_assignee, wallet_flow, wallet_year_balance
from wallet.services import ensure_source_lot


class DomainResponseSerializer(serializers.Serializer):
    """Schema di fallback esplicito per risposte di dominio documentate come oggetti."""


class ProjectListResponseSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.DictField())
    count = serializers.IntegerField()


class AuditHistoryResponseSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.DictField())
    count = serializers.IntegerField()


class DocumentedAPIView(APIView):
    serializer_class = DomainResponseSerializer


def current_settings() -> AppSettings:
    return AppSettings.get_solo()


def check_expected_version(request, instance) -> None:
    """Contratto comune PATCH: If-Match o expected_version, conflitto sempre 409."""
    header = request.headers.get("If-Match", "")
    expected_version = request.data.get("expected_version")
    if not header and expected_version in (None, ""):
        raise PreconditionRequired()
    if not etag_matches(header, instance) and str(expected_version) != str(instance.version):
        raise StaleResource(
            detail=(
                "La risorsa è stata modificata da un altro utente "
                f"(versione attuale {instance.version}): ricarica i dati e riprova."
            )
        )


class SettingsView(DocumentedAPIView):
    """Parametri globali: lettura per tutti, modifica solo Admin."""

    def get_permissions(self):
        return [IsAdmin()] if self.request.method not in ("GET", "HEAD") else [IsAuthenticated()]

    def get(self, request):
        settings_obj = current_settings()
        return Response(
            {
                "ore_per_giornata": settings_obj.hours_per_day,
                "costo_giornata_uomo": settings_obj.daily_person_cost,
                "costo_forfettario_canone": settings_obj.canone_fixed_cost,
                "politica_costo": (
                    "Valore globale corrente, non storicizzato e non differenziato per fornitore."
                ),
                "granularita_ppm_gg": settings_obj.ppm_granularity_days,
                "tolleranza_riconciliazione_gg": settings_obj.reconciliation_tolerance_days,
                "anni_validita_dopo_chiusura": settings_obj.residual_years_after_closure,
                "finestra_scadenza_giorni": settings_obj.residual_expiring_window_days,
                "version": settings_obj.version,
            }
        )

    @transaction.atomic
    def patch(self, request):
        existing = current_settings()
        settings_obj = AppSettings.objects.select_for_update().get(pk=existing.pk)
        header = request.headers.get("If-Match")
        version = request.data.get("expected_version")
        if header or version not in (None, ""):
            check_expected_version(request, settings_obj)
        mapping = {
            "ore_per_giornata": "hours_per_day",
            "costo_giornata_uomo": "daily_person_cost",
            "costo_forfettario_canone": "canone_fixed_cost",
            "granularita_ppm_gg": "ppm_granularity_days",
            "tolleranza_riconciliazione_gg": "reconciliation_tolerance_days",
            "anni_validita_dopo_chiusura": "residual_years_after_closure",
            "finestra_scadenza_giorni": "residual_expiring_window_days",
        }
        old_cost = settings_obj.daily_person_cost
        old_canone_cost = settings_obj.canone_fixed_cost
        for key, attr in mapping.items():
            if key in request.data:
                setattr(settings_obj, attr, request.data[key])
        try:
            settings_obj.full_clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        settings_obj.save()
        if old_cost != settings_obj.daily_person_cost:
            AdminAuditEvent.objects.create(
                actor=request.user,
                actor_username=request.user.get_username(),
                action="settings.daily_person_cost.update",
                target_type="app_settings",
                target_id=str(settings_obj.id),
                target_label="Impostazioni globali",
                details={"old": str(old_cost), "new": str(settings_obj.daily_person_cost)},
            )
        if old_canone_cost != settings_obj.canone_fixed_cost:
            AdminAuditEvent.objects.create(
                actor=request.user,
                actor_username=request.user.get_username(),
                action="settings.canone_fixed_cost.update",
                target_type="app_settings",
                target_id=str(settings_obj.id),
                target_label="Costo forfettario canone",
                details={"old": str(old_canone_cost), "new": str(settings_obj.canone_fixed_cost)},
            )
        return self.get(request)


class CostAnalysisView(DocumentedAPIView):
    """Costi a giornata e inclusione opzionale del forfait pagato dei canoni."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        parsed: dict[str, date | None] = {"from": None, "to": None}
        errors = {}
        for name in parsed:
            raw = request.query_params.get(name)
            if raw:
                try:
                    parsed[name] = date.fromisoformat(raw)
                except ValueError:
                    errors[name] = "Usare una data ISO nel formato YYYY-MM-DD."
        if errors:
            raise serializers.ValidationError(errors)
        if parsed["from"] and parsed["to"] and parsed["from"] > parsed["to"]:
            raise serializers.ValidationError({"from": "Deve essere precedente o uguale a to."})
        settings_obj = current_settings()
        raw_include_canone = request.query_params.get("include_canone", "false").lower()
        if raw_include_canone not in ("true", "false", "1", "0"):
            raise serializers.ValidationError({"include_canone": "Usare true o false."})
        return Response(
            build_cost_analysis(
                daily_cost=settings_obj.daily_person_cost,
                canone_fixed_cost=settings_obj.canone_fixed_cost,
                include_canone=raw_include_canone in ("true", "1"),
                date_from=parsed["from"],
                date_to=parsed["to"],
            )
        )


class DashboardView(DocumentedAPIView):
    """Aggregazioni read-only per grafici e prossime fatturazioni."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="dashboard_summary", responses={200: DomainResponseSerializer})
    def get(self, request):
        return Response(
            dashboard_summary(today=timezone.localdate(), settings_obj=current_settings())
        )


class ProjectListCreateView(DocumentedAPIView):
    """Elenco anagrafico e creazione guidata dei progetti."""

    permission_classes = [ReadOnlyOrCanCreateProjects]

    @extend_schema(operation_id="project_list", responses={200: ProjectListResponseSerializer})
    def get(self, request):
        from projects.models import Project

        rows = Project.objects.select_related("client_owner", "supplier_owner").order_by("code")
        return Response(
            {
                "results": [
                    {
                        "id": row.id,
                        "codice": row.code,
                        "titolo": row.title,
                        "tipo_contratto": row.contract_type,
                    }
                    for row in rows
                ],
                "count": rows.count(),
            }
        )

    @extend_schema(request=dict, responses={201: dict})
    @transaction.atomic
    def post(self, request):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from projects.billing import sync_project_billing_schedule
        from projects.models import Project

        allowed_fields = {
            "code",
            "title",
            "contract_type",
            "budget_days",
            "start_date",
            "planned_end_date",
            "offer_status",
            "timesheet_status",
            "billing_status",
            "notes",
        }
        data = {key: value for key, value in request.data.items() if key in allowed_fields}
        project = Project(**data)
        try:
            project.full_clean()
            project.save()
            sync_project_billing_schedule(project, user=request.user)
        except DjangoValidationError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"id": project.id, "codice": project.code, "version": project.version},
            status=status.HTTP_201_CREATED,
        )


class ProjectBalancesView(DocumentedAPIView):
    """Vista calcolata project_balance, con stato di scadenza del residuo (R2)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from domain.residuals import (
            project_balance_qs,
            project_closure_ready,
            project_operational_status,
        )

        settings_obj = current_settings()
        today = timezone.localdate()
        rows = []
        queryset = (
            project_balance_qs()
            .select_related("client_owner", "supplier_owner")
            .prefetch_related("wallet_allocations")
        )
        for project in queryset.order_by("code"):
            validity = residual_validity(
                timesheet_status=project.timesheet_status,
                closure_date=project.actual_closure_date,
                today=today,
                years_valid_after_closure=settings_obj.residual_years_after_closure,
                expiring_window_days=settings_obj.residual_expiring_window_days,
            )
            can_edit = capabilities.has_capability(request.user, capabilities.EDIT_PROJECTS)
            can_annotate = ReferentCanAnnotate.can_annotate(request.user, project)
            rows.append(
                {
                    "id": project.id,
                    "version": project.version,
                    "codice": project.code,
                    "titolo": project.title,
                    "tipo_contratto": project.contract_type,
                    "budget": project.budget_days,
                    "consuntivi_diretti": project.direct_consumed_days,
                    "allocato_a_wallet": project.allocated_to_wallet_days,
                    "rimanente_allocato_wallet": (
                        project.allocated_to_wallet_days - project.consumed_via_wallet_days
                    ),
                    "consumato_via_wallet": project.consumed_via_wallet_days,
                    "consumato_totale": project.total_consumed_days,
                    "residuo": project.residual_days,
                    "data_inizio": project.start_date,
                    "data_fine_prevista": project.planned_end_date,
                    "stato_consuntivazione": project.timesheet_status,
                    "stato_operativo": project_operational_status(project),
                    "stato_fatturazione": project.billing_status,
                    "stato_offerta": project.offer_status,
                    "stato_residuo": validity.state,
                    "residuo_scade_il": validity.expires_on,
                    "residuo_giorni_alla_scadenza": validity.days_to_expiry,
                    "residuo_motivo": validity.reason,
                    "spiegazione_residuo": residual_explanation(
                        project.budget_days,
                        project.direct_consumed_days,
                        project.allocated_to_wallet_days,
                    ),
                    "permissions": {
                        "edit": can_edit,
                        "annotate": can_annotate,
                        "validate_closure": (
                            capabilities.has_capability(
                                request.user, capabilities.VALIDATE_PROJECT_CLOSURE
                            )
                            and project_closure_ready(project)
                        ),
                    },
                }
            )
        return Response({"results": rows, "count": len(rows)})


class ProjectLedgerView(DocumentedAPIView):
    """Consuntivi diretti e attività wallet finanziate dal progetto."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [CanCreateTimesheets()]
        return [IsAuthenticated()]

    @staticmethod
    def get_project(pk):
        from projects.models import Project

        return get_object_or_404(Project, pk=pk)

    def get(self, request, pk):
        from timesheets.models import TimesheetEntry, TimesheetSource
        from wallet.models import WalletAllocation

        project = self.get_project(pk)
        timesheets = (
            TimesheetEntry.objects.filter(
                project=project,
                reversals__isnull=True,
            )
            .exclude(source=TimesheetSource.STORNO)
            .select_related("created_by")
            .order_by("-period", "-created_at", "-id")
        )
        allocations = (
            WalletAllocation.objects.filter(source_project=project)
            .select_related("activity", "assignee")
            .annotate(consumed=Sum("timesheet_entries__days"))
            .order_by("activity__code", "created_at")
        )
        return Response(
            {
                "consuntivi": [
                    {
                        "id": entry.id,
                        "data": entry.period,
                        "giornate": entry.days,
                        "descrizione": entry.note,
                        "utente": (
                            (entry.created_by.get_full_name() or entry.created_by.username)
                            if entry.created_by
                            else "Importazione"
                        ),
                        "utente_id": entry.created_by_id,
                        "origine": entry.source,
                    }
                    for entry in timesheets
                ],
                "wallet": [
                    {
                        "id": allocation.id,
                        "codice": allocation.activity.code,
                        "attivita": allocation.activity.title,
                        "assegnatario": (
                            allocation.assignee.full_name if allocation.assignee else None
                        ),
                        "allocato": allocation.allocated_days,
                        "consumato": allocation.consumed or 0,
                        "rimanente": allocation.allocated_days - (allocation.consumed or 0),
                        "stato": allocation.status,
                    }
                    for allocation in allocations
                ],
            }
        )

    @transaction.atomic
    def post(self, request, pk):
        from decimal import Decimal, InvalidOperation

        from projects.models import TimesheetStatus
        from timesheets.models import TimesheetEntry, TimesheetSource

        project = self.get_project(pk)
        if project.timesheet_status == TimesheetStatus.CHIUSO:
            return Response(
                {"detail": "Il progetto è chiuso: non è possibile aggiungere consuntivi diretti."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            days = Decimal(str(request.data.get("giornate", "")))
        except InvalidOperation:
            return Response({"giornate": ["Inserire un numero valido."]}, status=400)
        description = str(request.data.get("descrizione", "")).strip()
        if days <= 0:
            return Response(
                {"giornate": ["Le giornate devono essere maggiori di zero."]}, status=400
            )
        if not description:
            return Response({"descrizione": ["La descrizione è obbligatoria."]}, status=400)
        if len(description) > 300:
            return Response({"descrizione": ["Massimo 300 caratteri."]}, status=400)
        direct_consumed = (
            TimesheetEntry.objects.filter(project=project).aggregate(total=Sum("days"))["total"]
            or 0
        )
        allocated_to_wallet = (
            project.wallet_allocations.aggregate(total=Sum("allocated_days"))["total"] or 0
        )
        if days > project.budget_days - direct_consumed - allocated_to_wallet:
            return Response(
                {"giornate": ["Le giornate superano il residuo diretto del progetto."]},
                status=400,
            )
        raw_period = request.data.get("data") or request.data.get("periodo")
        try:
            period = date.fromisoformat(str(raw_period)) if raw_period else timezone.localdate()
        except ValueError:
            return Response({"data": ["Inserire una data valida."]}, status=400)
        try:
            author = resolve_author(request)
        except DjangoValidationError as exc:
            return Response(getattr(exc, "message_dict", {"detail": exc.messages}), status=400)
        entry = TimesheetEntry(
            project=project,
            period=period,
            days=days,
            source=TimesheetSource.MANUALE,
            note=description,
            created_by=author,
            updated_by=request.user,
        )
        try:
            entry.full_clean()
            entry.save()
        except DjangoValidationError as exc:
            return Response(getattr(exc, "message_dict", {"detail": exc.messages}), status=400)
        return Response({"id": entry.id}, status=status.HTTP_201_CREATED)


class ProjectTimesheetDetailView(DocumentedAPIView):
    """Rettifica o annulla un consuntivo manuale diretto con timesheets.edit."""

    permission_classes = [CanEditTimesheets]

    @staticmethod
    def get_entry(project_pk, entry_pk):
        from timesheets.models import TimesheetEntry, TimesheetSource

        return get_object_or_404(
            TimesheetEntry,
            pk=entry_pk,
            project_id=project_pk,
            source=TimesheetSource.MANUALE,
            reversals__isnull=True,
        )

    @staticmethod
    def parse_payload(request, entry):
        from decimal import Decimal, InvalidOperation

        raw_date = request.data.get("data", entry.period.isoformat())
        try:
            days = Decimal(str(request.data.get("giornate", entry.days)))
        except InvalidOperation as exc:
            raise DjangoValidationError({"giornate": "Inserire un numero valido."}) from exc
        try:
            entry_date = date.fromisoformat(str(raw_date))
        except ValueError as exc:
            raise DjangoValidationError({"data": "Inserire una data valida."}) from exc
        description = str(request.data.get("descrizione", entry.note)).strip()
        if days <= 0:
            raise DjangoValidationError({"giornate": "Le giornate devono essere maggiori di zero."})
        if not description:
            raise DjangoValidationError({"descrizione": "La descrizione è obbligatoria."})
        if len(description) > 300:
            raise DjangoValidationError({"descrizione": "Massimo 300 caratteri."})
        return days, entry_date, description

    @transaction.atomic
    def patch(self, request, pk, entry_pk):
        from timesheets.models import TimesheetEntry, TimesheetSource

        entry = self.get_entry(pk, entry_pk)
        try:
            days, entry_date, description = self.parse_payload(request, entry)
            author = resolve_author(request, default=entry.created_by)
        except DjangoValidationError as exc:
            return Response(getattr(exc, "message_dict", {"detail": exc.messages}), status=400)
        direct_without_entry = (
            TimesheetEntry.objects.filter(project_id=pk).aggregate(total=Sum("days"))["total"] or 0
        ) - entry.days
        allocated_to_wallet = (
            entry.project.wallet_allocations.aggregate(total=Sum("allocated_days"))["total"] or 0
        )
        if days > entry.project.budget_days - direct_without_entry - allocated_to_wallet:
            return Response(
                {"giornate": ["Le giornate superano il residuo diretto del progetto."]}, status=400
            )
        reversal = entry.build_reversal(note=f"Rettifica amministrativa del consuntivo {entry.id}")
        reversal.created_by = request.user
        reversal.updated_by = request.user
        reversal.full_clean()
        reversal.save()
        replacement = TimesheetEntry(
            project=entry.project,
            period=entry_date,
            days=days,
            source=TimesheetSource.MANUALE,
            note=description,
            created_by=author,
            updated_by=request.user,
        )
        replacement.full_clean()
        replacement.save()
        return Response({"id": replacement.id})

    @transaction.atomic
    def delete(self, request, pk, entry_pk):
        entry = self.get_entry(pk, entry_pk)
        reversal = entry.build_reversal(
            note=f"Eliminazione amministrativa del consuntivo {entry.id}"
        )
        reversal.created_by = request.user
        reversal.updated_by = request.user
        reversal.full_clean()
        reversal.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectReviewQueueView(DocumentedAPIView):
    """Coda di revisione progetti: 3 CHIUSO senza data + 9 DA_VERIFICARE (D-03)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request):
        from datetime import date

        from domain.residuals import review_queue_projects

        as_of = None
        as_of_param = request.query_params.get("as_of") or request.query_params.get(
            "reference_date"
        )
        if as_of_param:
            try:
                as_of = date.fromisoformat(as_of_param)
            except ValueError:
                pass

        items = review_queue_projects(as_of=as_of)
        return Response(
            {
                "results": items,
                "count": len(items),
                "chiuso_senza_data_count": sum(
                    1 for x in items if x["tipo_revisione"] == "CHIUSO_SENZA_DATA"
                ),
                "da_verificare_count": sum(
                    1 for x in items if x["tipo_revisione"] == "DA_VERIFICARE"
                ),
            }
        )


class AnomalyListView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from anomalies.models import Anomaly

        rows = Anomaly.objects.select_related("project", "superseded_by").order_by(
            "-detected_at", "external_ref"
        )
        if request.query_params.get("stato"):
            rows = rows.filter(status=request.query_params["stato"])
        if request.query_params.get("regola"):
            rows = rows.filter(rule_code=request.query_params["regola"])
        return Response(
            {
                "results": [
                    {
                        "id": row.id,
                        "external_ref": row.external_ref,
                        "codice_regola": row.rule_code,
                        "severita": row.severity,
                        "ambito": row.scope,
                        "descrizione": row.description,
                        "stato": row.status,
                        "progetto": row.project.code if row.project else None,
                        "contesto": row.context,
                        "azione_suggerita": row.suggested_action,
                        "nota_risoluzione": row.resolution_note,
                        "sostituita_da": (
                            row.superseded_by.rule_code if row.superseded_by else None
                        ),
                    }
                    for row in rows
                ]
            }
        )


class ChecksRunView(DocumentedAPIView):
    permission_classes = [ReadOnlyOrLedgerWriter]

    @extend_schema(request=DomainResponseSerializer, responses={200: DomainResponseSerializer})
    def post(self, request):
        from datetime import date

        from anomalies.runner import run_checks

        rules = request.data.get("regole")
        as_of_val = None
        as_of_str = request.data.get("as_of") or request.query_params.get("as_of")
        if as_of_str:
            try:
                as_of_val = date.fromisoformat(str(as_of_str))
            except ValueError:
                pass
        report = run_checks(rules if isinstance(rules, list) else None, as_of=as_of_val)
        return Response(report.as_dict())


class AnomalyActionView(DocumentedAPIView):
    permission_classes = [CanResolveAnomalies]

    @extend_schema(request=DomainResponseSerializer, responses={200: DomainResponseSerializer})
    def post(self, request, pk, action: str):
        from django.utils.dateparse import parse_date

        from anomalies.models import Anomaly, AnomalyStatus

        anomaly = get_object_or_404(Anomaly, pk=pk)
        note = str(request.data.get("nota", "")).strip()
        if action == "take":
            anomaly.status = AnomalyStatus.IN_VERIFICA
            anomaly.assigned_to = request.user
        elif action == "resolve":
            anomaly.resolve(note, request.user)
        elif action == "accept":
            anomaly.accept(note, parse_date(str(request.data.get("fino_al", ""))), request.user)
        else:
            return Response({"detail": "Azione non valida."}, status=status.HTTP_400_BAD_REQUEST)
        anomaly.save()
        return Response({"id": anomaly.id, "stato": anomaly.status})


class WalletBalanceView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, year: int):
        settings_obj = current_settings()
        balance = wallet_year_balance(
            year,
            years_valid_after_closure=settings_obj.residual_years_after_closure,
            expiring_window_days=settings_obj.residual_expiring_window_days,
        )
        return Response(balance.as_dict())


class ReleaseProjectToWalletView(DocumentedAPIView):
    """Endpoint legacy disabilitato: un progetto attivo non genera credito wallet."""

    permission_classes = [ReadOnlyOrLedgerWriter]

    def post(self, request, pk):
        return Response(
            {
                "detail": (
                    "Operazione non più consentita: il residuo entra nel wallet soltanto "
                    "alla chiusura del progetto con data effettiva."
                ),
                "code": "PROJECT_WALLET_RELEASE_DEPRECATED",
            },
            status=status.HTTP_409_CONFLICT,
        )


class WalletFlowView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, year: int):
        return Response({"results": wallet_flow(year)})


class WalletAssigneeSummaryView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, year: int):
        return Response({"results": wallet_by_assignee(year)})


class WalletAllocationCreateView(DocumentedAPIView):
    permission_classes = [CanEditWallet]

    @extend_schema(request=dict, responses={201: dict})
    @transaction.atomic
    def post(self, request):
        import re
        import uuid

        from directory.models import Person
        from domain.money import ZERO, to_days
        from domain.wallet_balance import wallet_year_balance
        from wallet.models import ActivityKind, WalletActivity, WalletAllocation, WalletYear
        from wallet.services import reserve_fifo

        required = ("year", "assignee", "allocated_days")
        missing = [field for field in required if request.data.get(field) in (None, "")]
        if missing:
            raise serializers.ValidationError(dict.fromkeys(missing, "Campo obbligatorio."))

        activity_id = request.data.get("activity")
        new_activity_title = request.data.get("new_activity_title") or request.data.get(
            "activity_title"
        )
        if not activity_id and not new_activity_title:
            raise serializers.ValidationError({"activity": "Attività obbligatoria."})

        try:
            requested_year = int(request.data["year"])
            assignee = Person.objects.get(pk=request.data["assignee"], is_active=True)
            allocated_days = to_days(request.data["allocated_days"])
        except Person.DoesNotExist as exc:
            raise serializers.ValidationError({"assignee": "Assegnatario non valido."}) from exc
        except (ValueError, TypeError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        if allocated_days <= 0:
            raise serializers.ValidationError({"allocated_days": "Deve essere maggiore di zero."})

        activity = None
        if activity_id:
            activity = WalletActivity.objects.filter(pk=activity_id).first()

        if activity is None:
            title = (new_activity_title or str(activity_id)).strip()
            if not title:
                raise serializers.ValidationError({"activity": "Titolo attività non valido."})
            activity = WalletActivity.objects.filter(title__iexact=title).first()
            if activity is None:
                clean_title = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").upper()
                base_code = (
                    f"ACT-{clean_title}"[:50]
                    if clean_title
                    else f"ACT-{uuid.uuid4().hex[:8].upper()}"
                )
                code = base_code
                while WalletActivity.objects.filter(code=code).exists():
                    code = f"{base_code[:40]}-{uuid.uuid4().hex[:6].upper()}"
                activity = WalletActivity.objects.create(
                    code=code,
                    title=title,
                    kind=ActivityKind.ATTIVITA,
                )

        if request.data.get("source_project"):
            raise serializers.ValidationError(
                {
                    "source_project": (
                        "La fonte non è selezionabile manualmente: il prelievo segue sempre "
                        "il FIFO dei lotti wallet."
                    )
                }
            )
        settings_obj = current_settings()
        balance = wallet_year_balance(
            requested_year,
            years_valid_after_closure=settings_obj.residual_years_after_closure,
            expiring_window_days=settings_obj.residual_expiring_window_days,
        )
        if allocated_days > balance.unallocated_capacity:
            raise serializers.ValidationError(
                {
                    "allocated_days": (
                        f"Giornate richieste {allocated_days} superiori al residuo non allocato "
                        f"del monte wallet ({balance.unallocated_capacity} gg)."
                    )
                }
            )
        available_after = max(ZERO, balance.unallocated_capacity - allocated_days)

        wallet_year, _ = WalletYear.objects.get_or_create(year=requested_year)
        allocation = WalletAllocation(
            wallet_year=wallet_year,
            source_project=None,
            activity=activity,
            assignee=assignee,
            allocated_days=allocated_days,
            initial_allocated_days=allocated_days,
            notes=str(request.data.get("notes", "")),
            external_ref=str(request.data.get("external_ref", "")),
        )
        allocation.full_clean()
        allocation.save()
        try:
            funding = reserve_fifo(allocation, allocated_days)
        except ValueError as exc:
            raise serializers.ValidationError({"allocated_days": str(exc)}) from exc

        origin_label = "Monte Wallet FIFO"
        _audit_mutation(
            request,
            "wallet_allocation.create",
            "wallet_allocation",
            allocation.id,
            allocation.external_ref or f"{origin_label} → {activity.code}",
            {
                "year": requested_year,
                "source_project": None,
                "fonti_fifo": [tranche.source_lot.source_project.code for tranche in funding],
                "activity": activity.code,
                "allocated_days": str(allocated_days),
                "version": allocation.version,
            },
        )
        return Response(
            {
                "id": str(allocation.id),
                "version": allocation.version,
                "year": requested_year,
                "source_project": None,
                "source_project_code": "Monte Wallet FIFO",
                "funding": [
                    {
                        "source_project_code": tranche.source_lot.source_project.code,
                        "days": str(tranche.committed_days),
                        "sequence": tranche.sequence,
                    }
                    for tranche in funding
                ],
                "activity": str(activity.id),
                "activity_code": activity.code,
                "assignee": str(assignee.id),
                "architetto": assignee.full_name,
                "allocated_days": str(allocation.allocated_days),
                "available_source_after": str(available_after),
            },
            status=status.HTTP_201_CREATED,
            headers={"ETag": make_etag(allocation)},
        )


class WalletAllocationOptionsView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
        from django.db.models.functions import Coalesce
        from django.utils import timezone

        from directory.models import Person
        from domain.money import ZERO
        from projects.models import Project, TimesheetStatus
        from timesheets.models import TimesheetEntry
        from wallet.models import WalletActivity, WalletAllocation

        days_field = DecimalField(max_digits=12, decimal_places=4)
        direct = (
            TimesheetEntry.objects.filter(project=OuterRef("pk"))
            .order_by()
            .values("project")
            .annotate(total=Sum("days", output_field=days_field))
            .values("total")[:1]
        )
        allocated = (
            WalletAllocation.objects.filter(source_project=OuterRef("pk"))
            .order_by()
            .values("source_project")
            .annotate(total=Sum("allocated_days", output_field=days_field))
            .values("total")[:1]
        )
        zero = Value(ZERO, output_field=days_field)
        settings_obj = current_settings()
        today = timezone.localdate()
        project_rows = list(
            Project.objects.filter(
                timesheet_status=TimesheetStatus.CHIUSO,
                actual_closure_date__isnull=False,
            )
            .annotate(
                direct_days=Coalesce(Subquery(direct, output_field=days_field), zero),
                allocated_days=Coalesce(Subquery(allocated, output_field=days_field), zero),
            )
            .annotate(available_days=F("budget_days") - F("direct_days") - F("allocated_days"))
            .order_by("code")
        )
        projects = []
        for row in project_rows:
            validity = residual_validity(
                timesheet_status=row.timesheet_status,
                closure_date=row.actual_closure_date,
                today=today,
                years_valid_after_closure=settings_obj.residual_years_after_closure,
                expiring_window_days=settings_obj.residual_expiring_window_days,
            )
            projects.append(
                {
                    "id": row.id,
                    "code": row.code,
                    "title": row.title,
                    "year": row.actual_closure_date.year if row.actual_closure_date else None,
                    "available_days": str(row.available_days if validity.usable else ZERO),
                    "validity": validity.state,
                    "expires_on": validity.expires_on.isoformat() if validity.expires_on else None,
                    "usable": validity.usable,
                }
            )

        year_param = request.query_params.get("year")
        try:
            year_val = int(year_param) if year_param else today.year
        except (ValueError, TypeError):
            year_val = today.year
        from domain.wallet_balance import wallet_year_balance

        balance = wallet_year_balance(
            year_val,
            years_valid_after_closure=settings_obj.residual_years_after_closure,
            expiring_window_days=settings_obj.residual_expiring_window_days,
        )
        return Response(
            {
                "projects": projects,
                "activities": [
                    {"id": row.id, "code": row.code, "title": row.title}
                    for row in WalletActivity.objects.order_by("code")
                ],
                "assignees": [
                    {"id": row.id, "name": row.full_name, "full_name": row.full_name}
                    for row in Person.objects.order_by("full_name")
                ],
                "architects": [
                    {"id": row.id, "name": row.full_name, "full_name": row.full_name}
                    for row in Person.objects.order_by("full_name")
                ],
                "unallocated_capacity": str(balance.unallocated_capacity),
                "potential_wallet_capacity": str(balance.potential_wallet_capacity),
            }
        )


CANONE_DAYS = DecimalField(max_digits=12, decimal_places=4)


class CanoneDeleteBlocked(DomainError):
    error_code = "canone-delete-bloccata"
    default_detail = (
        "Il canone non può essere eliminato perché conserva consuntivi o provenienza import."
    )


def _canone_state(total, consumed) -> str:
    if consumed <= 0:
        return "NON_AVVIATO"
    if consumed > total:
        return "SUPERATO"
    if consumed == total:
        return "COMPLETATO"
    return "IN_CORSO"


def _canone_row(row) -> dict:
    consumed = row.consumed_days
    return {
        "id": row.id,
        "version": row.version,
        "semestre": row.semester,
        "periodicita": row.periodicity,
        "nome": row.name,
        "pianificato": row.total_days,
        "riservato": row.reserved_days,
        "disponibile": row.total_days - row.reserved_days,
        "consuntivato": consumed,
        "residuo": row.total_days - consumed,
        "stato": _canone_state(row.total_days, consumed),
        "sottoattivita_count": row.subactivity_count,
        "ultimo_movimento": row.last_movement,
    }


def _canone_queryset():
    reserved = (
        CanoneSubactivity.objects.filter(canone=OuterRef("pk"))
        .order_by()
        .values("canone")
        .annotate(total=Sum("reserved_days", output_field=CANONE_DAYS))
        .values("total")[:1]
    )
    return (
        Canone.objects.select_related("project")
        .annotate(
            consumed_days=Coalesce(
                Sum("subactivities__timesheet_entries__days"),
                Value(0, output_field=CANONE_DAYS),
            ),
            reserved_days=Coalesce(
                Subquery(reserved, output_field=CANONE_DAYS),
                Value(0, output_field=CANONE_DAYS),
            ),
            subactivity_count=Count("subactivities", distinct=True),
            last_movement=Max("subactivities__timesheet_entries__period"),
        )
        .order_by("-semester", "name")
    )


def _audit_canone(request, action: str, target, details=None) -> None:
    AdminAuditEvent.objects.create(
        actor=request.user,
        actor_username=request.user.username,
        action=action,
        target_type=target.__class__.__name__.lower(),
        target_id=str(target.pk),
        target_label=str(target)[:150],
        details=details or {},
    )


class CanoneListView(DocumentedAPIView):
    """Lista aggregata e creazione dell'Organico Allargato."""

    permission_classes = [ReadOnlyOrCanManageCanone]

    @extend_schema(responses={200: dict})
    def get(self, request):
        rows = list(_canone_queryset())
        if request.query_params.get("management") != "1":
            last_moved = max(
                (row for row in rows if row.last_movement is not None),
                key=lambda row: (row.last_movement, row.semester),
                default=None,
            )
            default_canone = last_moved or (rows[0] if rows else None)
            return Response(
                {
                    "results": [
                        {
                            "id": row.id,
                            "semestre": row.semester,
                            "nome": row.name,
                            "ultimo_movimento": row.last_movement,
                        }
                        for row in rows
                    ],
                    "count": len(rows),
                    "default_canone_id": default_canone.id if default_canone else None,
                }
            )
        semester = request.query_params.get("semester") or request.query_params.get("semestre")
        search = (request.query_params.get("search") or "").strip()
        state = (
            request.query_params.get("state") or request.query_params.get("stato") or ""
        ).upper()
        office = (request.query_params.get("office") or request.query_params.get("dominio") or "").upper()
        if semester:
            rows = [row for row in rows if row.semester == semester]
        if search:
            needle = search.casefold()
            rows = [
                row
                for row in rows
                if needle in row.name.casefold()
                or needle in row.semester.casefold()
            ]
        if state:
            rows = [
                row for row in rows if _canone_state(row.total_days, row.consumed_days) == state
            ]
        if office:
            rows = [row for row in rows if row.subactivities.filter(office=office).exists()]
            for row in rows:
                row.subactivity_count = row.subactivities.filter(office=office).count()
        all_rows = list(_canone_queryset())
        target_rows = rows if rows else all_rows
        last_moved = max(
            (row for row in target_rows if row.last_movement is not None),
            key=lambda row: (row.last_movement, row.semester),
            default=None,
        )
        default_canone = last_moved or (target_rows[0] if target_rows else None)
        return Response(
            {
                "results": [_canone_row(row) for row in rows],
                "count": len(rows),
                "default_canone_id": default_canone.id if default_canone else None,
                "summary": {
                    "pianificato": sum((row.total_days for row in rows), 0),
                    "riservato": sum((row.reserved_days for row in rows), 0),
                    "disponibile": sum((row.total_days - row.reserved_days for row in rows), 0),
                    "consuntivato": sum((row.consumed_days for row in rows), 0),
                    "residuo": sum((row.total_days - row.consumed_days for row in rows), 0),
                    "sottoattivita": sum((row.subactivity_count for row in rows), 0),
                },
                "filters": {
                    "semestri": sorted({row.semester for row in all_rows}, reverse=True),
                    "stati": ["NON_AVVIATO", "IN_CORSO", "COMPLETATO", "SUPERATO"],
                    "domini": ["EA", "TA", "SA", "CROSS"],
                },
            }
        )

    @transaction.atomic
    def post(self, request):
        serializer = CanoneWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        canone = serializer.save()
        _audit_canone(request, "canone.create", canone, {"version": canone.version})
        return Response(_canone_detail(canone), status=status.HTTP_201_CREATED)


class CanoneDetailView(DocumentedAPIView):
    permission_classes = [ReadOnlyOrCanManageCanone]

    def get_object(self, pk):
        return get_object_or_404(Canone.objects.select_related("project"), pk=pk)

    def get(self, request, pk):
        office = (request.query_params.get("office") or request.query_params.get("dominio") or "").upper()
        search = (request.query_params.get("search") or "").strip()
        return Response(_canone_detail(self.get_object(pk), office=office, search=search))

    @transaction.atomic
    def patch(self, request, pk):
        canone = Canone.objects.select_for_update().get(pk=pk)
        check_expected_version(request, canone)
        serializer = CanoneWriteSerializer(canone, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        canone = serializer.save()
        _audit_canone(request, "canone.update", canone, {"version": canone.version})
        return Response(_canone_detail(canone))

    @transaction.atomic
    def delete(self, request, pk):
        canone = Canone.objects.select_for_update().get(pk=pk)
        check_expected_version(request, canone)
        if (
            canone.import_batch_id
            or canone.subactivities.filter(
                Q(import_batch__isnull=False) | Q(timesheet_entries__isnull=False)
            ).exists()
        ):
            raise CanoneDeleteBlocked()
        snapshot = {"semester": canone.semester, "name": canone.name}
        _audit_canone(request, "canone.delete", canone, snapshot)
        canone.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _canone_detail(canone, office: str = "", search: str = "") -> dict:
    from domain.canone_status import subactivity_state

    balance = canone_status(canone).as_dict()
    all_subactivities = list(
        canone.subactivities.annotate(
            consumed_days=Coalesce(Sum("timesheet_entries__days"), Value(0, output_field=CANONE_DAYS)),
            timesheet_count=Count("timesheet_entries"),
        ).order_by("office", "title")
    )
    filtered_subactivities = all_subactivities
    if office:
        filtered_subactivities = [s for s in filtered_subactivities if s.office.upper() == office.upper()]
    if search:
        needle = search.casefold()
        filtered_subactivities = [
            s
            for s in filtered_subactivities
            if needle in s.title.casefold()
            or needle in (s.office or "").casefold()
            or needle in (s.notes or "").casefold()
            or needle in (s.redmine_ref or "").casefold()
        ]
    subactivities = []
    for row in filtered_subactivities:
        subactivities.append(
            {
                "id": row.id,
                "version": row.version,
                "office": row.office,
                "title": row.title,
                "reserved_days": row.reserved_days,
                "start_date": row.start_date,
                "end_date": row.end_date,
                "remaining_reserved_days": row.reserved_days - row.consumed_days,
                "stato": subactivity_state(row.reserved_days, row.consumed_days),
                "redmine_ref": row.redmine_ref,
                "quarter_estimate_days": row.quarter_estimate_days,
                "forecast_remaining_days": row.forecast_remaining_days,
                "notes": row.notes,
                "needs_review": row.needs_review,
                "consuntivato": row.consumed_days,
                "timesheet_count": row.timesheet_count,
                "consuntivi": [
                    {
                        "id": entry.id,
                        "data": entry.period,
                        "giornate": entry.days,
                        "descrizione": entry.note,
                        "utente": (
                            (entry.created_by.get_full_name() or entry.created_by.username)
                            if entry.created_by else "Importazione"
                        ),
                        "utente_id": entry.created_by_id,
                        "origine": entry.source,
                    }
                    for entry in row.timesheet_entries.filter(reversals__isnull=True)
                    .exclude(source="STORNO").select_related("created_by")
                    .order_by("-period", "-created_at")
                ],
            }
        )
    return {
        "id": canone.id,
        "version": canone.version,
        "name": canone.name,
        "semester": canone.semester,
        "periodicity": canone.periodicity,
        "total_days": canone.total_days,
        "reserved_days": sum((row.reserved_days for row in all_subactivities), 0),
        "available_days": canone.total_days
        - sum((row.reserved_days for row in all_subactivities), 0),
        "target_base_days": canone.target_base_days,
        "target_days_per_week": canone.target_days_per_week,
        "weeks_elapsed_at_import": canone.weeks_elapsed_at_import,
        "cap_at_total": canone.cap_at_total,
        "start_date": canone.start_date,
        "end_date": canone.end_date,
        "extracted_at": canone.extracted_at,
        "status": balance,
        "subactivities": subactivities,
    }


class CanoneSubactivityListView(DocumentedAPIView):
    permission_classes = [ReadOnlyOrCanManageCanone]

    @transaction.atomic
    def post(self, request, pk):
        canone = get_object_or_404(Canone.objects.select_for_update(), pk=pk)
        serializer = CanoneSubactivityWriteSerializer(data=request.data, context={"canone": canone})
        serializer.is_valid(raise_exception=True)
        row = serializer.save(canone=canone)
        _audit_canone(request, "canone.subactivity.create", row, {"canone_id": str(pk)})
        return Response(_canone_detail(canone), status=status.HTTP_201_CREATED)


class CanoneSubactivityDetailView(DocumentedAPIView):
    permission_classes = [ReadOnlyOrCanManageCanone]

    @transaction.atomic
    def patch(self, request, pk, subactivity_pk):
        Canone.objects.select_for_update().get(pk=pk)
        row = CanoneSubactivity.objects.select_for_update().get(pk=subactivity_pk, canone_id=pk)
        check_expected_version(request, row)
        serializer = CanoneSubactivityWriteSerializer(
            row, data=request.data, partial=True, context={"canone": row.canone}
        )
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        _audit_canone(request, "canone.subactivity.update", row, {"version": row.version})
        return Response(_canone_detail(row.canone))

    @transaction.atomic
    def delete(self, request, pk, subactivity_pk):
        row = CanoneSubactivity.objects.select_for_update().get(pk=subactivity_pk, canone_id=pk)
        check_expected_version(request, row)
        from timesheets.models import TimesheetEntry

        if row.import_batch_id or TimesheetEntry.objects.filter(canone_subactivity=row).exists():
            raise CanoneDeleteBlocked(
                "La sotto-attività non può essere eliminata perché conserva "
                "consuntivi o provenienza import."
            )
        canone = row.canone
        _audit_canone(request, "canone.subactivity.delete", row, {"canone_id": str(pk)})
        row.delete()
        return Response(_canone_detail(canone))


class CanoneSubactivityTimesheetListView(DocumentedAPIView):
    """Inserimento dei consuntivi su un'attività del canone."""

    permission_classes = [CanCreateTimesheets]

    @transaction.atomic
    def post(self, request, pk, subactivity_pk):
        from decimal import Decimal, InvalidOperation
        from timesheets.models import TimesheetEntry, TimesheetSource

        row = get_object_or_404(
            CanoneSubactivity.objects.select_for_update(), pk=subactivity_pk, canone_id=pk
        )
        try:
            days = Decimal(str(request.data.get("giornate", "")))
        except InvalidOperation:
            return Response({"giornate": ["Inserire un numero valido."]}, status=400)
        description = str(request.data.get("descrizione", "")).strip()
        try:
            entry_date = date.fromisoformat(str(request.data.get("data", "")))
        except ValueError:
            return Response({"data": ["Inserire una data valida."]}, status=400)
        if days <= 0:
            return Response({"giornate": ["Le giornate devono essere maggiori di zero."]}, status=400)
        if not description:
            return Response({"descrizione": ["La descrizione è obbligatoria."]}, status=400)
        if row.start_date and entry_date < row.start_date or row.end_date and entry_date > row.end_date:
            return Response({"data": ["La data deve rientrare nel periodo dell'attività."]}, status=400)
        consumed = row.timesheet_entries.aggregate(total=Sum("days"))["total"] or 0
        if consumed + days > row.reserved_days:
            return Response({"giornate": ["Il consuntivo supera le giornate riservate all'attività."]}, status=400)
        try:
            author = resolve_author(request)
        except DjangoValidationError as exc:
            return Response(getattr(exc, "message_dict", {"detail": exc.messages}), status=400)
        entry = TimesheetEntry(
            canone_subactivity=row, period=entry_date, days=days,
            source=TimesheetSource.MANUALE, note=description,
            created_by=author, updated_by=request.user,
        )
        try:
            entry.full_clean()
            entry.save()
        except DjangoValidationError as exc:
            return Response(getattr(exc, "message_dict", {"detail": exc.messages}), status=400)
        return Response(_canone_detail(row.canone), status=status.HTTP_201_CREATED)


class CanoneSubactivityTimesheetDetailView(DocumentedAPIView):
    """Rettifica append-only di un consuntivo con timesheets.edit."""

    permission_classes = [CanEditTimesheets]

    def get_entry(self, pk, subactivity_pk, entry_pk):
        from timesheets.models import TimesheetEntry, TimesheetSource
        return get_object_or_404(
            TimesheetEntry, pk=entry_pk, canone_subactivity_id=subactivity_pk,
            canone_subactivity__canone_id=pk, source=TimesheetSource.MANUALE,
            reversals__isnull=True,
        )

    @transaction.atomic
    def patch(self, request, pk, subactivity_pk, entry_pk):
        from decimal import Decimal, InvalidOperation
        from timesheets.models import TimesheetEntry, TimesheetSource

        entry = self.get_entry(pk, subactivity_pk, entry_pk)
        row = entry.canone_subactivity
        try:
            days = Decimal(str(request.data.get("giornate", entry.days)))
            entry_date = date.fromisoformat(str(request.data.get("data", entry.period)))
        except (InvalidOperation, ValueError):
            return Response({"detail": "Data o giornate non valide."}, status=400)
        description = str(request.data.get("descrizione", entry.note)).strip()
        if days <= 0 or not description:
            return Response({"detail": "Giornate positive e descrizione sono obbligatorie."}, status=400)
        if row.start_date and entry_date < row.start_date or row.end_date and entry_date > row.end_date:
            return Response({"data": ["La data deve rientrare nel periodo dell'attività."]}, status=400)
        consumed_without_entry = (row.timesheet_entries.aggregate(total=Sum("days"))["total"] or 0) - entry.days
        if consumed_without_entry + days > row.reserved_days:
            return Response({"giornate": ["Il consuntivo supera le giornate riservate all'attività."]}, status=400)
        try:
            author = resolve_author(request, default=entry.created_by)
        except DjangoValidationError as exc:
            return Response(getattr(exc, "message_dict", {"detail": exc.messages}), status=400)
        reversal = entry.build_reversal(note=f"Rettifica amministrativa del consuntivo {entry.id}")
        reversal.created_by = request.user
        reversal.updated_by = request.user
        reversal.full_clean()
        reversal.save()
        replacement = TimesheetEntry(
            canone_subactivity=row, period=entry_date, days=days,
            source=TimesheetSource.MANUALE, note=description,
            created_by=author, updated_by=request.user,
        )
        replacement.full_clean()
        replacement.save()
        return Response(_canone_detail(row.canone))

    @transaction.atomic
    def delete(self, request, pk, subactivity_pk, entry_pk):
        entry = self.get_entry(pk, subactivity_pk, entry_pk)
        reversal = entry.build_reversal(note=f"Eliminazione amministrativa del consuntivo {entry.id}")
        reversal.created_by = request.user
        reversal.updated_by = request.user
        reversal.full_clean()
        reversal.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommandSearchView(DocumentedAPIView):
    """Ricerca globale leggera per la command palette."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request):
        from django.db.models import Q

        from anomalies.models import Anomaly
        from projects.models import Project
        from wallet.models import WalletActivity

        query = str(request.query_params.get("q", "")).strip()
        if len(query) < 2:
            return Response({"results": []})
        projects = Project.objects.filter(Q(code__icontains=query) | Q(title__icontains=query))[:8]
        activities = WalletActivity.objects.filter(
            Q(code__icontains=query) | Q(title__icontains=query)
        )[:8]
        anomalies = Anomaly.objects.filter(
            Q(external_ref__icontains=query) | Q(description__icontains=query)
        )[:8]
        results = [
            {
                "tipo": "progetto",
                "id": row.id,
                "codice": row.code,
                "titolo": row.title,
                "url": f"/progetti/{row.id}",
            }
            for row in projects
        ]
        results.extend(
            {
                "tipo": "attivita_wallet",
                "id": row.id,
                "codice": row.code,
                "titolo": row.title,
                "url": "/wallet",
            }
            for row in activities
        )
        results.extend(
            {
                "tipo": "anomalia",
                "id": row.id,
                "codice": row.external_ref or row.rule_code,
                "titolo": row.description,
                "url": "/anomalie",
            }
            for row in anomalies
        )
        return Response({"results": results})


class ExportJsonView(DocumentedAPIView):
    permission_classes = [CanExport]

    def get(self, request):
        from exporters import export_json_bytes

        return HttpResponse(
            export_json_bytes(),
            content_type="application/json; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="supplier-ledger-1.0.0.json"'},
        )


class ExportCsvView(DocumentedAPIView):
    permission_classes = [CanExport]

    def get(self, request, entity: str):
        from exporters import export_csv_bytes

        try:
            data = export_csv_bytes(entity)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return HttpResponse(
            data,
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{entity}-1.0.0.csv"'},
        )


class ExportExcelView(DocumentedAPIView):
    permission_classes = [CanExport]

    def get(self, request):
        from exporters import export_excel_bytes

        return HttpResponse(
            export_excel_bytes(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="supplier-ledger-1.0.0.xlsx"'},
        )


class CanoneStatusView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request, pk):
        canone = get_object_or_404(Canone, pk=pk)
        status_data = canone_status(canone).as_dict()
        status_data["burndown"] = canone_burndown(canone)
        return Response(status_data)


class ReconciliationView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        settings_obj = current_settings()
        tolerance = settings_obj.reconciliation_tolerance_days
        rows = reconcile(tolerance=tolerance)
        return Response(
            {
                "riepilogo": reconciliation_summary(tolerance, rows=rows),
                "tolleranza": tolerance,
                "results": [
                    {**row.as_dict(), "spiegazione": row.explanation}
                    for row in rows
                    if row.internal_days or not row.missing_in_ppm
                ],
            }
        )


class ProjectDeleteBlocked(DomainError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "project-delete-bloccata"
    default_detail = "Il progetto non può essere eliminato perché conserva dipendenze operative."


def _project_delete_dependencies(project) -> list[dict[str, object]]:
    checks = (
        (
            "milestone",
            "milestone di fatturazione",
            project.milestones.filter(schedule_slot=""),
        ),
        ("consuntivi", "consuntivi progetto", project.timesheet_entries),
        ("allocazioni_origine", "allocazioni wallet originate", project.wallet_allocations),
        ("attivita_wallet", "attività wallet collegate", project.wallet_activities),
        ("canoni", "canoni e sotto-attività", project.canoni),
        ("ppm", "righe PPM associate", project.ppm_rows),
        ("anomalie", "anomalie associate", project.anomalies),
    )
    return [
        {"categoria": code, "descrizione": label, "conteggio": manager.count()}
        for code, label, manager in checks
        if manager.exists()
    ]


def _audit_mutation(request, action: str, target_type: str, target_id, label: str, details) -> None:
    AdminAuditEvent.objects.create(
        actor=request.user,
        actor_username=request.user.get_username(),
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        target_label=label[:150],
        details=details,
    )


def project_detail_payload(project, user) -> dict:
    """Anagrafica persistita modificabile, senza campi tecnici, import o valori calcolati."""
    can_edit = capabilities.has_capability(user, capabilities.EDIT_PROJECTS)
    can_annotate = ReferentCanAnnotate.can_annotate(user, project)
    return {
        "id": project.id,
        "code": project.code,
        "title": project.title,
        "contract_type": project.contract_type,
        "aro_code": project.aro_code,
        "rda_code": project.rda_code,
        "deliverable": project.deliverable,
        "client_owner": project.client_owner_id,
        "client_owner_name": project.client_owner.full_name if project.client_owner else None,
        "supplier_owner": project.supplier_owner_id,
        "supplier_owner_name": project.supplier_owner.full_name if project.supplier_owner else None,
        "billing_milestones": [
            {
                "id": str(milestone.id),
                "slot": milestone.schedule_slot,
                "planned_date": milestone.planned_date.isoformat()
                if milestone.planned_date
                else None,
                "status": milestone.status,
                "amount_days": str(milestone.amount_days)
                if milestone.amount_days is not None
                else None,
            }
            for milestone in project.milestones.all()
        ],
        "budget_days": str(project.budget_days),
        "start_date": str(project.start_date) if project.start_date else None,
        "planned_end_date": str(project.planned_end_date) if project.planned_end_date else None,
        "actual_closure_date": (
            str(project.actual_closure_date) if project.actual_closure_date else None
        ),
        "offer_status": project.offer_status,
        "timesheet_status": project.timesheet_status,
        "billing_status": project.billing_status,
        "notes": project.notes,
        "reliability": project.reliability,
        "verification_points": project.verification_points,
        "version": project.version,
        "permissions": {
            "edit": can_edit,
            "delete": can_edit,
            "annotate": can_annotate,
            "editable_fields": sorted(
                PROJECT_EDITABLE_FIELDS if can_edit else PROJECT_ANNOTATION_FIELDS
            ),
        },
        "readonly": {
            "code": "Il codice è bloccato perché può essere referenziato da import e ledger.",
        },
    }


class ProjectDetailUpdateView(DocumentedAPIView):
    def get_permissions(self):
        if self.request.method == "DELETE":
            return [CanEditProjects()]
        return [ReferentCanAnnotate()]

    def get_object(self, pk, *, for_update=False):
        from projects.models import Project

        queryset = Project.objects.select_related("client_owner", "supplier_owner")
        if for_update:
            queryset = queryset.select_for_update(of=("self",))
        obj = get_object_or_404(queryset, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(operation_id="project_detail", responses={200: dict})
    def get(self, request, pk):
        project = self.get_object(pk)
        return Response(
            project_detail_payload(project, request.user), headers={"ETag": make_etag(project)}
        )

    @extend_schema(request=ProjectUpdateSerializer, responses={200: dict})
    @transaction.atomic
    def patch(self, request, pk):
        from projects.billing import sync_project_billing_schedule

        project = self.get_object(pk)
        check_expected_version(request, project)
        supplied_fields = set(request.data) - PROJECT_CONTROL_FIELDS
        allowed_fields = (
            PROJECT_EDITABLE_FIELDS
            if capabilities.has_capability(request.user, capabilities.EDIT_PROJECTS)
            else PROJECT_ANNOTATION_FIELDS
        )
        forbidden = supplied_fields - allowed_fields
        if forbidden:
            raise serializers.ValidationError(
                dict.fromkeys(forbidden, "Campo non modificabile per il ruolo corrente.")
            )
        serializer = ProjectUpdateSerializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        sync_project_billing_schedule(project, user=request.user)
        # Chiudere un progetto conferisce il suo residuo al wallet: senza il lotto la
        # capienza resterebbe solo calcolata e il FIFO non troverebbe nulla da prelevare.
        ensure_source_lot(project)
        return Response(
            project_detail_payload(project, request.user), headers={"ETag": make_etag(project)}
        )

    @transaction.atomic
    def delete(self, request, pk):
        project = self.get_object(pk, for_update=True)
        check_expected_version(request, project)
        dependencies = _project_delete_dependencies(project)
        if project.import_batch_id:
            dependencies.insert(
                0,
                {
                    "categoria": "import",
                    "descrizione": "progetto proveniente da import",
                    "conteggio": 1,
                },
            )
        if dependencies:
            summary = "; ".join(
                f"{item['descrizione']} ({item['conteggio']})" for item in dependencies
            )
            raise ProjectDeleteBlocked(
                detail=f"Eliminazione bloccata: {summary}.", dipendenze=dependencies
            )
        snapshot = {
            "code": project.code,
            "title": project.title,
            "contract_type": project.contract_type,
            "budget_days": str(project.budget_days),
            "version": project.version,
        }
        project_id = project.id
        project_code = project.code
        _audit_mutation(
            request, "project.delete", "project", project_id, project_code, {"snapshot": snapshot}
        )
        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectFormOptionsView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="project_form_options", responses={200: dict})
    def get(self, request):
        from core.models import Reliability
        from directory.models import Organization, Person
        from projects.models import BillingStatus, ContractType, OfferStatus, TimesheetStatus

        def choices(values):
            return [{"value": value, "label": label} for value, label in values]

        organizations = Organization.objects.order_by("kind", "name")
        people = Person.objects.filter(is_active=True).select_related("organization")
        return Response(
            {
                "contract_types": choices(ContractType.choices),
                "offer_statuses": choices(OfferStatus.choices),
                "timesheet_statuses": choices(TimesheetStatus.choices),
                "billing_statuses": choices(BillingStatus.choices),
                "reliabilities": choices(Reliability.choices),
                "organizations": [
                    {"id": item.id, "code": item.code, "name": item.name, "kind": item.kind}
                    for item in organizations
                ],
                "people": [
                    {
                        "id": item.id,
                        "name": item.full_name,
                        "organization_id": item.organization_id,
                        "organization_kind": item.organization.kind,
                    }
                    for item in people
                ],
            }
        )


class ProjectConfirmReviewView(DocumentedAPIView):
    permission_classes = [ReadOnlyOrLedgerWriter]

    @extend_schema(request=dict, responses={200: dict})
    def post(self, request, pk):
        from datetime import date

        from projects.models import Project

        project = get_object_or_404(Project, pk=pk)
        if "timesheet_status" in request.data:
            project.timesheet_status = request.data["timesheet_status"]
        if "actual_closure_date" in request.data:
            val = request.data["actual_closure_date"]
            project.actual_closure_date = date.fromisoformat(val) if val else None
        project.full_clean()
        project.save()
        if project.actual_closure_date:
            from anomalies.models import Anomaly, AnomalyStatus

            for a in Anomaly.objects.filter(
                project=project, rule_code="CHK_CLOSED_NO_DATE", status=AnomalyStatus.APERTA
            ):
                a.resolve("Data di chiusura confermata dalla coda di revisione.", request.user)
                a.save()
            ensure_source_lot(project)
        return Response(
            {
                "id": project.id,
                "timesheet_status": project.timesheet_status,
                "actual_closure_date": str(project.actual_closure_date),
            }
        )


class ProjectValidateClosureView(DocumentedAPIView):
    permission_classes = [CanValidateProjectClosure]

    @transaction.atomic
    @extend_schema(request=dict, responses={200: dict})
    def post(self, request, pk):
        from domain.residuals import project_closure_ready
        from projects.models import Project, TimesheetStatus
        from wallet.models import SourceLotStatus

        project = get_object_or_404(
            Project.objects.select_for_update().prefetch_related(
                "wallet_allocations", "wallet_source_lots"
            ),
            pk=pk,
        )
        check_expected_version(request, project)
        if not project_closure_ready(project):
            raise serializers.ValidationError(
                {
                    "status": (
                        "Il progetto non è in chiusura da validare: deve avere almeno una quota "
                        "wallet e tutte le quote devono essere chiuse."
                    )
                }
            )

        project.timesheet_status = TimesheetStatus.CHIUSO
        project.actual_closure_date = timezone.localdate()
        project.full_clean()
        project.save()
        project.wallet_source_lots.filter(status=SourceLotStatus.CHIUSURA_DA_VALIDARE).update(
            status=SourceLotStatus.CHIUSO
        )
        ensure_source_lot(project)
        _audit_mutation(
            request,
            "project.closure.validate",
            "project",
            project.id,
            project.code,
            {
                "timesheet_status": project.timesheet_status,
                "actual_closure_date": project.actual_closure_date.isoformat(),
                "version": project.version,
            },
        )
        return Response(
            {
                "id": str(project.id),
                "version": project.version,
                "stato_operativo": "CHIUSO",
                "timesheet_status": project.timesheet_status,
                "actual_closure_date": project.actual_closure_date.isoformat(),
            },
            headers={"ETag": make_etag(project)},
        )


def update_wallet_allocation(request, alloc, data: dict, *, enforce_version: bool = True):
    from django.core.exceptions import PermissionDenied
    from django.db import transaction
    from django.db.models import Sum
    from django.utils import timezone
    from rest_framework import serializers

    from core import capabilities
    from core.exceptions import InsufficientResidual
    from directory.models import Person
    from domain.money import ZERO, to_days
    from domain.wallet_balance import available_residual_for_allocation
    from timesheets.models import TimesheetEntry, TimesheetSource, month_start
    from wallet.models import AllocationStatus
    from wallet.services import close_allocation, resize_allocation, sync_allocation_funding

    if enforce_version:
        check_expected_version(request, alloc)
    elif request.headers.get("If-Match") or data.get("expected_version") is not None:
        check_expected_version(request, alloc)

    # Identifica se la richiesta tocca i consuntivi contabili
    has_timesheet_adjust = any(
        k in data
        for k in (
            "adjust_timesheet",
            "timesheet_adjustment",
            "timesheet_days",
            "adjust_consumed_to",
            "adjust_consumed_days",
            "reversal_entry_id",
            "timesheet_reversal_id",
            "reversal_entry_ids",
            "new_timesheet_entry",
        )
    )

    if has_timesheet_adjust:
        if not (
            capabilities.has_capability(request.user, capabilities.ADJUST_ACCOUNTING)
            or capabilities.has_capability(request.user, capabilities.EDIT_TIMESHEETS)
        ):
            raise PermissionDenied(
                "La rettifica dei consuntivi richiede timesheets.edit oppure accounting.adjust."
            )

    released_days = ZERO
    funded_new_allocated = None
    with transaction.atomic():
        previous_status = alloc.status
        # 1. Modifica giorni allocati
        allocated_key = None
        if "allocated_days" in data:
            allocated_key = "allocated_days"
        elif "days_allocated" in data:
            allocated_key = "days_allocated"

        if allocated_key is not None:
            new_allocated = to_days(data[allocated_key])
            if new_allocated < ZERO:
                raise serializers.ValidationError(
                    {allocated_key: "Le giornate non possono essere negative."}
                )

            # Validazione capienza del residuo del progetto sorgente (se allocazione da progetto)
            if alloc.source_project_id is not None:
                available = available_residual_for_allocation(
                    alloc.source_project_id, exclude_allocation_id=alloc.id
                )
                if new_allocated > available:
                    raise InsufficientResidual(
                        f"Le giornate richieste ({new_allocated}) superano il residuo disponibile "
                        f"del progetto di origine ({available} gg)."
                    )

            # Consuntivato attuale
            current_consumed = (
                TimesheetEntry.objects.filter(wallet_allocation=alloc).aggregate(total=Sum("days"))[
                    "total"
                ]
                or ZERO
            )
            if not has_timesheet_adjust and new_allocated < current_consumed:
                raise serializers.ValidationError(
                    {
                        allocated_key: (
                            f"Le giornate allocate ({new_allocated}) non possono essere inferiori "
                            f"a quelle già consuntivate ({current_consumed})."
                        )
                    }
                )

            if alloc.funding_tranches.exists():
                funded_new_allocated = new_allocated
            else:
                alloc.allocated_days = new_allocated

        # 2. Architetto assegnatario
        if "assignee" in data or "assignee_id" in data:
            assignee_val = data.get("assignee") if "assignee" in data else data.get("assignee_id")
            if assignee_val in (None, ""):
                alloc.assignee = None
            else:
                try:
                    alloc.assignee = Person.objects.get(pk=assignee_val)
                except (Person.DoesNotExist, ValueError) as err:
                    raise serializers.ValidationError(
                        {"assignee": "Architetto assegnatario non valido."}
                    ) from err

        # 3. Note / descrizione
        if "notes" in data:
            alloc.notes = data["notes"] or ""
        elif "description" in data:
            alloc.notes = data["description"] or ""

        if "activity_notes" in data and alloc.activity:
            alloc.activity.notes = data["activity_notes"] or ""
            alloc.activity.save(update_fields=["notes"])

        # 4. Stato
        if "status" in data:
            alloc.status = data["status"]

        # 5. Rettifica consuntivi append-only (storno + nuova emissione)
        if has_timesheet_adjust:
            reversal_ids = []
            if "reversal_entry_ids" in data and isinstance(data["reversal_entry_ids"], list):
                reversal_ids = data["reversal_entry_ids"]
            elif data.get("reversal_entry_id"):
                reversal_ids = [data["reversal_entry_id"]]
            elif data.get("timesheet_reversal_id"):
                reversal_ids = [data["timesheet_reversal_id"]]
            elif "adjust_timesheet" in data and isinstance(data["adjust_timesheet"], dict):
                adj = data["adjust_timesheet"]
                if adj.get("reversal_entry_id"):
                    reversal_ids = [adj["reversal_entry_id"]]

            reversal_note = (
                data.get("reversal_note") or f"Rettifica consuntivo allocazione {alloc.id}"
            )

            for r_id in reversal_ids:
                entry = get_object_or_404(TimesheetEntry, pk=r_id, wallet_allocation=alloc)
                rev = entry.build_reversal(note=reversal_note)
                rev.save()

            # Eventuale nuova entry esplicita
            new_entry_data = data.get("new_timesheet_entry")
            if (
                not new_entry_data
                and "adjust_timesheet" in data
                and isinstance(data["adjust_timesheet"], dict)
            ):
                adj = data["adjust_timesheet"]
                if "new_days" in adj:
                    new_entry_data = {
                        "days": adj["new_days"],
                        "period": adj.get("new_period"),
                        "note": adj.get("new_note", "Nuova registrazione consuntivo dopo storno"),
                    }

            if new_entry_data and isinstance(new_entry_data, dict) and new_entry_data.get("days"):
                days_val = to_days(new_entry_data["days"])
                if days_val != ZERO:
                    period_val = new_entry_data.get("period")
                    if period_val:
                        from datetime import date

                        if isinstance(period_val, str):
                            period_val = date.fromisoformat(period_val)
                        period_val = month_start(period_val)
                    else:
                        period_val = month_start(timezone.now().date())
                    TimesheetEntry.objects.create(
                        wallet_allocation=alloc,
                        period=period_val,
                        days=days_val,
                        source=TimesheetSource.MANUALE,
                        note=new_entry_data.get("note", "Registrazione rettifica consuntivo"),
                    )

            # Rettifica sintetica del totale consuntivato (adjust_consumed_days o timesheet_days)
            synthetic_target = None
            for key in (
                "adjust_consumed_days",
                "adjust_consumed_to",
                "timesheet_days",
            ):
                if key in data and data[key] is not None:
                    synthetic_target = to_days(data[key])
                    break

            if synthetic_target is not None:
                effective_allocated = (
                    funded_new_allocated
                    if funded_new_allocated is not None
                    else alloc.allocated_days
                )
                if synthetic_target < ZERO:
                    raise serializers.ValidationError(
                        {"adjust_consumed_to": "Le giornate consumate non possono essere negative."}
                    )
                if synthetic_target > effective_allocated:
                    raise serializers.ValidationError(
                        {
                            "adjust_consumed_to": (
                                "Le giornate consumate non possono superare quelle allocate "
                                f"({effective_allocated} gg)."
                            )
                        }
                    )
                active_entries = list(
                    alloc.timesheet_entries.filter(reversals__isnull=True).exclude(
                        source=TimesheetSource.STORNO
                    )
                )
                for entry in active_entries:
                    rev = entry.build_reversal(note=reversal_note)
                    rev.save()
                if synthetic_target > ZERO:
                    TimesheetEntry.objects.create(
                        wallet_allocation=alloc,
                        period=month_start(timezone.now().date()),
                        days=synthetic_target,
                        source=TimesheetSource.MANUALE,
                        note=f"Rettifica consuntivo allocazione: {synthetic_target} gg",
                    )

        closing_now = (
            previous_status == AllocationStatus.APERTA and alloc.status == AllocationStatus.CHIUSA
        )
        if closing_now and not alloc.funding_tranches.exists():
            final_consumed = (
                TimesheetEntry.objects.filter(wallet_allocation=alloc).aggregate(total=Sum("days"))[
                    "total"
                ]
                or ZERO
            )
            if final_consumed < alloc.allocated_days:
                released_days = alloc.allocated_days - final_consumed
                alloc.allocated_days = max(final_consumed, ZERO)

        alloc.full_clean()
        alloc.save()
        if alloc.funding_tranches.exists():
            if funded_new_allocated is not None and not closing_now:
                try:
                    resize_allocation(alloc, funded_new_allocated)
                except ValueError as exc:
                    raise serializers.ValidationError({"allocated_days": str(exc)}) from exc
            if closing_now:
                released_days = close_allocation(alloc)
            else:
                sync_allocation_funding(alloc)

    final_consumed = (
        TimesheetEntry.objects.filter(wallet_allocation=alloc).aggregate(total=Sum("days"))["total"]
        or ZERO
    )
    final_available = alloc.allocated_days - final_consumed

    return {
        "id": str(alloc.id),
        "version": alloc.version,
        "external_ref": alloc.external_ref,
        "allocated_days": str(alloc.allocated_days),
        "days_allocated": str(alloc.allocated_days),
        "consumed_days": str(final_consumed),
        "available_days": str(final_available),
        "released_days": str(released_days),
        "status": alloc.status,
        "notes": alloc.notes,
        "assignee": str(alloc.assignee_id) if alloc.assignee_id else None,
        "architetto": alloc.assignee.full_name if alloc.assignee else None,
        "source_project": str(alloc.source_project_id) if alloc.source_project_id else None,
        "source_project_code": alloc.source_project.code if alloc.source_project else None,
        "source_project_title": alloc.source_project.title if alloc.source_project else None,
        "activity": str(alloc.activity_id),
        "activity_code": alloc.activity.code,
        "activity_title": alloc.activity.title,
        "year": alloc.wallet_year.year,
    }


class WalletAllocationDetailUpdateView(DocumentedAPIView):
    """Dettaglio leggibile dagli autenticati, mutazioni riservate a wallet.edit."""

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [CanEditWallet()]

    def get_object(self, pk, *, for_update=False):
        from wallet.models import WalletAllocation

        queryset = WalletAllocation.objects.select_related(
            "source_project", "activity", "assignee", "wallet_year"
        )
        if for_update:
            queryset = queryset.select_for_update(of=("self",))
        return get_object_or_404(queryset, pk=pk)

    @extend_schema(responses={200: dict})
    def get(self, request, pk):
        from django.db.models import Sum

        from domain.money import ZERO
        from timesheets.models import TimesheetEntry

        alloc = self.get_object(pk)
        consumed = (
            TimesheetEntry.objects.filter(wallet_allocation=alloc).aggregate(total=Sum("days"))[
                "total"
            ]
            or ZERO
        )
        available = alloc.allocated_days - consumed
        entries = [
            {
                "id": str(entry.id),
                "period": entry.period.isoformat() if entry.period else None,
                "days": str(entry.days),
                "source": entry.source,
                "note": entry.note,
                "reverses_id": str(entry.reverses_id) if entry.reverses_id else None,
            }
            for entry in alloc.timesheet_entries.order_by("-period", "-created_at")
        ]
        consuntivi = [entry_payload(entry) for entry in active_entries(alloc)]
        flow_detail = next(
            row for row in wallet_flow(alloc.wallet_year.year) if row["id"] == alloc.id
        )
        payload = {
            "id": str(alloc.id),
            "version": alloc.version,
            "external_ref": alloc.external_ref,
            "allocated_days": str(alloc.allocated_days),
            "initial_allocated_days": str(alloc.initial_allocated_days),
            "days_allocated": str(alloc.allocated_days),
            "consumed_days": str(consumed),
            "available_days": str(available),
            "residuo_allocazione": str(available),
            "residuo_spendibile_origine": (
                str(flow_detail["residuo_spendibile_origine"])
                if flow_detail["residuo_spendibile_origine"] is not None
                else None
            ),
            "validita_origine": flow_detail["validita_origine"],
            "scadenza_origine": flow_detail["scadenza_origine"],
            "status": alloc.status,
            "closure_reason": alloc.closure_reason,
            "stato_operativo": flow_detail["stato_operativo"],
            "notes": alloc.notes,
            "assignee": str(alloc.assignee_id) if alloc.assignee_id else None,
            "architetto": alloc.assignee.full_name if alloc.assignee else None,
            "source_project": str(alloc.source_project_id) if alloc.source_project_id else None,
            "source_project_code": alloc.source_project.code if alloc.source_project else None,
            "source_project_title": alloc.source_project.title if alloc.source_project else None,
            "activity": str(alloc.activity_id),
            "activity_code": alloc.activity.code,
            "activity_title": alloc.activity.title,
            "activity_kind": alloc.activity.kind,
            "year": alloc.wallet_year.year,
            "timesheet_entries": entries,
            "consuntivi": consuntivi,
            "funding": flow_detail.get("fonti_fifo", []),
        }
        return Response(payload, headers={"ETag": make_etag(alloc)})

    @extend_schema(request=dict, responses={200: dict})
    def patch(self, request, pk):
        alloc = self.get_object(pk)
        payload = update_wallet_allocation(request, alloc, request.data, enforce_version=True)
        return Response(payload, headers={"ETag": make_etag(alloc)})

    @transaction.atomic
    def delete(self, request, pk):
        alloc = self.get_object(pk, for_update=True)
        check_expected_version(request, alloc)
        dependencies = []
        if alloc.import_batch_id:
            dependencies.append("allocazione proveniente da import")
        entry_count = alloc.timesheet_entries.count()
        if entry_count:
            dependencies.append(f"consuntivi/rettifiche collegati ({entry_count})")
        anomaly_count = alloc.anomalies.count()
        if anomaly_count:
            dependencies.append(f"anomalie collegate ({anomaly_count})")
        if dependencies:
            raise DomainError(
                detail=(
                    "Eliminazione bloccata: " + "; ".join(dependencies) + ". "
                    "Chiudi o rettifica l'allocazione senza cancellare il ledger."
                ),
                dipendenze=dependencies,
            )
        snapshot = {
            "year": alloc.wallet_year.year,
            "source_project": alloc.source_project.code if alloc.source_project else None,
            "activity": alloc.activity.code,
            "allocated_days": str(alloc.allocated_days),
            "status": alloc.status,
            "version": alloc.version,
        }
        allocation_id = alloc.id
        label = alloc.external_ref or f"{snapshot['source_project']} → {snapshot['activity']}"
        _audit_mutation(
            request,
            "wallet_allocation.delete",
            "wallet_allocation",
            allocation_id,
            label,
            {"snapshot": snapshot},
        )
        alloc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WalletAllocationAdjustView(DocumentedAPIView):
    permission_classes = [CanEditWallet]

    @extend_schema(request=dict, responses={200: dict})
    def post(self, request, pk):
        from wallet.models import WalletAllocation

        alloc = get_object_or_404(
            WalletAllocation.objects.select_related(
                "source_project", "activity", "assignee", "wallet_year"
            ),
            pk=pk,
        )
        payload = update_wallet_allocation(request, alloc, request.data, enforce_version=False)
        return Response(payload, headers={"ETag": make_etag(alloc)})


class AuditHistoryView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: AuditHistoryResponseSerializer})
    def get(self, request, entity_type: str, pk):
        from anomalies.models import Anomaly
        from projects.models import Project
        from wallet.models import WalletAllocation

        model_map = {
            "project": Project,
            "progetto": Project,
            "projects": Project,
            "allocation": WalletAllocation,
            "allocazione": WalletAllocation,
            "allocations": WalletAllocation,
            "anomaly": Anomaly,
            "anomalia": Anomaly,
            "anomalies": Anomaly,
        }
        model_cls = model_map.get(entity_type.lower())
        if model_cls is None:
            return Response(
                {"detail": "Tipo entità per audit non valido."}, status=status.HTTP_404_NOT_FOUND
            )
        instance = get_object_or_404(model_cls, pk=pk)
        history_manager = instance.history  # type: ignore[attr-defined]
        history_records = list(history_manager.all().order_by("-history_date")[:30])
        rows = []
        for i, h in enumerate(history_records):
            changes = []
            if i < len(history_records) - 1:
                prev = history_records[i + 1]
                delta = h.diff_against(prev)
                for change in delta.changes:
                    changes.append(f"{change.field}: {change.old} -> {change.new}")
            rows.append(
                {
                    "history_id": h.history_id,
                    "data": h.history_date.isoformat(),
                    "tipo": h.get_history_type_display(),
                    "utente": str(h.history_user or "Sistema"),
                    "modifiche": changes,
                }
            )
        return Response({"results": rows, "count": len(rows)})


class PpmImportUploadView(DocumentedAPIView):
    permission_classes = [CanUploadImports]

    @extend_schema(request=dict, responses={200: dict})
    def post(self, request):
        import tempfile
        from pathlib import Path

        from core import roles
        from importers.ppm import apply_ppm, dry_run_ppm

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "File non fornito."}, status=status.HTTP_400_BAD_REQUEST)
        suffix = Path(upload.name).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in upload.chunks():
                tmp.write(chunk)
            tmp_path = Path(tmp.name)
        try:
            is_supplier = roles.has_role(
                request.user, roles.SUPPLIER
            ) and not roles.can_write_ledger(request.user)
            wants_apply = request.data.get("apply") in (True, "true", "1") and not is_supplier
            if wants_apply:
                report = apply_ppm(tmp_path, user=request.user)
            else:
                report = dry_run_ppm(tmp_path)
            return Response(report.as_dict())
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
