"""R4 — target, delta e forecast del canone semestrale.

Caso obbligatorio 11.7: monte 173, consuntivato 100,27, 15 settimane
-> target = 2 + 15 x 6,69 = 102,35 e delta = +2,08 a favore.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.canone_status import (
    UNDERUSE_THRESHOLD,
    canone_burndown,
    canone_status,
    target_days,
    target_formula_text,
    weeks_elapsed,
)
from tests.factories import CanoneFactory, CanoneSubactivityFactory, TimesheetEntryFactory


class TestSettimaneTrascorse:
    def test_conta_settimane_intere(self):
        assert weeks_elapsed(date(2026, 7, 1), date(2026, 7, 7)) == 0
        assert weeks_elapsed(date(2026, 7, 1), date(2026, 7, 8)) == 1
        assert weeks_elapsed(date(2026, 7, 1), date(2026, 10, 16)) == 15
        assert weeks_elapsed(date(2026, 7, 1), date(2026, 10, 20)) == 15

    def test_mai_negative_prima_dell_inizio(self):
        assert weeks_elapsed(date(2026, 7, 1), date(2026, 6, 1)) == 0


class TestTarget:
    def test_caso_11_7_target_alla_quindicesima_settimana(self):
        assert target_days(
            total_days=Decimal("173.0000"),
            base_days=Decimal("2.0000"),
            days_per_week=Decimal("6.6900"),
            weeks=15,
        ) == Decimal("102.3500")

    def test_il_target_e_limitato_al_monte(self):
        assert target_days(
            total_days=Decimal("173.0000"),
            base_days=Decimal("2.0000"),
            days_per_week=Decimal("6.6900"),
            weeks=40,
        ) == Decimal("173.0000")

    def test_senza_cap_il_target_supera_il_monte(self):
        assert target_days(
            total_days=Decimal("173.0000"),
            base_days=Decimal("2.0000"),
            days_per_week=Decimal("6.6900"),
            weeks=40,
            cap_at_total=False,
        ) == Decimal("269.6000")

    def test_la_formula_e_spiegata_per_il_tooltip(self):
        text = target_formula_text(
            base_days=Decimal("2.0000"),
            days_per_week=Decimal("6.6900"),
            weeks=15,
            total_days=Decimal("173.0000"),
        )
        assert "15 settimane" in text
        assert "6,69 gg" in text
        assert "102,35 gg" in text


@pytest.mark.django_db
class TestStatoCanone:
    def build_s2(self, consumed: list[str], forecast: list[str] | None = None):
        canone = CanoneFactory(semester="2026-S2")
        forecast = forecast or ["0"] * len(consumed)
        for index, (days, remaining) in enumerate(zip(consumed, forecast, strict=True)):
            subactivity = CanoneSubactivityFactory(
                canone=canone,
                title=f"#30000{index} attività {index}",
                forecast_remaining_days=Decimal(remaining),
            )
            if Decimal(days) != 0:
                TimesheetEntryFactory(
                    canone_subactivity=subactivity,
                    days=Decimal(days),
                    period=date(2026, 10, 1),
                )
        return canone

    def test_caso_11_7_delta_a_favore(self):
        canone = self.build_s2(["60.0000", "40.2700"])
        status = canone_status(canone, today=date(2026, 10, 16))

        assert status.total_days == Decimal("173.0000")
        assert status.consumed_days == Decimal("100.2700")
        assert status.weeks == 15
        assert status.target == Decimal("102.3500")
        assert status.delta == Decimal("2.0800")  # positivo: sotto target, a favore di BMED

    def test_il_forecast_somma_i_residui_delle_sottoattivita(self):
        canone = self.build_s2(["60.0000", "40.2700"], forecast=["30.0000", "-5.0000"])
        status = canone_status(canone, today=date(2026, 10, 16))
        assert status.forecast == Decimal("125.2700")
        assert status.unused_days == Decimal("47.7300")

    def test_sotto_utilizzo_previsto(self):
        canone = self.build_s2(["100.2700"], forecast=["10.0000"])
        status = canone_status(canone, today=date(2026, 10, 16))
        assert status.forecast == Decimal("110.2700")
        assert status.forecast < canone.total_days * UNDERUSE_THRESHOLD
        assert status.is_underused
        assert status.projection == "Sotto-utilizzo previsto"

    def test_sovra_utilizzo_previsto(self):
        canone = self.build_s2(["170.0000"], forecast=["20.0000"])
        status = canone_status(canone, today=date(2026, 10, 16))
        assert status.projection == "Sovra-utilizzo previsto"
        assert not status.is_overused  # consuntivato ancora sotto il monte

    def test_sforamento_del_monte(self):
        canone = self.build_s2(["180.0000"])
        status = canone_status(canone, today=date(2026, 12, 1))
        assert status.is_overused

    def test_raggruppamento_per_ufficio(self):
        canone = CanoneFactory(semester="2026-S2")
        for office, days in (("EA", "10.0000"), ("SA", "5.0000"), ("SA", "2.5000")):
            subactivity = CanoneSubactivityFactory(
                canone=canone, office=office, quarter_estimate_days=Decimal("1.0000")
            )
            TimesheetEntryFactory(canone_subactivity=subactivity, days=Decimal(days))

        status = canone_status(canone, today=date(2026, 10, 16))
        assert status.by_office["EA"].consumed_days == Decimal("10.0000")
        assert status.by_office["SA"].consumed_days == Decimal("7.5000")
        assert status.by_office["SA"].subactivities == 2
        assert status.by_office["SA"].quarter_estimate_days == Decimal("2.0000")

    def test_le_settimane_si_fermano_a_fine_semestre(self):
        canone = self.build_s2(["100.0000"])
        status = canone_status(canone, today=date(2027, 3, 1))
        assert status.weeks == weeks_elapsed(date(2026, 7, 1), date(2026, 12, 31))
        assert status.target == Decimal("173.0000")

    def test_burndown_ha_una_riga_per_settimana(self):
        canone = self.build_s2(["50.0000"])
        series = canone_burndown(canone, today=date(2026, 10, 16))
        assert series[0]["settimana"] == 0
        assert series[-1]["target"] == Decimal("173.0000")
        # Oltre la data odierna il consuntivato non viene disegnato.
        assert series[-1]["consuntivato"] is None

    def test_il_dizionario_e_pronto_per_lapi(self):
        canone = self.build_s2(["100.2700"])
        payload = canone_status(canone, today=date(2026, 10, 16)).as_dict()
        assert payload["monte"] == Decimal("173.0000")
        assert payload["target_alla_data"] == Decimal("102.3500")
        assert payload["delta"] == Decimal("2.0800")
        assert "formula_target" in payload
