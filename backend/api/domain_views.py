"""Endpoint delle viste calcolate: residui, wallet, canone, riconciliazione.

Qui non si scrive nulla: tutti i numeri arrivano dai builder in domain/, mai da colonne
salvate. Ogni risposta porta con sé la spiegazione del calcolo, che la UI mostra in tooltip.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
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
from core.permissions import IsAdmin, ReadOnlyOrLedgerWriter
from domain.canone_status import canone_burndown, canone_status
from domain.money import ZERO, quantize_days
from domain.reconciliation import reconcile, reconciliation_summary
from domain.residuals import project_balance_qs, residual_explanation, residual_validity
from domain.wallet_balance import wallet_flow, wallet_year_balance


class DomainResponseSerializer(serializers.Serializer):
    """Schema di fallback esplicito per risposte di dominio documentate come oggetti."""


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

    @extend_schema(responses={200: dict})
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
    """Rende esplicitamente disponibile al wallet una quota del residuo di un progetto attivo."""

    permission_classes = [ReadOnlyOrLedgerWriter]

    @transaction.atomic
    def post(self, request, pk):
        from projects.models import Project, TimesheetStatus

        project = get_object_or_404(Project.objects.select_for_update(), pk=pk)
        if project.timesheet_status != TimesheetStatus.ATTIVO:
            return Response(
                {"detail": "Il rilascio è consentito solo per progetti ATTIVI."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = str(request.data.get("motivazione", "")).strip()
        if not reason:
            return Response(
                {"motivazione": ["Questo campo è obbligatorio."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            days = quantize_days(Decimal(str(request.data.get("giornate", ""))))
        except (InvalidOperation, TypeError, ValueError):
            return Response(
                {"giornate": ["Inserire un numero valido."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if days <= ZERO:
            return Response(
                {"giornate": ["Il valore deve essere maggiore di zero."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        calculated = project_balance_qs(Project.objects.filter(pk=project.pk)).get()
        available_to_release = quantize_days(
            calculated.residual_days - project.released_to_wallet_days
        )
        if days > available_to_release:
            return Response(
                {
                    "giornate": [
                        "Il rilascio supera il residuo ancora rilasciabile "
                        f"({available_to_release})."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        project.released_to_wallet_days = quantize_days(project.released_to_wallet_days + days)
        project._change_reason = reason  # type: ignore[attr-defined]
        project.save(update_fields=["released_to_wallet_days", "updated_at"])
        return Response(
            {
                "id": project.id,
                "codice": project.code,
                "giornate_rilasciate": days,
                "rilasciato_al_wallet": project.released_to_wallet_days,
                "residuo_ancora_rilasciabile": quantize_days(available_to_release - days),
                "motivazione": reason,
            },
            status=status.HTTP_200_OK,
        )


class WalletFlowView(DocumentedAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, year: int):
        return Response({"results": wallet_flow(year)})


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
                "riepilogo": reconciliation_summary(tolerance),
                "tolleranza": tolerance,
                "results": [
                    {**row.as_dict(), "spiegazione": row.explanation}
                    for row in rows
                    if row.internal_days or not row.missing_in_ppm
                ],
            }
        )
