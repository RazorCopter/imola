"""Endpoint delle viste calcolate: residui, wallet, canone, riconciliazione.

Qui non si scrive nulla: tutti i numeri arrivano dai builder in domain/, mai da colonne
salvate. Ogni risposta porta con sé la spiegazione del calcolo, che la UI mostra in tooltip.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
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


def current_settings() -> AppSettings:
    return AppSettings.get_solo()


class SettingsView(APIView):
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


class ProjectBalancesView(APIView):
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


class ProjectReviewQueueView(APIView):
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


class AnomalyListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from anomalies.models import Anomaly

        rows = Anomaly.objects.select_related("project").order_by("-detected_at", "external_ref")
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
                    }
                    for row in rows
                ]
            }
        )


class WalletBalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, year: int):
        settings_obj = current_settings()
        balance = wallet_year_balance(
            year,
            years_valid_after_closure=settings_obj.residual_years_after_closure,
            expiring_window_days=settings_obj.residual_expiring_window_days,
        )
        return Response(balance.as_dict())


class ReleaseProjectToWalletView(APIView):
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


class WalletFlowView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, year: int):
        return Response({"results": wallet_flow(year)})


class CanoneListView(APIView):
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


class CanoneStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request, pk):
        canone = Canone.objects.get(pk=pk)
        status_data = canone_status(canone).as_dict()
        status_data["burndown"] = canone_burndown(canone)
        return Response(status_data)


class ReconciliationView(APIView):
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
