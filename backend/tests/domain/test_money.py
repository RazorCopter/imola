"""Le giornate sono dati contabili: nessun float, nessuna sorpresa di arrotondamento."""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.money import (
    DaysValueError,
    days_sum,
    format_days_it,
    is_within_tolerance,
    quantize_days,
    quantize_display,
    to_days,
    to_days_or_none,
)


class TestToDays:
    def test_converte_passando_da_stringa_senza_artefatti_binari(self):
        # 0.1 + 0.2 in float darebbe 0.30000000000000004.
        assert to_days(0.1) + to_days(0.2) == Decimal("0.3000")

    def test_mantiene_la_granularita_ppm(self):
        assert to_days(0.0625) == Decimal("0.0625")
        assert to_days(8.6875) == Decimal("8.6875")

    def test_accetta_decimal_stringa_e_intero(self):
        assert to_days(Decimal("1.5")) == Decimal("1.5000")
        assert to_days("2.25") == Decimal("2.2500")
        assert to_days(3) == Decimal("3.0000")

    def test_accetta_il_formato_italiano(self):
        assert to_days("1,5") == Decimal("1.5000")

    def test_ignora_i_separatori_di_migliaia(self):
        assert to_days("1,234.56") == Decimal("1234.5600")

    def test_arrotonda_half_up_alla_quarta_cifra(self):
        assert to_days("1.00005") == Decimal("1.0001")
        assert to_days("1.00004") == Decimal("1.0000")

    @pytest.mark.parametrize("value", [None, "", "abc", True, float("nan"), float("inf")])
    def test_rifiuta_i_valori_non_validi(self, value):
        with pytest.raises(DaysValueError):
            to_days(value)

    def test_or_none_tollera_i_campi_vuoti(self):
        assert to_days_or_none(None) is None
        assert to_days_or_none("") is None
        assert to_days_or_none("0") == Decimal("0.0000")


class TestQuantizzazione:
    def test_le_giornate_hanno_quattro_decimali(self):
        assert quantize_days(Decimal("1.23456")) == Decimal("1.2346")

    def test_la_visualizzazione_ha_due_decimali(self):
        assert quantize_display(Decimal("102.3450")) == Decimal("102.35")

    def test_somma_ignora_i_valori_assenti(self):
        assert days_sum(Decimal("1.5"), None, Decimal("2.25")) == Decimal("3.7500")


class TestTolleranza:
    def test_il_delta_sulla_soglia_e_dentro_tolleranza(self):
        assert is_within_tolerance(Decimal("0.0100"), Decimal("0.0100"))
        assert is_within_tolerance(Decimal("-0.0100"), Decimal("0.0100"))

    def test_il_delta_oltre_la_soglia_e_fuori_tolleranza(self):
        assert not is_within_tolerance(Decimal("0.0101"), Decimal("0.0100"))

    def test_caso_11_9_riconciliazione_entro_tolleranza(self):
        # IM25138: interno 5,25 + 3,44 = 8,69 contro PPM 8,6875 -> delta 0,0025.
        interno = to_days("5.25") + to_days("3.44")
        delta = interno - to_days("8.6875")
        assert delta == Decimal("0.0025")
        assert is_within_tolerance(delta, Decimal("0.0100"))


class TestFormatoItaliano:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (Decimal("1234.56"), "1.234,56 gg"),
            (Decimal("130.8900"), "130,89 gg"),
            (Decimal("0"), "0,00 gg"),
            (Decimal("-7.8"), "-7,80 gg"),
            (Decimal("1234567.891"), "1.234.567,89 gg"),
            (None, "-"),
        ],
    )
    def test_formatta_con_separatori_italiani(self, value, expected):
        assert format_days_it(value) == expected
