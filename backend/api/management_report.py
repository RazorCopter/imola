from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import F, Sum
from django.utils import timezone
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from canone.models import Canone, CanoneSubactivity
from core.models import AppSettings
from core.roles import is_admin
from domain.canone_status import subactivity_state
from domain.cost_analysis import build_cost_analysis
from domain.residuals import project_balance_qs
from domain.wallet_balance import allocation_balance_qs
from projects.models import TimesheetStatus
from wallet.models import AllocationStatus, WalletAllocation


class AdminOnly(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_admin(request.user))


class ManagementReportView(APIView):
    permission_classes = [AdminOnly]

    def get(self, request):
        today = timezone.localdate()
        settings = AppSettings.get_solo()
        economics = build_cost_analysis(
            daily_cost=settings.daily_person_cost,
            date_from=date(today.year, 1, 1),
            date_to=today,
        )
        projects = []
        # Ordinamenti per lettura, non per codice: le righe si raggruppano da se sotto il
        # nome di chi ne risponde, e chi non ha un referente finisce in fondo invece di
        # spezzare un gruppo a meta.
        for p in (
            project_balance_qs()
            .filter(timesheet_status=TimesheetStatus.ATTIVO)
            .select_related("client_owner")
            .order_by(F("client_owner__full_name").asc(nulls_last=True), "code")
        ):
            projects.append(
                {
                    "code": p.code,
                    "title": p.title,
                    "owner": p.client_owner.full_name if p.client_owner else None,
                    "budget": str(p.budget_days),
                    "consumed": str(p.total_consumed_days),
                    "direct": str(p.direct_consumed_days),
                    "wallet_consumed": str(p.consumed_via_wallet_days),
                    "end": p.planned_end_date.isoformat() if p.planned_end_date else None,
                }
            )
        allocations = (
            allocation_balance_qs(
                WalletAllocation.objects.filter(
                    status=AllocationStatus.APERTA, is_technical=False, activity__is_technical=False
                )
            )
            .select_related("activity", "activity__client_owner", "assignee", "wallet_year")
            .order_by(
                F("assignee__full_name").asc(nulls_last=True),
                "activity__code",
                "wallet_year__year",
            )
        )
        wallet = []
        for a in allocations:
            wallet.append(
                {
                    "code": a.activity.code,
                    "title": a.activity.title,
                    # Il referente BMED sta sull'attivita e di norma e vuoto: le attivita
                    # create dal wallet non lo chiedono. Chi risponde delle giornate e
                    # l'assegnatario dell'allocazione, che e anche quello che l'elenco mostra.
                    "owner": a.activity.client_owner.full_name if a.activity.client_owner else None,
                    "assignee": a.assignee.full_name if a.assignee else None,
                    "year": a.wallet_year.year,
                    "allocated": str(a.allocated_days),
                    "consumed": str(a.consumed_days),
                    "remaining": str(a.available_days),
                }
            )
        rows = (
            CanoneSubactivity.objects.filter(
                canone__start_date__lte=today, canone__end_date__gte=today
            )
            .select_related("canone")
            .annotate(consumed=Sum("timesheet_entries__days"))
            # Raggruppate per dominio di appartenenza, poi per titolo.
            .order_by(F("office").asc(nulls_last=True), "title")
        )
        activities = []
        domains = defaultdict(lambda: {"reserved": Decimal(0), "consumed": Decimal(0), "count": 0})
        for a in rows:
            consumed = a.consumed or Decimal(0)
            domain = a.office or "Non assegnato"
            domains[domain]["reserved"] += a.reserved_days
            domains[domain]["consumed"] += consumed
            domains[domain]["count"] += 1
            if subactivity_state(a.reserved_days, consumed) == "CHIUSO":
                continue
            activities.append(
                {
                    "domain": domain,
                    "title": a.title,
                    "period": a.canone.semester,
                    "reserved": str(a.reserved_days),
                    "consumed": str(consumed),
                    "remaining": str(a.reserved_days - consumed),
                }
            )
        domain_rows = [
            {
                "domain": key,
                "count": value["count"],
                "reserved": str(value["reserved"]),
                "consumed": str(value["consumed"]),
                "remaining": str(value["reserved"] - value["consumed"]),
            }
            for key, value in sorted(domains.items())
        ]
        return Response(
            {
                "date": today.isoformat(),
                "economics": economics,
                "projects": projects,
                "wallet": wallet,
                "domains": domain_rows,
                "organico_monte": str(
                    Canone.objects.filter(start_date__lte=today, end_date__gte=today).aggregate(
                        total=Sum("total_days")
                    )["total"]
                    or Decimal(0)
                ),
                "activities": activities,
            }
        )
