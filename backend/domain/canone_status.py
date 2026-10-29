"""R4 — stato di un canone semestrale.

    target alla data = min(monte, base_gg + settimane_trascorse * gg_per_settimana)
    delta            = target - consuntivato        (positivo = sotto target, a favore BMED)
    forecast         = consuntivato + somma dei forecast residui delle sotto-attività

La gestione delle giornate di canone non usate non è definita dalle specifiche: qui resta
solo un indicatore (vedi docs/DECISIONI_APERTE.md, voce D-01). Nessun travaso automatico
verso il wallet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from domain.money import ZERO, format_days_it, quantize_days

DAYS_OUTPUT = DecimalField(max_digits=12, decimal_places=4)
UNDERUSE_THRESHOLD = Decimal("0.95")


def subactivity_state(reserved_days: Decimal, consumed_days: Decimal) -> str:
    """Stato derivato dal totale netto dei consuntivi, inclusi gli storni."""
    return "IN_CORSO" if consumed_days < reserved_days else "CHIUSO"


def weeks_elapsed(start_date: date, today: date) -> int:
    """Settimane intere trascorse dall'inizio del semestre, mai negative."""
    if today <= start_date:
        return 0
    return max(0, (today - start_date).days // 7)


def target_days(
    *,
    total_days: Decimal,
    base_days: Decimal,
    days_per_week: Decimal,
    weeks: int,
    cap_at_total: bool = True,
) -> Decimal:
    """Target progressivo alla data (R4)."""
    raw = base_days + (days_per_week * Decimal(weeks))
    if cap_at_total:
        raw = min(raw, total_days)
    return quantize_days(raw)


def target_formula_text(
    *, base_days: Decimal, days_per_week: Decimal, weeks: int, total_days: Decimal
) -> str:
    """Testo del tooltip: la formula con i suoi addendi, come la vede l'utente."""
    computed = base_days + days_per_week * Decimal(weeks)
    return (
        f"Target = min({format_days_it(total_days)}; {format_days_it(base_days)} "
        f"+ {weeks} settimane x {format_days_it(days_per_week)}) "
        f"= min({format_days_it(total_days)}; {format_days_it(computed)})"
    )


@dataclass
class OfficeBreakdown:
    office: str
    consumed_days: Decimal = ZERO
    quarter_estimate_days: Decimal = ZERO
    forecast_remaining_days: Decimal = ZERO
    subactivities: int = 0


@dataclass
class CanoneStatus:
    """Vista calcolata `canone_status` (par. 3.2)."""

    semester: str
    total_days: Decimal
    consumed_days: Decimal
    weeks: int
    target: Decimal
    delta: Decimal
    forecast: Decimal
    forecast_ratio: Decimal
    projection: str
    unused_days: Decimal
    formula: str
    by_office: dict[str, OfficeBreakdown] = field(default_factory=dict)

    @property
    def is_underused(self) -> bool:
        return self.forecast < quantize_days(self.total_days * UNDERUSE_THRESHOLD)

    @property
    def is_overused(self) -> bool:
        return self.consumed_days > self.total_days

    def as_dict(self) -> dict:
        return {
            "semestre": self.semester,
            "monte": self.total_days,
            "consuntivato": self.consumed_days,
            "settimane_trascorse": self.weeks,
            "target_alla_data": self.target,
            "delta": self.delta,
            "forecast": self.forecast,
            "percentuale_forecast": self.forecast_ratio,
            "proiezione": self.projection,
            "giornate_non_usate_previste": self.unused_days,
            "formula_target": self.formula,
            "per_ufficio": {
                office: {
                    "consuntivato": row.consumed_days,
                    "stima_trimestre": row.quarter_estimate_days,
                    "forecast_residuo": row.forecast_remaining_days,
                    "sottoattivita": row.subactivities,
                }
                for office, row in self.by_office.items()
            },
        }


def subactivity_balance_qs(canone):
    """Sotto-attività con il consuntivato annotato."""
    from canone.models import CanoneSubactivity
    from timesheets.models import TimesheetEntry

    consumed = (
        TimesheetEntry.objects.filter(canone_subactivity=OuterRef("pk"))
        .order_by()
        .values("canone_subactivity")
        .annotate(total=Sum("days", output_field=DAYS_OUTPUT))
        .values("total")[:1]
    )
    return (
        CanoneSubactivity.objects.filter(canone=canone)
        .annotate(
            consumed_days=Coalesce(
                Subquery(consumed, output_field=DAYS_OUTPUT),
                Value(ZERO, output_field=DAYS_OUTPUT),
            )
        )
        .order_by("office", "title")
    )


def canone_status(canone, *, today: date | None = None) -> CanoneStatus:
    """Calcola gli indicatori di un canone. Il consuntivato arriva dalle sotto-attività."""
    from django.utils import timezone

    today = today or timezone.localdate()
    start = canone.start_date
    if start is None:
        start_iso, _ = canone.semester_bounds(canone.semester)
        start = date.fromisoformat(start_iso)

    # Le settimane dichiarate nell'estratto hanno la precedenza solo se il semestre non è
    # ancora iniziato nel calendario reale (import di dati storici).
    weeks = weeks_elapsed(start, today)
    if canone.end_date and today > canone.end_date:
        weeks = weeks_elapsed(start, canone.end_date)

    rows = list(subactivity_balance_qs(canone))
    consumed = quantize_days(sum((row.consumed_days for row in rows), ZERO))
    forecast_remaining = quantize_days(
        sum((max(row.reserved_days - row.consumed_days, ZERO) for row in rows), ZERO)
    )

    target = target_days(
        total_days=canone.total_days,
        base_days=canone.target_base_days,
        days_per_week=canone.target_days_per_week,
        weeks=weeks,
        cap_at_total=canone.cap_at_total,
    )
    forecast = quantize_days(consumed + forecast_remaining)
    ratio = quantize_days(forecast / canone.total_days * 100) if canone.total_days else ZERO
    unused = quantize_days(max(canone.total_days - forecast, ZERO))

    if forecast > canone.total_days:
        projection = "Sovra-utilizzo previsto"
    elif forecast < quantize_days(canone.total_days * UNDERUSE_THRESHOLD):
        projection = "Sotto-utilizzo previsto"
    else:
        projection = "In linea con il monte"

    status = CanoneStatus(
        semester=canone.semester,
        total_days=canone.total_days,
        consumed_days=consumed,
        weeks=weeks,
        target=target,
        delta=quantize_days(target - consumed),
        forecast=forecast,
        forecast_ratio=ratio,
        projection=projection,
        unused_days=unused,
        formula=target_formula_text(
            base_days=canone.target_base_days,
            days_per_week=canone.target_days_per_week,
            weeks=weeks,
            total_days=canone.total_days,
        ),
    )

    for row in rows:
        office = row.office or "SENZA_UFFICIO"
        breakdown = status.by_office.setdefault(office, OfficeBreakdown(office=office))
        breakdown.consumed_days = quantize_days(breakdown.consumed_days + row.consumed_days)
        breakdown.quarter_estimate_days = quantize_days(
            breakdown.quarter_estimate_days + (row.quarter_estimate_days or ZERO)
        )
        breakdown.forecast_remaining_days = quantize_days(
            breakdown.forecast_remaining_days + max(row.reserved_days - row.consumed_days, ZERO)
        )
        breakdown.subactivities += 1

    return status


def canone_burndown(canone, *, today: date | None = None) -> list[dict]:
    """Serie settimanale consuntivato / target per il grafico di burn-down."""
    from django.utils import timezone

    from timesheets.models import TimesheetEntry

    today = today or timezone.localdate()
    start_iso, end_iso = canone.semester_bounds(canone.semester)
    start = canone.start_date or date.fromisoformat(start_iso)
    end = canone.end_date or date.fromisoformat(end_iso)

    monthly = (
        TimesheetEntry.objects.filter(canone_subactivity__canone=canone)
        .values("period")
        .annotate(total=Sum("days", output_field=DAYS_OUTPUT))
        .order_by("period")
    )
    by_month = {row["period"]: row["total"] for row in monthly}

    series: list[dict] = []
    total_weeks = max(1, (end - start).days // 7)
    for week in range(total_weeks + 1):
        day = min(start + timedelta(weeks=week), end)
        month_key = day.replace(day=1)
        cumulative = quantize_days(
            sum((value for key, value in by_month.items() if key <= month_key), ZERO)
        )
        series.append(
            {
                "settimana": week,
                "data": day,
                "mese": month_key,
                "consuntivato": cumulative if day <= today else None,
                "target": target_days(
                    total_days=canone.total_days,
                    base_days=canone.target_base_days,
                    days_per_week=canone.target_days_per_week,
                    weeks=week,
                    cap_at_total=canone.cap_at_total,
                ),
            }
        )
    return series
