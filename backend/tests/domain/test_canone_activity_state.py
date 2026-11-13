from decimal import Decimal

import pytest

from domain.canone_status import subactivity_state


@pytest.mark.parametrize(
    ("reserved", "consumed", "expected"),
    [
        ("10", "0", "IN_CORSO"),
        ("10", "9.9999", "IN_CORSO"),
        ("10", "10", "CHIUSO"),
        ("10", "11", "CHIUSO"),
        ("0", "0", "CHIUSO"),
    ],
)
def test_stato_attivita_derivato(reserved, consumed, expected):
    assert subactivity_state(Decimal(reserved), Decimal(consumed)) == expected


def test_stato_dichiarato_aperto_vince_sul_derivato():
    """Un'attività forzata aperta resta IN_CORSO anche a consuntivo esaurito o superato."""
    assert subactivity_state(Decimal("10"), Decimal("10"), declared_open=True) == "IN_CORSO"
    assert subactivity_state(Decimal("10"), Decimal("12"), declared_open=True) == "IN_CORSO"
