"""Serializzazione JSON dei dati contabili.

`COERCE_DECIMAL_TO_STRING` di DRF vale solo per i campi dei serializer: un Decimal messo
direttamente in una Response verrebbe convertito in float dall'encoder predefinito, con
perdita di precisione (0.1 + 0.2, 8.6875 arrotondato, ecc.). Qui i Decimal diventano
**stringhe** sempre, così le giornate attraversano la rete intatte e il frontend le
converte solo per la vista.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework.renderers import JSONRenderer
from rest_framework.utils.encoders import JSONEncoder


class DaysJSONEncoder(JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class DaysJSONRenderer(JSONRenderer):
    """Renderer predefinito dell'API: nessun Decimal diventa float."""

    encoder_class = DaysJSONEncoder
