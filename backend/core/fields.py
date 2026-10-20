"""Campi riutilizzabili per i dati contabili."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import models

DAYS_MAX_DIGITS = 8
DAYS_DECIMAL_PLACES = 4
ZERO_DAYS = Decimal("0.0000")


class DaysField(models.DecimalField):
    """Giornate/uomo: sempre Decimal(8,4), mai float."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", DAYS_MAX_DIGITS)
        kwargs.setdefault("decimal_places", DAYS_DECIMAL_PLACES)
        super().__init__(**kwargs)

    def deconstruct(self) -> tuple[str, str, Any, dict[str, Any]]:
        name, _path, args, kwargs = super().deconstruct()
        kwargs.pop("max_digits", None)
        kwargs.pop("decimal_places", None)
        return name, "core.fields.DaysField", args, kwargs
