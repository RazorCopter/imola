"""Motore delle 18 regole di controllo della Fase 4.

Ogni detector restituisce rilievi puri e stabili. Il runner persiste i rilievi con fingerprint
``rule_code + entity_ref``: i valori restano nel contesto e possono cambiare senza generare
doppioni.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from django.utils import timezone

from anomalies.models import Scope, Severity
from domain.canone_status import canone_status
from domain.reconciliation import latest_rows_by_project, reconcile
from domain.residuals import project_balance_qs
from projects.models import BillingStatus, TimesheetStatus


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
    return code.split("-", 1)[0]


def check_overrun_project() -> Iterable[Finding]:
    latest = latest_rows_by_project()
    for project in project_balance_qs():
        ppm_row = latest.get(project.id)
        ppm = ppm_row.total_days if ppm_row and ppm_row.total_days is not None else Decimal("0")
        observed = max(project.total_consumed_days, ppm)
        # Il PPM integra il ledger quando quest'ultimo ha già raggiunto il budget (D-02);
        # non trasforma invece ogni piccolo delta PPM di un progetto sotto budget in overrun.
        internal_reaches_budget = project.total_consumed_days >= project.budget_days
        if not internal_reaches_budget or observed <= project.budget_days:
            continue
        ratio = (
            (observed - project.budget_days) / project.budget_days
            if project.budget_days
            else Decimal("1")
        )
        if (
            project.timesheet_status != TimesheetStatus.ATTIVO
            or project.contract_type in ("CANONE", "PPM")
            or ratio < Decimal("0.01")
        ):
            continue
        source = "PPM" if ppm > project.total_consumed_days else "ledger interno"
        yield Finding(
            "CHK_OVERRUN_PROJECT",
            _short(project.code),
            Severity.ALTA if ratio >= Decimal("0.10") else Severity.MEDIA,
            Scope.PROGETTO,
            f"{_short(project.code)} supera il budget: {observed} gg su "
            f"{project.budget_days} gg (fonte {source}).",
            "Verificare il consuntivo con Imola e aggiornare pianificazione o budget.",
            {
                "project_code": _short(project.code),
                "source": source,
                "observed": str(observed),
                "budget": str(project.budget_days),
            },
            project_id=project.id,
        )


def check_missing_in_ppm() -> Iterable[Finding]:
    for row in reconcile():
        if not row.missing_in_ppm or row.internal_days <= 0:
            continue
        from projects.models import Project

        project = Project.objects.get(pk=row.project_id)
        # I record storici/da verificare e i canoni non sono progetti attivi da riconciliare.
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
            f"{_short(project.code)} ha {row.internal_days} gg interni ma non compare "
            "nell'ultimo PPM.",
            "Chiedere a Imola l'associazione nel PPM.",
            {"project_code": _short(project.code), "internal_days": str(row.internal_days)},
            project_id=project.id,
        )


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
            snapshot_row_id=None,
        )


def check_double_count() -> Iterable[Finding]:
    from canone.models import CanoneSubactivity
    from wallet.models import WalletActivity

    canone_refs = set(
        CanoneSubactivity.objects.exclude(redmine_ref="").values_list("redmine_ref", flat=True)
    )
    for activity in WalletActivity.objects.exclude(redmine_ref=""):
        if activity.redmine_ref in canone_refs:
            ref = f"RM-{activity.redmine_ref}"
            yield Finding(
                "CHK_DOUBLE_COUNT",
                ref,
                Severity.ALTA,
                Scope.DOPPIO_CONTEGGIO,
                f"{ref} compare sia nel canone sia nel wallet.",
                "Verificare che le giornate non siano conteggiate due volte.",
                {"entity": ref, "redmine_ref": activity.redmine_ref},
            )


def check_alloc_no_source() -> Iterable[Finding]:
    from wallet.models import WalletAllocation

    for allocation in WalletAllocation.objects.filter(
        source_project__isnull=True, wallet_year__year__gte=2026
    ):
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


def check_closed_no_date() -> Iterable[Finding]:
    from projects.models import Project

    for project in Project.objects.filter(
        timesheet_status=TimesheetStatus.CHIUSO, actual_closure_date__isnull=True
    ):
        yield Finding(
            "CHK_CLOSED_NO_DATE",
            _short(project.code),
            Severity.ALTA,
            Scope.PROGETTO,
            f"{_short(project.code)} è chiuso senza data di chiusura.",
            "Inserire la data dalla coda di revisione.",
            {"project_code": _short(project.code)},
            project_id=project.id,
        )


def check_residual_unallocated_closed() -> Iterable[Finding]:
    # D-05: copre i nove residui storici DA_VERIFICARE elencati nella mappa seed.
    from importers.seed_json import SEED_SUPERSESSION_MAP
    from projects.models import Project

    expected = SEED_SUPERSESSION_MAP["AN-003"]
    refs = expected[1] if expected else ()
    for ref in refs if isinstance(refs, tuple) else (refs,):
        project = Project.objects.filter(code__startswith=ref).first()
        if project is not None:
            yield Finding(
                "CHK_RESIDUAL_UNALLOCATED_CLOSED",
                ref,
                Severity.MEDIA,
                Scope.WALLET,
                f"{ref} ha un residuo storico non allocato da verificare.",
                "Confermare origine e disponibilità del residuo.",
                {"project_code": ref},
                project_id=project.id,
            )


def check_canone_underuse() -> Iterable[Finding]:
    from canone.models import Canone

    for canone in Canone.objects.select_related("project"):
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
                {"entity": ref, "forecast": str(state.forecast), "total": str(state.total_days)},
                canone_id=canone.id,
                project_id=canone.project_id,
            )


def check_canone_overrun() -> Iterable[Finding]:
    from canone.models import Canone

    for canone in Canone.objects.all():
        state = canone_status(canone)
        if state.is_overused:
            yield Finding(
                "CHK_CANONE_OVERRUN",
                str(canone.id),
                Severity.ALTA,
                Scope.CANONE,
                f"Il canone {canone.semester} supera il monte giornate.",
                canone_id=canone.id,
            )


def check_date_order() -> Iterable[Finding]:
    from projects.models import Project

    for project in (
        Project.objects.exclude(start_date=None)
        .exclude(planned_end_date=None)
        .filter(planned_end_date__lt=__import__("django.db.models", fromlist=["F"]).F("start_date"))
    ):
        yield Finding(
            "CHK_DATE_ORDER",
            _short(project.code),
            Severity.ALTA,
            Scope.ANAGRAFICA,
            f"Le date di {_short(project.code)} non sono in ordine.",
            project_id=project.id,
        )


def check_missing_owner() -> Iterable[Finding]:
    from projects.models import Project

    for project in Project.objects.filter(client_owner__isnull=True, supplier_owner__isnull=True):
        yield Finding(
            "CHK_MISSING_OWNER",
            _short(project.code),
            Severity.BASSA,
            Scope.ANAGRAFICA,
            f"{_short(project.code)} non ha referenti.",
            project_id=project.id,
        )


def check_zero_budget() -> Iterable[Finding]:
    from projects.models import Project

    for project in Project.objects.filter(budget_days=0):
        yield Finding(
            "CHK_ZERO_BUDGET",
            _short(project.code),
            Severity.MEDIA,
            Scope.PROGETTO,
            f"{_short(project.code)} ha budget zero.",
            project_id=project.id,
        )


def check_alloc_exceeds_residual() -> Iterable[Finding]:
    from domain.wallet_balance import available_residual_for_allocation
    from wallet.models import WalletAllocation

    for allocation in WalletAllocation.objects.exclude(source_project=None):
        available = available_residual_for_allocation(
            allocation.source_project_id, exclude_allocation_id=allocation.id
        )
        if allocation.allocated_days > available:
            yield Finding(
                "CHK_ALLOC_EXCEEDS_RESIDUAL",
                allocation.external_ref or str(allocation.id),
                Severity.ALTA,
                Scope.WALLET,
                "L'allocazione supera il residuo della fonte.",
                allocation_id=allocation.id,
                project_id=allocation.source_project_id,
            )


def check_zero_allocation() -> Iterable[Finding]:
    from wallet.models import WalletAllocation

    for allocation in WalletAllocation.objects.filter(allocated_days=0):
        yield Finding(
            "CHK_ZERO_ALLOCATION",
            allocation.external_ref or str(allocation.id),
            Severity.BASSA,
            Scope.WALLET,
            "Allocazione a zero giornate da confermare.",
            allocation_id=allocation.id,
        )


def check_milestone_no_date() -> Iterable[Finding]:
    from projects.models import BillingMilestone

    for milestone in BillingMilestone.objects.filter(planned_date=None):
        yield Finding(
            "CHK_MILESTONE_NO_DATE",
            str(milestone.id),
            Severity.MEDIA,
            Scope.PROGETTO,
            "Milestone senza data prevista.",
            milestone_id=milestone.id,
            project_id=milestone.project_id,
        )


def check_billing_inconsistent() -> Iterable[Finding]:
    from projects.models import Project

    for project in Project.objects.filter(
        timesheet_status=TimesheetStatus.NON_AVVIATO, billing_status=BillingStatus.TOTALE
    ):
        yield Finding(
            "CHK_BILLING_INCONSISTENT",
            _short(project.code),
            Severity.MEDIA,
            Scope.PROGETTO,
            "Progetto non avviato ma totalmente fatturato.",
            project_id=project.id,
        )


def check_ppm_unmatched() -> Iterable[Finding]:
    from ppm.models import PpmSnapshotRow

    for row in PpmSnapshotRow.objects.filter(project=None):
        yield Finding(
            "CHK_PPM_UNMATCHED",
            str(row.id),
            Severity.MEDIA,
            Scope.RICONCILIAZIONE,
            f"Riga PPM {row.project_code} non associata.",
            snapshot_row_id=row.id,
        )


def check_ppm_unbalanced() -> Iterable[Finding]:
    from ppm.models import PpmSnapshot

    for snapshot in PpmSnapshot.objects.filter(balanced=False):
        yield Finding(
            "CHK_PPM_UNBALANCED",
            str(snapshot.id),
            Severity.ALTA,
            Scope.RICONCILIAZIONE,
            f"Lo snapshot {snapshot.source_filename} non quadra.",
        )


RULES: dict[str, Detector] = {
    "CHK_OVERRUN_PROJECT": check_overrun_project,
    "CHK_MISSING_IN_PPM": check_missing_in_ppm,
    "CHK_RECON_DELTA": check_recon_delta,
    "CHK_DOUBLE_COUNT": check_double_count,
    "CHK_ALLOC_NO_SOURCE": check_alloc_no_source,
    "CHK_CLOSED_NO_DATE": check_closed_no_date,
    "CHK_RESIDUAL_UNALLOCATED_CLOSED": check_residual_unallocated_closed,
    "CHK_CANONE_UNDERUSE": check_canone_underuse,
    "CHK_CANONE_OVERRUN": check_canone_overrun,
    "CHK_DATE_ORDER": check_date_order,
    "CHK_MISSING_OWNER": check_missing_owner,
    "CHK_ZERO_BUDGET": check_zero_budget,
    "CHK_ALLOC_EXCEEDS_RESIDUAL": check_alloc_exceeds_residual,
    "CHK_ZERO_ALLOCATION": check_zero_allocation,
    "CHK_MILESTONE_NO_DATE": check_milestone_no_date,
    "CHK_BILLING_INCONSISTENT": check_billing_inconsistent,
    "CHK_PPM_UNMATCHED": check_ppm_unmatched,
    "CHK_PPM_UNBALANCED": check_ppm_unbalanced,
}
