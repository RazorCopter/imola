"""Saldo operativo dei progetti e validità dei residui wallet.

Un progetto non chiuso può avere un saldo operativo positivo, ma non genera credito wallet.
Solo un progetto CHIUSO con data effettiva produce un residuo spendibile, valido fino al
31 dicembre dell'anno successivo alla chiusura. I totali sono sempre calcolati dal database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce

from domain.money import ZERO, quantize_days

DAYS_OUTPUT = DecimalField(max_digits=12, decimal_places=4)


class ResidualState(str):
    """Stato di validità di un residuo, condiviso fra API e interfaccia."""

    VALIDO = "VALIDO"
    IN_SCADENZA = "IN_SCADENZA"
    SCADUTO = "SCADUTO"
    DA_VERIFICARE = "DA_VERIFICARE"
    NON_DISPONIBILE = "NON_DISPONIBILE"


@dataclass(frozen=True)
class ResidualValidity:
    """Esito della regola R2 per un progetto."""

    state: str
    expires_on: date | None
    days_to_expiry: int | None
    reason: str

    @property
    def usable(self) -> bool:
        return self.state in {ResidualState.VALIDO, ResidualState.IN_SCADENZA}


def last_usable_day(closure_date: date, years_valid_after_closure: int = 1) -> date:
    """Ultimo giorno utile del residuo di un progetto chiuso (R2)."""
    return date(closure_date.year + years_valid_after_closure, 12, 31)


def residual_validity(
    *,
    timesheet_status: str,
    closure_date: date | None,
    today: date,
    years_valid_after_closure: int = 1,
    expiring_window_days: int = 90,
) -> ResidualValidity:
    """Applica R2 senza toccare il database, così da essere testabile in isolamento."""
    from projects.models import TimesheetStatus

    if timesheet_status == TimesheetStatus.CHIUSO:
        if closure_date is None:
            # D-03: senza data la scadenza non è calcolabile. Residuo non spendibile
            # finché la coda di revisione non registra la data.
            return ResidualValidity(
                ResidualState.DA_VERIFICARE,
                None,
                None,
                "Progetto chiuso senza data di chiusura: scadenza non calcolabile.",
            )
        deadline = last_usable_day(closure_date, years_valid_after_closure)
        remaining = (deadline - today).days
        if remaining < 0:
            return ResidualValidity(
                ResidualState.SCADUTO,
                deadline,
                remaining,
                f"Residuo scaduto il {deadline.strftime('%d/%m/%Y')}.",
            )
        if remaining <= expiring_window_days:
            return ResidualValidity(
                ResidualState.IN_SCADENZA,
                deadline,
                remaining,
                f"Scade fra {remaining} giorni, il {deadline.strftime('%d/%m/%Y')}.",
            )
        return ResidualValidity(
            ResidualState.VALIDO,
            deadline,
            remaining,
            f"Valido fino al {deadline.strftime('%d/%m/%Y')}.",
        )

    if timesheet_status == TimesheetStatus.DA_VERIFICARE:
        return ResidualValidity(
            ResidualState.DA_VERIFICARE,
            None,
            None,
            "Stato della consuntivazione da confermare: residuo non spendibile.",
        )

    return ResidualValidity(
        ResidualState.NON_DISPONIBILE,
        None,
        None,
        "Progetto non chiuso: saldo operativo non disponibile nel wallet.",
    )


def direct_consumed_expr() -> Coalesce:
    """Giornate consuntivate direttamente sul progetto (storni inclusi, con segno)."""
    return Coalesce(
        Sum("timesheet_entries__days", output_field=DAYS_OUTPUT),
        Value(ZERO, output_field=DAYS_OUTPUT),
        output_field=DAYS_OUTPUT,
    )


def allocated_out_expr() -> Coalesce:
    """Giornate uscite dal progetto verso il wallet (solo allocazioni aperte o chiuse,
    comunque impegnate)."""
    return Coalesce(
        Sum("wallet_allocations__allocated_days", output_field=DAYS_OUTPUT),
        Value(ZERO, output_field=DAYS_OUTPUT),
        output_field=DAYS_OUTPUT,
    )


def consumed_via_wallet_expr() -> Coalesce:
    return Coalesce(
        Sum("wallet_allocations__timesheet_entries__days", output_field=DAYS_OUTPUT),
        Value(ZERO, output_field=DAYS_OUTPUT),
        output_field=DAYS_OUTPUT,
    )


def project_balance_qs(queryset: models.QuerySet | None = None) -> models.QuerySet:
    """Vista calcolata `project_balance` (par. 3.2).

    Le somme sono annotate con subquery indipendenti, così i join multipli non si
    moltiplicano fra loro. Nessun totale è mai persistito.
    """
    from projects.models import Project
    from timesheets.models import TimesheetEntry
    from wallet.models import WalletAllocation

    qs = queryset if queryset is not None else Project.objects.all()

    direct = (
        TimesheetEntry.objects.filter(project=models.OuterRef("pk"))
        .order_by()
        .values("project")
        .annotate(total=Sum("days", output_field=DAYS_OUTPUT))
        .values("total")[:1]
    )
    allocated = (
        WalletAllocation.objects.filter(source_project=models.OuterRef("pk"))
        .order_by()
        .values("source_project")
        .annotate(total=Sum("allocated_days", output_field=DAYS_OUTPUT))
        .values("total")[:1]
    )
    consumed_wallet = (
        TimesheetEntry.objects.filter(wallet_allocation__source_project=models.OuterRef("pk"))
        .order_by()
        .values("wallet_allocation__source_project")
        .annotate(total=Sum("days", output_field=DAYS_OUTPUT))
        .values("total")[:1]
    )

    zero = Value(ZERO, output_field=DAYS_OUTPUT)
    return qs.annotate(
        direct_consumed_days=Coalesce(models.Subquery(direct, output_field=DAYS_OUTPUT), zero),
        allocated_to_wallet_days=Coalesce(
            models.Subquery(allocated, output_field=DAYS_OUTPUT), zero
        ),
        consumed_via_wallet_days=Coalesce(
            models.Subquery(consumed_wallet, output_field=DAYS_OUTPUT), zero
        ),
    ).annotate(
        total_consumed_days=F("direct_consumed_days") + F("consumed_via_wallet_days"),
        residual_days=F("budget_days") - F("direct_consumed_days") - F("allocated_to_wallet_days"),
    )


def project_closure_ready(project) -> bool:
    from projects.models import ContractType, TimesheetStatus
    from wallet.models import SourceLotStatus

    if project.contract_type == ContractType.CANONE:
        return False
    if project.timesheet_status == TimesheetStatus.CHIUSO:
        return False
    lots = list(project.wallet_source_lots.all())
    if lots:
        return all(lot.status == SourceLotStatus.CHIUSURA_DA_VALIDARE for lot in lots)
    allocations = list(project.wallet_allocations.all())
    return bool(allocations) and all(allocation.status == "CHIUSA" for allocation in allocations)


def project_operational_status(project) -> str:
    from projects.models import ContractType, OfferStatus, TimesheetStatus

    if project.contract_type == ContractType.CANONE:
        return "CANONE"
    if project.timesheet_status == TimesheetStatus.CHIUSO:
        return "CHIUSO"
    if project_closure_ready(project):
        return "CHIUSURA_DA_VALIDARE"

    allocations = list(project.wallet_allocations.all())
    if project.released_to_wallet_days > ZERO or allocations or project.wallet_source_lots.exists():
        return "WALLET"

    if project.offer_status == OfferStatus.INVIATA:
        return "OFFERTA_INVIATA"
    if (
        project.offer_status == OfferStatus.ACCETTATA
        and project.timesheet_status == TimesheetStatus.NON_AVVIATO
    ):
        return "OFFERTA_ACCETTATA"
    if project.timesheet_status == TimesheetStatus.ATTIVO:
        return "IN_CORSO"
    return project.timesheet_status


def unallocated_residual(
    budget_days: Decimal, direct_consumed: Decimal, allocated_out: Decimal
) -> Decimal:
    """R3 in forma pura, usata dai test e dalle validazioni di allocazione."""
    return quantize_days(budget_days - direct_consumed - allocated_out)


def residual_explanation(
    budget_days: Decimal, direct_consumed: Decimal, allocated_out: Decimal
) -> str:
    """Testo del tooltip: spiega sempre come nasce il numero."""
    from domain.money import format_days_it

    residual = unallocated_residual(budget_days, direct_consumed, allocated_out)
    return (
        f"Residuo = {format_days_it(budget_days)} "
        f"- {format_days_it(direct_consumed)} (consuntivi diretti) "
        f"- {format_days_it(allocated_out)} (allocato a wallet) "
        f"= {format_days_it(residual)}"
    )


def projects_with_usable_residual(today: date, years_valid_after_closure: int = 1):
    """Progetti chiusi con data e residuo spendibile, ordinati per scadenza crescente."""
    from projects.models import TimesheetStatus

    first_valid_closure_year = today.year - years_valid_after_closure
    return (
        project_balance_qs()
        .filter(
            timesheet_status=TimesheetStatus.CHIUSO,
            actual_closure_date__isnull=False,
            actual_closure_date__year__gte=first_valid_closure_year,
            residual_days__gt=0,
        )
        .order_by("actual_closure_date", "code")
    )


