"""Aritmetica delle giornate/uomo.

Le giornate sono dati contabili: sempre Decimal con 4 decimali, mai float.
L'arrotondamento è ROUND_HALF_UP; i 2 decimali servono solo in visualizzazione.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

DAYS_QUANT = Decimal("0.0001")
DISPLAY_QUANT = Decimal("0.01")
MONEY_QUANT = Decimal("0.01")
ZERO = Decimal("0.0000")
PPM_GRANULARITY = Decimal("0.0625")


class DaysValueError(ValueError):
    """Valore non convertibile in giornate."""


def to_days(value: Any, *, field: str = "giornate") -> Decimal:
    """Converte in Decimal(.4) passando sempre da stringa, così da non ereditare
    gli artefatti binari dei float (es. 0.1 + 0.2)."""
    if value is None or value == "":
        raise DaysValueError(f"{field}: valore mancante.")
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, bool):
        raise DaysValueError(f"{field}: valore booleano non ammesso.")
    else:
        text = str(value).strip().replace(" ", "")
        if text.count(",") == 1 and text.count(".") == 0:
            text = text.replace(",", ".")  # formato italiano: 1,5 -> 1.5
        else:
            text = text.replace(",", "")  # separatore di migliaia
        try:
            candidate = Decimal(text)
        except InvalidOperation as exc:
            raise DaysValueError(f"{field}: {value!r} non è un numero valido.") from exc
    if not candidate.is_finite():
        raise DaysValueError(f"{field}: valore non finito.")
    return quantize_days(candidate)


def quantize_money(value: Decimal) -> Decimal:
    """Arrotonda importi monetari ai centesimi con ROUND_HALF_UP."""
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def cost_for_days(days: Decimal, daily_cost: Decimal) -> Decimal:
    """Calcola il costo di giornate nette usando il costo globale corrente."""
    return quantize_money(days * daily_cost)


def to_days_or_none(value: Any, *, field: str = "giornate") -> Decimal | None:
    if value is None or value == "":
        return None
    return to_days(value, field=field)


def quantize_days(value: Decimal) -> Decimal:
    return value.quantize(DAYS_QUANT, rounding=ROUND_HALF_UP)


def quantize_display(value: Decimal) -> Decimal:
    return value.quantize(DISPLAY_QUANT, rounding=ROUND_HALF_UP)


def days_sum(*values: Decimal | None) -> Decimal:
    total = ZERO
    for value in values:
        if value is not None:
            total += value
    return quantize_days(total)


def is_within_tolerance(delta: Decimal, tolerance: Decimal) -> bool:
    """La riconciliazione considera uguali due valori entro la tolleranza inclusa."""
    return abs(delta) <= tolerance


def format_days_it(value: Decimal | None) -> str:
    """Formato italiano per log ed export: 1.234,56 gg."""
    if value is None:
        return "-"
    quantized = quantize_display(value)
    sign = "-" if quantized < 0 else ""
    integer, _, decimals = f"{abs(quantized):.2f}".partition(".")
    groups: list[str] = []
    while len(integer) > 3:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    groups.insert(0, integer)
    return f"{sign}{'.'.join(groups)},{decimals} gg"
