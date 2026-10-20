"""R2 (scadenza dei residui) e R3 (residuo di progetto).

R2 — Un progetto ATTIVO non ha scadenza dei residui, qualunque sia l'anno di apertura.
     Quando passa a CHIUSO conta l'anno della data di chiusura: il residuo si usa
     nell'anno di chiusura e nei successivi `anni_validita_dopo_chiusura` (default 1),
     poi scade dal 1 gennaio dell'anno seguente.
     Esempio: chiuso il 15/11/2025 -> utilizzabile fino al 31/12/2026, scaduto dal 01/01/2027.

R3 — residuo = budget - consuntivi diretti - allocazioni wallet in uscita.
     Mai un numero scritto a mano: sempre calcolato dal database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from domain.money import ZERO, quantize_days

DAYS_OUTPUT = DecimalField(max_digits=12, decimal_places=4)


class ResidualState(str):
    """Stato di validità di un residuo, condiviso fra API e interfaccia."""

    VALIDO = "VALIDO"
    IN_SCADENZA = "IN_SCADENZA"
    SCADUTO = "SCADUTO"
    DA_VERIFICARE = "DA_VERIFICARE"


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
            "Stato della consuntivazione da confermare: residuo potenziale.",
        )

    return ResidualValidity(
        ResidualState.VALIDO,
        None,
        None,
        "Progetto non chiuso: il residuo non ha scadenza.",
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
    """Progetti il cui residuo è spendibile (R2), ordinati per scadenza crescente.

    L'ordinamento serve alla UI: si consuma prima ciò che scade prima.
    """
    from projects.models import TimesheetStatus

    expiry_limit = date(today.year - years_valid_after_closure - 1, 12, 31)
    return (
        project_balance_qs()
        .filter(residual_days__gt=0)
        .exclude(timesheet_status=TimesheetStatus.DA_VERIFICARE)
        .exclude(
            Q(timesheet_status=TimesheetStatus.CHIUSO)
            & (Q(actual_closure_date__isnull=True) | Q(actual_closure_date__lte=expiry_limit))
        )
        .order_by(F("actual_closure_date").asc(nulls_last=True), "code")
    )
