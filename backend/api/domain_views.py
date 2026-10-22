"""Endpoint delle viste calcolate: residui, wallet, canone, riconciliazione.

Qui non si scrive nulla: tutti i numeri arrivano dai builder in domain/, mai da colonne
salvate. Ogni risposta porta con sé la spiegazione del calcolo, che la UI mostra in tooltip.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from canone.models import Canone
from core.models import AppSettings
from core.permissions import CanUploadImports, IsAdmin, ReadOnlyOrLedgerWriter, ReferentCanAnnotate
from domain.canone_status import canone_burndown, canone_status
from domain.reconciliation import reconcile, reconciliation_summary
from domain.residuals import residual_explanation, residual_validity
from domain.wallet_balance import wallet_by_assignee, wallet_flow, wallet_year_balance


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


class SettingsView(DocumentedAPIView):
    """Parametri globali: lettura per tutti, modifica solo Admin."""

    def get_permissions(self):
        return [IsAdmin()] if self.request.method not in ("GET", "HEAD") else [IsAuthenticated()]

    def get(self, request):
        settings_obj = current_settings()
        return Response(
            {
                "ore_per_giornata": settings_obj.hours_per_day,
                "granularita_ppm_gg": settings_obj.ppm_granularity_days,
                "tolleranza_riconciliazione_gg": settings_obj.reconciliation_tolerance_days,
                "anni_validita_dopo_chiusura": settings_obj.residual_years_after_closure,
                "finestra_scadenza_giorni": settings_obj.residual_expiring_window_days,
                "version": settings_obj.version,
            }
        )

    def patch(self, request):
        settings_obj = current_settings()
        mapping = {
            "ore_per_giornata": "hours_per_day",
            "granularita_ppm_gg": "ppm_granularity_days",
            "tolleranza_riconciliazione_gg": "reconciliation_tolerance_days",
            "anni_validita_dopo_chiusura": "residual_years_after_closure",
            "finestra_scadenza_giorni": "residual_expiring_window_days",
        }
        for key, attr in mapping.items():
            if key in request.data:
                setattr(settings_obj, attr, request.data[key])
        settings_obj.full_clean()
        settings_obj.save()
        return self.get(request)


class ProjectListCreateView(DocumentedAPIView):
    """Elenco anagrafico e creazione guidata dei progetti."""

    permission_classes = [ReadOnlyOrLedgerWriter]

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
    def post(self, request):
        from django.core.exceptions import ValidationError as DjangoValidationError

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
        from domain.residuals import project_balance_qs

        settings_obj = current_settings()
        today = timezone.localdate()
        rows = []
        queryset = project_balance_qs().select_related("client_owner", "supplier_owner")
        for project in queryset.order_by("code"):
            validity = residual_validity(
                timesheet_status=project.timesheet_status,
                closure_date=project.actual_closure_date,
                today=today,
                years_valid_after_closure=settings_obj.residual_years_after_closure,
                expiring_window_days=settings_obj.residual_expiring_window_days,
            )
            can_annotate = ReferentCanAnnotate.can_annotate(request.user, project)
            rows.append(
                {
                    "id": project.id,
                    "codice": project.code,
                    "titolo": project.title,
                    "tipo_contratto": project.contract_type,
                    "budget": project.budget_days,
                    "consuntivi_diretti": project.direct_consumed_days,
                    "allocato_a_wallet": project.allocated_to_wallet_days,
                    "consumato_via_wallet": project.consumed_via_wallet_days,
                    "consumato_totale": project.total_consumed_days,
                    "residuo": project.residual_days,
                    "stato_consuntivazione": project.timesheet_status,
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
                    "permissions": {"annotate": can_annotate},
                }
            )
        return Response({"results": rows, "count": len(rows)})


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
    permission_classes = [ReadOnlyOrLedgerWriter]

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
    permission_classes = [ReadOnlyOrLedgerWriter]

    @extend_schema(request=dict, responses={201: dict})
    def post(self, request):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.db import transaction

        from directory.models import Person
        from domain.money import to_days
        from domain.wallet_balance import available_residual_for_allocation
        from projects.models import Project
        from wallet.models import WalletActivity, WalletAllocation, WalletYear

        required = ("year", "source_project", "activity", "assignee", "allocated_days")
        missing = [field for field in required if not request.data.get(field)]
        if missing:
            return Response(
                {field: ["Campo obbligatorio."] for field in missing},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            source = Project.objects.get(pk=request.data["source_project"])
            activity = WalletActivity.objects.get(pk=request.data["activity"])
            assignee = Person.objects.get(pk=request.data["assignee"])
            allocated_days = to_days(request.data["allocated_days"])
            if allocated_days <= 0:
                raise DjangoValidationError({"allocated_days": "Deve essere maggiore di zero."})
            available = available_residual_for_allocation(source.id)
            if allocated_days > available:
                raise DjangoValidationError(
                    {
                        "allocated_days": (
                            f"Giornate richieste {allocated_days} superiori al disponibile "
                            f"{available} del progetto di origine."
                        )
                    }
                )
            with transaction.atomic():
                wallet_year, _ = WalletYear.objects.get_or_create(year=int(request.data["year"]))
                allocation = WalletAllocation(
                    wallet_year=wallet_year,
                    source_project=source,
                    activity=activity,
                    assignee=assignee,
                    allocated_days=allocated_days,
                    notes=str(request.data.get("notes", "")),
                    external_ref=str(request.data.get("external_ref", "")),
                )
                allocation.full_clean()
                allocation.save()
        except (Project.DoesNotExist, WalletActivity.DoesNotExist, Person.DoesNotExist):
            return Response(
                {"detail": "Origine, attività o architetto non valido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (ValueError, TypeError, DjangoValidationError) as exc:
            detail = (
                exc.message_dict if isinstance(exc, DjangoValidationError) else {"detail": str(exc)}
            )
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "id": allocation.id,
                "architetto": assignee.full_name,
                "allocated_days": str(allocation.allocated_days),
            },
            status=status.HTTP_201_CREATED,
        )


class WalletAllocationOptionsView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from directory.models import Person
        from projects.models import Project, TimesheetStatus
        from wallet.models import WalletActivity

        return Response(
            {
                "projects": [
                    {"id": row.id, "code": row.code, "title": row.title}
                    for row in Project.objects.filter(
                        timesheet_status=TimesheetStatus.CHIUSO,
                        actual_closure_date__isnull=False,
                    ).order_by("code")
                ],
                "activities": [
                    {"id": row.id, "code": row.code, "title": row.title}
                    for row in WalletActivity.objects.order_by("code")
                ],
                "assignees": [
                    {"id": row.id, "name": row.full_name}
                    for row in Person.objects.order_by("full_name")
                ],
            }
        )


class CanoneListView(DocumentedAPIView):
    """Indice minimo dei canoni per il selettore semestre della UI."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request):
        rows = Canone.objects.select_related("project").order_by("-semester")
        return Response(
            {
                "results": [
                    {
                        "id": row.id,
                        "semestre": row.semester,
                        "progetto_codice": row.project.code,
                        "progetto_titolo": row.project.title,
                    }
                    for row in rows
                ],
                "count": rows.count(),
            }
        )


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
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from exporters import export_json_bytes

        return HttpResponse(
            export_json_bytes(),
            content_type="application/json; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="supplier-ledger-1.0.0.json"'},
        )


class ExportCsvView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

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
        canone = Canone.objects.get(pk=pk)
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


class ProjectDetailUpdateView(DocumentedAPIView):
    permission_classes = [ReferentCanAnnotate]

    def get_object(self, pk):
        from projects.models import Project

        obj = get_object_or_404(Project, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(operation_id="project_detail", responses={200: dict})
    def get(self, request, pk):
        project = self.get_object(pk)
        return Response(
            {
                "id": project.id,
                "codice": project.code,
                "titolo": project.title,
                "tipo_contratto": project.contract_type,
                "stato_consuntivazione": project.timesheet_status,
                "stato_fatturazione": project.billing_status,
                "stato_offerta": project.offer_status,
                "budget_days": str(project.budget_days),
                "start_date": str(project.start_date) if project.start_date else None,
                "planned_end_date": (
                    str(project.planned_end_date) if project.planned_end_date else None
                ),
                "actual_closure_date": (
                    str(project.actual_closure_date) if project.actual_closure_date else None
                ),
                "notes": project.notes,
            }
        )

    @extend_schema(request=dict, responses={200: dict})
    def patch(self, request, pk):
        from datetime import date

        from core import roles

        project = self.get_object(pk)
        if "notes" in request.data:
            project.notes = str(request.data["notes"])
        if "planned_end_date" in request.data:
            val = request.data["planned_end_date"]
            project.planned_end_date = date.fromisoformat(val) if val else None
        if roles.can_write_ledger(request.user):
            if "actual_closure_date" in request.data:
                val = request.data["actual_closure_date"]
                project.actual_closure_date = date.fromisoformat(val) if val else None
            if "timesheet_status" in request.data:
                project.timesheet_status = request.data["timesheet_status"]
            if "billing_status" in request.data:
                project.billing_status = request.data["billing_status"]
        project.full_clean()
        project.save()
        return self.get(request, pk)


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
        return Response(
            {
                "id": project.id,
                "timesheet_status": project.timesheet_status,
                "actual_closure_date": str(project.actual_closure_date),
            }
        )


class WalletAllocationAdjustView(DocumentedAPIView):
    permission_classes = [ReadOnlyOrLedgerWriter]

    @extend_schema(request=dict, responses={200: dict})
    def post(self, request, pk):
        from domain.money import to_days
        from wallet.models import WalletAllocation

        alloc = get_object_or_404(WalletAllocation, pk=pk)
        if "allocated_days" in request.data:
            alloc.allocated_days = to_days(request.data["allocated_days"])
        if "status" in request.data:
            alloc.status = request.data["status"]
        alloc.full_clean()
        alloc.save()
        return Response(
            {
                "id": alloc.id,
                "external_ref": alloc.external_ref,
                "allocated_days": str(alloc.allocated_days),
                "status": alloc.status,
            }
        )


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
