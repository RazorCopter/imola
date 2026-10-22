"""Motore delle 18 regole di controllo della Fase 4.

Ogni detector restituisce rilievi puri e stabili. Il runner persiste i rilievi con fingerprint
``rule_code + entity_ref``: i valori restano nel contesto e possono cambiare senza generare
doppioni.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.utils import timezone

from anomalies.models import Scope, Severity
from canone.models import Canone, CanoneSubactivity
from core.models import AppSettings
from domain.canone_status import canone_status
from domain.money import ZERO, quantize_days
from domain.reconciliation import latest_rows_by_project, reconcile
from domain.residuals import ResidualState, project_balance_qs, residual_validity
from domain.wallet_balance import allocation_balance_qs
from projects.models import BillingMilestone, OfferStatus, Project, TimesheetStatus
from wallet.models import WalletActivity, WalletAllocation


@dataclass(frozen=True)
class Finding:
    rule_code: str
    entity_ref: str
    severity: str
    scope: str
    description: str
    suggested_action: str = ""
    context: dict = field(default_factory=dict)
    project_id: object | None = None
    allocation_id: object | None = None
    canone_id: object | None = None
    subactivity_id: object | None = None
    snapshot_row_id: object | None = None
    milestone_id: object | None = None


Detector = Callable[[], Iterable[Finding]]


def _short(code: str) -> str:
    if not code:
        return ""
    if code.startswith("IM"):
        return code.split("-", 1)[0]
    return code


# 1. CHK_DATE_ORDER
def check_date_order() -> Iterable[Finding]:
    for project in Project.objects.exclude(start_date=None):
        if project.start_date is None:
            continue
        if project.planned_end_date and project.planned_end_date < project.start_date:
            yield Finding(
                "CHK_DATE_ORDER",
                _short(project.code),
                Severity.ALTA,
                Scope.PROGETTO,
                f"La data di fine prevista di {_short(project.code)} precede la data di inizio.",
                "Correggere le date del progetto.",
                {
                    "project_code": _short(project.code),
                    "start_date": str(project.start_date),
                    "planned_end_date": str(project.planned_end_date),
                },
                project_id=project.id,
            )
        elif project.actual_closure_date and project.actual_closure_date < project.start_date:
            yield Finding(
                "CHK_DATE_ORDER",
                _short(project.code),
                Severity.ALTA,
                Scope.PROGETTO,
                f"La chiusura di {_short(project.code)} precede la data di inizio.",
                "Correggere la data di chiusura del progetto.",
                {
                    "project_code": _short(project.code),
                    "start_date": str(project.start_date),
                    "actual_closure_date": str(project.actual_closure_date),
                },
                project_id=project.id,
            )


# 2. CHK_END_PASSED_ACTIVE
def check_end_passed_active(as_of: date | None = None) -> Iterable[Finding]:
    from datetime import timedelta

    reference_date = as_of or timezone.localdate()
    cutoff_date = reference_date - timedelta(days=30)
    for project in Project.objects.filter(
        timesheet_status=TimesheetStatus.ATTIVO,
        planned_end_date__isnull=False,
        planned_end_date__lt=cutoff_date,
    ).order_by("code"):
        yield Finding(
            "CHK_END_PASSED_ACTIVE",
            _short(project.code),
            Severity.MEDIA,
            Scope.PROGETTO,
            f"{_short(project.code)} è attivo ma la data di fine prevista "
            f"({project.planned_end_date}) è superata da oltre 30 giorni.",
            "Prorogare la data di fine prevista o chiudere la consuntivazione.",
            {
                "project_code": _short(project.code),
                "planned_end_date": str(project.planned_end_date),
                "reference_date": str(reference_date),
            },
            project_id=project.id,
        )


# 3. CHK_CLOSED_NO_DATE
def check_closed_no_date() -> Iterable[Finding]:
    for project in Project.objects.filter(
        timesheet_status=TimesheetStatus.CHIUSO,
        actual_closure_date__isnull=True,
    ).order_by("code"):
        yield Finding(
            "CHK_CLOSED_NO_DATE",
            _short(project.code),
            Severity.ALTA,
            Scope.PROGETTO,
            f"{_short(project.code)} è chiuso senza data di chiusura.",
            "Inserire la data di chiusura effettiva dalla coda di revisione.",
            {"project_code": _short(project.code)},
            project_id=project.id,
        )


# 4. CHK_OVERRUN_PROJECT
def check_overrun_project() -> Iterable[Finding]:
    latest = latest_rows_by_project()
    for project in project_balance_qs():
        if project.timesheet_status != TimesheetStatus.ATTIVO or project.contract_type in (
            "CANONE",
            "PPM",
        ):
            continue
        ppm_row = latest.get(project.id)
        ppm = ppm_row.total_days if ppm_row and ppm_row.total_days is not None else Decimal("0")
        if project.direct_consumed_days > project.budget_days:
            observed = project.direct_consumed_days
            source = "ledger interno"
        elif ppm > project.budget_days and project.total_consumed_days == project.budget_days:
            observed = ppm
            source = "PPM"
        else:
            continue
        ratio = quantize_days(
            (observed - project.budget_days) / project.budget_days
            if project.budget_days
            else Decimal("1.0000")
        )
        yield Finding(
            "CHK_OVERRUN_PROJECT",
            _short(project.code),
            Severity.ALTA if ratio > Decimal("0.10") else Severity.MEDIA,
            Scope.PROGETTO,
            f"{_short(project.code)} supera il budget: {observed} gg su "
            f"{project.budget_days} gg (fonte {source}).",
            "Verificare il consuntivo con Imola e aggiornare pianificazione o budget.",
            {
                "project_code": _short(project.code),
                "source": source,
                "observed": str(observed),
                "budget": str(project.budget_days),
                "ratio": str(ratio),
            },
            project_id=project.id,
        )


# 5. CHK_OVERRUN_ALLOCATION
def check_overrun_allocation() -> Iterable[Finding]:
    for allocation in allocation_balance_qs().select_related("activity").order_by("external_ref"):
        if allocation.consumed_days > allocation.allocated_days:
            ref = allocation.external_ref or str(allocation.id)
            ratio = quantize_days(
                (allocation.consumed_days - allocation.allocated_days) / allocation.allocated_days
                if allocation.allocated_days
                else Decimal("1.0000")
            )
            yield Finding(
                "CHK_OVERRUN_ALLOCATION",
                ref,
                Severity.ALTA if ratio > Decimal("0.10") else Severity.MEDIA,
                Scope.WALLET,
                f"L'allocazione {ref} ({allocation.activity.code}) supera le giornate allocate: "
                f"{allocation.consumed_days} gg su {allocation.allocated_days} gg.",
                "Verificare i consuntivi wallet con Imola o incrementare l'allocazione.",
                {
                    "allocation_ref": ref,
                    "activity": allocation.activity.code,
                    "allocated": str(allocation.allocated_days),
                    "consumed": str(allocation.consumed_days),
                },
                allocation_id=allocation.id,
            )


# 6. CHK_ALLOC_EXCEEDS_RESIDUAL
def check_alloc_exceeds_residual() -> Iterable[Finding]:
    from django.db.models import Sum

    from timesheets.models import TimesheetEntry

    sources = (
        WalletAllocation.objects.exclude(source_project=None)
        .values_list("source_project_id", flat=True)
        .distinct()
    )
    for project_id in sorted(sources, key=str):
        project = Project.objects.filter(pk=project_id).first()
        if project is None:
            continue
        direct = (
            TimesheetEntry.objects.filter(project=project).aggregate(
                total=Sum("days")
            )["total"]
            or ZERO
        )
        base_residual = project.budget_days - direct
        allocations = list(
            WalletAllocation.objects.filter(source_project=project).order_by("external_ref")
        )
        total_allocated = sum((alloc.allocated_days for alloc in allocations), ZERO)
        if total_allocated > base_residual:
            excess = quantize_days(total_allocated - base_residual)
            alloc_refs = [a.external_ref or str(a.id) for a in allocations]
            # atteso da specifica: una sola anomalia aggregata per progetto origine
            ref = _short(project.code)
            yield Finding(
                "CHK_ALLOC_EXCEEDS_RESIDUAL",
                ref,
                Severity.ALTA,
                Scope.WALLET,
                f"Le allocazioni da {ref} superano il residuo disponibile del progetto: "
                f"totale allocato {total_allocated} gg su {base_residual} gg "
                f"(eccedenza {excess} gg).",
                "Ridurre le allocazioni o approvare l'override con motivazione formale.",
                {
                    "source_project": ref,
                    "budget": str(project.budget_days),
                    "direct_consumed": str(direct),
                    "base_residual": str(base_residual),
                    "total_allocated": str(total_allocated),
                    "excess": str(excess),
                    "allocations": alloc_refs,
                },
                project_id=project.id,
            )


# 7. CHK_RESIDUAL_EXPIRING
def check_residual_expiring(as_of: date | None = None) -> Iterable[Finding]:
    settings_obj = AppSettings.get_solo()
    reference_date = as_of or timezone.localdate()
    for project in project_balance_qs():
        if (
            project.timesheet_status == TimesheetStatus.CHIUSO
            and project.actual_closure_date is not None
        ):
            validity = residual_validity(
                timesheet_status=project.timesheet_status,
                closure_date=project.actual_closure_date,
                today=reference_date,
                years_valid_after_closure=settings_obj.residual_years_after_closure,
                expiring_window_days=settings_obj.residual_expiring_window_days,
            )
            unallocated = project.residual_days - project.released_to_wallet_days
            if unallocated > Decimal("0") and validity.state == ResidualState.IN_SCADENZA:
                expiry_str = (
                    validity.expires_on.strftime("%d/%m/%Y") if validity.expires_on else "fine anno"
                )
                yield Finding(
                    "CHK_RESIDUAL_EXPIRING",
                    _short(project.code),
                    Severity.MEDIA,
                    Scope.WALLET,
                    f"Il residuo di {_short(project.code)} ({unallocated} gg) "
                    f"scade il {expiry_str}.",
                    "Allocare il residuo al wallet prima della scadenza.",
                    {
                        "project_code": _short(project.code),
                        "expires_on": str(validity.expires_on),
                        "unallocated_days": str(unallocated),
                    },
                    project_id=project.id,
                )


# 8. CHK_RESIDUAL_UNALLOCATED_CLOSED
def check_residual_unallocated_closed(as_of: date | None = None) -> Iterable[Finding]:
    settings_obj = AppSettings.get_solo()
    reference_date = as_of or timezone.localdate()
    for project in project_balance_qs():
        if (
            project.timesheet_status == TimesheetStatus.CHIUSO
            and project.actual_closure_date is not None
        ):
            validity = residual_validity(
                timesheet_status=project.timesheet_status,
                closure_date=project.actual_closure_date,
                today=reference_date,
                years_valid_after_closure=settings_obj.residual_years_after_closure,
                expiring_window_days=settings_obj.residual_expiring_window_days,
            )
            unallocated = project.residual_days - project.released_to_wallet_days
            if unallocated > Decimal("0") and validity.state == ResidualState.VALIDO:
                yield Finding(
                    "CHK_RESIDUAL_UNALLOCATED_CLOSED",
                    _short(project.code),
                    Severity.BASSA,
                    Scope.WALLET,
                    f"{_short(project.code)} è chiuso con residuo non allocato "
                    f"di {unallocated} gg.",
                    "Valutare l'allocazione delle giornate al wallet.",
                    {
                        "project_code": _short(project.code),
                        "unallocated_days": str(unallocated),
                    },
                    project_id=project.id,
                )


# 9. CHK_ALLOC_FROM_EXPIRED
def check_alloc_from_expired(as_of: date | None = None) -> Iterable[Finding]:
    settings_obj = AppSettings.get_solo()
    reference_date = as_of or timezone.localdate()
    for allocation in WalletAllocation.objects.exclude(source_project=None).select_related(
        "source_project"
    ):
        source = allocation.source_project
        if (
            source is not None
            and source.timesheet_status == TimesheetStatus.CHIUSO
            and source.actual_closure_date is not None
        ):
            validity = residual_validity(
                timesheet_status=source.timesheet_status,
                closure_date=source.actual_closure_date,
                today=reference_date,
                years_valid_after_closure=settings_obj.residual_years_after_closure,
                expiring_window_days=settings_obj.residual_expiring_window_days,
            )
            if validity.state == ResidualState.SCADUTO:
                ref = allocation.external_ref or str(allocation.id)
                yield Finding(
                    "CHK_ALLOC_FROM_EXPIRED",
                    ref,
                    Severity.ALTA,
                    Scope.WALLET,
                    f"L'allocazione {ref} proviene da {_short(source.code)} con residuo scaduto.",
                    "Revocare o motivare l'allocazione da residuo scaduto.",
                    {"allocation_ref": ref, "source_project": _short(source.code)},
                    allocation_id=allocation.id,
                    project_id=source.id,
                )


# 10. CHK_RECON_DELTA
def check_recon_delta() -> Iterable[Finding]:
    for row in reconcile():
        if row.outcome != "KO":
            continue
        yield Finding(
            "CHK_RECON_DELTA",
            _short(row.project_code),
            Severity.MEDIA,
            Scope.RICONCILIAZIONE,
            f"{_short(row.project_code)} non riconcilia: delta {row.delta} gg.",
            row.suggested_action,
            {
                "project_code": _short(row.project_code),
                "internal_days": str(row.internal_days),
                "ppm_days": str(row.ppm_days),
                "delta": str(row.delta),
            },
            project_id=row.project_id,
        )


# 11. CHK_MISSING_IN_PPM
def check_missing_in_ppm() -> Iterable[Finding]:
    for row in reconcile():
        if not row.missing_in_ppm or row.internal_days <= 0:
            continue
        project = Project.objects.get(pk=UUID(str(row.project_id)))
        if (
            project.timesheet_status != TimesheetStatus.ATTIVO
            or project.contract_type in ("CANONE", "PPM")
            or project.planned_end_date is None
            or project.planned_end_date >= timezone.localdate()
        ):
            continue
        yield Finding(
            "CHK_MISSING_IN_PPM",
            _short(project.code),
            Severity.MEDIA,
            Scope.RICONCILIAZIONE,
            f"{_short(project.code)} ha {row.internal_days} gg interni ma non compare nel PPM.",
            "Chiedere a Imola l'associazione nel PPM.",
            {"project_code": _short(project.code), "internal_days": str(row.internal_days)},
            project_id=project.id,
        )


# 12. CHK_DOUBLE_COUNT
def check_double_count() -> Iterable[Finding]:
    canone_refs = set(
        CanoneSubactivity.objects.exclude(redmine_ref="").values_list("redmine_ref", flat=True)
    )
    for activity in WalletActivity.objects.exclude(redmine_ref="").order_by("redmine_ref"):
        if activity.redmine_ref in canone_refs:
            ref = f"RM-{activity.redmine_ref}"
            yield Finding(
                "CHK_DOUBLE_COUNT",
                ref,
                Severity.MEDIA,
                Scope.DOPPIO_CONTEGGIO,
                f"{ref} compare sia nel canone sia nel wallet.",
                "Verificare che le giornate non siano conteggiate due volte.",
                {"entity": ref, "redmine_ref": activity.redmine_ref},
            )


# 13. CHK_CANONE_UNDERUSE
def check_canone_underuse() -> Iterable[Finding]:
    for canone in Canone.objects.select_related("project").order_by("-semester"):
        state = canone_status(canone)
        if state.is_underused:
            ref = _short(canone.project.code)
            yield Finding(
                "CHK_CANONE_UNDERUSE",
                ref,
                Severity.MEDIA,
                Scope.CANONE,
                f"Il forecast del canone {ref} è sotto il 95% del monte.",
                "Rivedere forecast e carico delle sotto-attività.",
                {
                    "entity": ref,
                    "forecast": str(state.forecast),
                    "total": str(state.total_days),
                },
                canone_id=canone.id,
                project_id=canone.project_id,
            )


# 14. CHK_CANONE_OVERUSE
def check_canone_overuse() -> Iterable[Finding]:
    for canone in Canone.objects.select_related("project").order_by("-semester"):
        state = canone_status(canone)
        if state.is_overused:
            ref = _short(canone.project.code)
            yield Finding(
                "CHK_CANONE_OVERUSE",
                ref,
                Severity.ALTA,
                Scope.CANONE,
                f"Il canone {canone.semester} supera il monte: {state.consumed_days} su "
                f"{state.total_days} gg.",
                "Verificare i consuntivi del canone o concordare una variazione del monte.",
                {
                    "entity": ref,
                    "consumed": str(state.consumed_days),
                    "total": str(state.total_days),
                },
                canone_id=canone.id,
                project_id=canone.project_id,
            )


# 15. CHK_ACTIVE_WITHOUT_OFFER
def check_active_without_offer() -> Iterable[Finding]:
    for project in (
        Project.objects.filter(timesheet_status=TimesheetStatus.ATTIVO)
        .exclude(offer_status=OfferStatus.ACCETTATA)
        .order_by("code")
    ):
        yield Finding(
            "CHK_ACTIVE_WITHOUT_OFFER",
            _short(project.code),
            Severity.MEDIA,
            Scope.PROGETTO,
            f"{_short(project.code)} è attivo con offerta non accettata ({project.offer_status}).",
            "Sollecitare l'accettazione dell'offerta o sospendere la consuntivazione.",
            {"project_code": _short(project.code), "offer_status": project.offer_status},
            project_id=project.id,
        )


# 16. CHK_ALLOC_NO_SOURCE
def check_alloc_no_source() -> Iterable[Finding]:
    for allocation in WalletAllocation.objects.filter(
        source_project__isnull=True, wallet_year__year__gte=2026
    ).order_by("external_ref"):
        ref = allocation.external_ref or str(allocation.id)
        yield Finding(
            "CHK_ALLOC_NO_SOURCE",
            ref,
            Severity.ALTA,
            Scope.WALLET,
            f"L'allocazione {ref} non ha un progetto di origine.",
            "Attribuire l'origine o motivare l'uso del wallet generale.",
            {"entity": ref, "activity": allocation.activity.code},
            allocation_id=allocation.id,
        )


# 17. CHK_UNVERIFIED_DATA
def check_unverified_data() -> Iterable[Finding]:
    for project in Project.objects.filter(timesheet_status=TimesheetStatus.DA_VERIFICARE).order_by(
        "code"
    ):
        yield Finding(
            "CHK_UNVERIFIED_DATA",
            _short(project.code),
            Severity.BASSA,
            Scope.PROGETTO,
            f"{_short(project.code)} è in stato DA_VERIFICARE: verificare la consuntivazione.",
            "Revisionare il progetto nella coda di revisione.",
            {"project_code": _short(project.code)},
            project_id=project.id,
        )


# 18. CHK_MILESTONE_SLIPPED
def check_milestone_slipped() -> Iterable[Finding]:
    for milestone in (
        BillingMilestone.objects.filter(move_count__gt=0).select_related("project").order_by("id")
    ):
        yield Finding(
            "CHK_MILESTONE_SLIPPED",
            str(milestone.id),
            Severity.MEDIA,
            Scope.PROGETTO,
            f"Milestone del progetto {_short(milestone.project.code)} "
            f"slittata {milestone.move_count} volte.",
            "Verificare i motivi dello slittamento con il fornitore.",
            {"project_code": _short(milestone.project.code), "move_count": milestone.move_count},
            milestone_id=milestone.id,
            project_id=milestone.project_id,
        )


RULES: dict[str, Detector] = {
    "CHK_DATE_ORDER": check_date_order,
    "CHK_END_PASSED_ACTIVE": check_end_passed_active,
    "CHK_CLOSED_NO_DATE": check_closed_no_date,
    "CHK_OVERRUN_PROJECT": check_overrun_project,
    "CHK_OVERRUN_ALLOCATION": check_overrun_allocation,
    "CHK_ALLOC_EXCEEDS_RESIDUAL": check_alloc_exceeds_residual,
    "CHK_RESIDUAL_EXPIRING": check_residual_expiring,
    "CHK_RESIDUAL_UNALLOCATED_CLOSED": check_residual_unallocated_closed,
    "CHK_ALLOC_FROM_EXPIRED": check_alloc_from_expired,
    "CHK_RECON_DELTA": check_recon_delta,
    "CHK_MISSING_IN_PPM": check_missing_in_ppm,
    "CHK_DOUBLE_COUNT": check_double_count,
    "CHK_CANONE_UNDERUSE": check_canone_underuse,
    "CHK_CANONE_OVERUSE": check_canone_overuse,
    "CHK_ACTIVE_WITHOUT_OFFER": check_active_without_offer,
    "CHK_ALLOC_NO_SOURCE": check_alloc_no_source,
    "CHK_UNVERIFIED_DATA": check_unverified_data,
    "CHK_MILESTONE_SLIPPED": check_milestone_slipped,
}
