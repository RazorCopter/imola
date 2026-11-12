"""Test del parser dell'estratto operativo settimanale.

Non toccano il database: il parser è puro, e questi test girano anche dove non c'è
PostgreSQL. I numeri attesi sul workbook reale vengono da docs/importazione_plan.md §2.1.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from importers.operational_excel import (
    Section,
    WorkbookStructureError,
    parse_days,
    parse_period,
    parse_workbook,
)

REAL_WORKBOOK = (
    Path(__file__).resolve().parents[3] / "docs" / "Andamento_operativo_Banca_mediolanum_2026.xlsx"
)

HEADERS = {
    Section.PROGETTI: ["Progetto", "Collaboratore", "Data", "Note", "gg tot"],
    Section.WALLET: ["Progetto", "Sottoprogetto", "Collaboratore", "Data", "Note", "gg tot"],
    Section.ORGANICO: ["Sotto progetto", "Collaboratore", "Data", "Note", "gg tot"],
}


def build_workbook(sheets: dict[str, list[list]]) -> BytesIO:
    """Costruisce un xlsx in memoria. Il primo elemento di ogni foglio è l'intestazione."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream


def progetti(*rows: list) -> BytesIO:
    """Un workbook con il solo foglio Progetti e le righe date."""
    return build_workbook({"Progetti": [HEADERS[Section.PROGETTI], *rows]})


def one_row(**overrides) -> list:
    base = {
        "project": "IM26294-3313-BMED-ARCH-SELEZIONE-SOFTWARE-RISK",
        "collaborator": "Venturi Simone",
        "period": dt.date(2026, 11, 3),
        "note": "Redazione paragrafo 4.1.2.1 Clonazione Campagne",
        "days": 0.25,
    }
    base.update(overrides)
    return [base["project"], base["collaborator"], base["period"], base["note"], base["days"]]


def problems_at(parsed, cell: str):
    return [p for p in parsed.all_problems if p.cell == cell]


# --------------------------------------------------------------------------- giornate


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.125, "0.1250"),
        (0.375, "0.3750"),
        (0.0625, "0.0625"),
        (0.1875, "0.1875"),
        (1, "1.0000"),
        ("0,375", "0.3750"),
        ("0.375", "0.3750"),
        (" 0,5 ", "0.5000"),
        (Decimal("0.3125"), "0.3125"),
    ],
)
def test_parse_days_normalizza(raw, expected):
    days, warning = parse_days(raw)
    assert days == Decimal(expected)
    assert days.as_tuple().exponent == -4
    assert not warning


def test_parse_days_non_usa_il_float_binario():
    """`Decimal(0.375)` porterebbe la rappresentazione binaria: deve passare per str."""
    days, _ = parse_days(0.375)
    assert str(days) == "0.3750"


def test_parse_days_avvisa_quando_arrotonda():
    days, warning = parse_days(0.12345)
    assert days == Decimal("0.1235")
    assert "arrotondate" in warning


@pytest.mark.parametrize(
    "raw", [0, -1, "0", "-0,5", "mezza giornata", "", None, True, float("inf")]
)
def test_parse_days_rifiuta(raw):
    with pytest.raises(ValueError):
        parse_days(raw)


# ------------------------------------------------------------------------------ date


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (dt.datetime(2026, 11, 3, tzinfo=dt.UTC), dt.date(2026, 11, 3)),
        (dt.date(2026, 11, 3), dt.date(2026, 11, 3)),
        ("03/11/2026", dt.date(2026, 11, 3)),
        ("2026-11-03", dt.date(2026, 11, 3)),
        (46325, dt.date(2026, 10, 30)),
        (46331, dt.date(2026, 11, 5)),
    ],
)
def test_parse_period(raw, expected):
    assert parse_period(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "3 nov", "31/02/2026", "domani", True])
def test_parse_period_rifiuta(raw):
    with pytest.raises(ValueError):
        parse_period(raw)


def test_data_mancante_non_diventa_oggi():
    parsed = parse_workbook(progetti(one_row(period=None)))
    assert parsed.has_errors
    assert parsed.sheet(Section.PROGETTI).rows == []
    assert any("Data mancante" in p.message for p in parsed.errors)


# -------------------------------------------------------------------------- struttura


def test_intestazioni_abbinate_per_nome_non_per_posizione():
    """Colonne in ordine diverso: l'abbinamento è per nome (§8.1)."""
    stream = build_workbook(
        {
            "Progetti": [
                ["gg tot", "Note", "Data", "Collaboratore", "Progetto"],
                [0.25, "SAL", dt.date(2026, 11, 3), "Venturi Simone", "IM26294"],
            ]
        }
    )
    sheet = parse_workbook(stream).sheet(Section.PROGETTI)
    assert sheet.errors == []
    row = sheet.rows[0]
    assert (row.project, row.collaborator, row.days) == (
        "IM26294",
        "Venturi Simone",
        Decimal("0.2500"),
    )


@pytest.mark.parametrize("header", ["Sotto progetto", "Sottoprogetto", "SOTTO  PROGETTO"])
def test_sotto_progetto_equivale_a_sottoprogetto(header):
    stream = build_workbook(
        {
            "Organico_Allargato": [
                [header, "Collaboratore", "Data", "Note", "gg tot"],
                ["MNG - GESTIONE", "Ravagli Andrea", dt.date(2026, 11, 5), "Tool", 0.375],
            ]
        }
    )
    sheet = parse_workbook(stream).sheet(Section.ORGANICO)
    assert sheet.errors == []
    assert sheet.rows[0].subproject == "MNG - GESTIONE"


def test_foglio_progetto_e_alias_di_progetti():
    stream = build_workbook({"Progetto": [HEADERS[Section.PROGETTI], one_row()]})
    assert parse_workbook(stream).sheet(Section.PROGETTI).rows_valid == 1


def test_foglio_non_previsto_e_solo_un_avviso():
    stream = build_workbook(
        {
            "Progetti": [HEADERS[Section.PROGETTI], one_row()],
            "Capacity Mensile": [["qualcosa"], [1]],
        }
    )
    parsed = parse_workbook(stream)
    assert not parsed.has_errors
    assert any("Capacity Mensile" in p.message for p in parsed.warnings)


def test_intestazione_mancante_e_errore_sulla_prima_riga():
    stream = build_workbook(
        {"Progetti": [["Progetto", "Collaboratore", "Data", "Note"], ["IM1", "X Y", None, "n"]]}
    )
    parsed = parse_workbook(stream)
    errors = parsed.sheet(Section.PROGETTI).errors
    assert len(errors) == 1
    assert errors[0].cell == "A1"
    assert "gg tot" in errors[0].message


def test_file_senza_fogli_attesi():
    with pytest.raises(WorkbookStructureError):
        parse_workbook(build_workbook({"info": [["a"], [1]]}))


def test_file_non_xlsx():
    with pytest.raises(WorkbookStructureError):
        parse_workbook(BytesIO(b"non sono un xlsx"))


def test_sezione_assente_e_un_avviso():
    parsed = parse_workbook(progetti(one_row()))
    messages = [p.message for p in parsed.warnings]
    assert any("Wallet" in m for m in messages)
    assert any("Organico allargato" in m for m in messages)


# ------------------------------------------------------------------- righe e totali


def test_riga_due_e_dati_non_un_modello():
    """TEMPLATE.md la descrive come modello di formato, ma nell'estratto contiene dati."""
    sheet = parse_workbook(progetti(one_row())).sheet(Section.PROGETTI)
    assert sheet.rows[0].excel_row == 2


def test_righe_vuote_ignorate_e_non_contate():
    stream = progetti(one_row(), [None, None, None, None, None], one_row(days=0.5))
    sheet = parse_workbook(stream).sheet(Section.PROGETTI)
    assert (sheet.rows_valid, sheet.rows_read, sheet.rows_empty) == (2, 2, 1)


def test_riga_di_totale_esclusa_e_totale_ricalcolato():
    """La formula non genera consuntivi e il totale si somma dalle righe (§8.3)."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheet = workbook.create_sheet("Progetti")
    sheet.append(HEADERS[Section.PROGETTI])
    sheet.append(one_row(days=0.375))
    sheet.append(one_row(days=0.125))
    sheet["E4"] = "=SUM(E2:E3)"
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)

    result = parse_workbook(stream).sheet(Section.PROGETTI)
    assert result.rows_valid == 2
    assert result.rows_formula == 1
    assert result.days_total == Decimal("0.5000")
    assert all(row.excel_row != 4 for row in result.rows)


def test_formula_in_un_campo_informativo_e_errore_comprensibile():
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheet = workbook.create_sheet("Progetti")
    sheet.append(HEADERS[Section.PROGETTI])
    sheet.append(one_row())
    sheet["D2"] = "=CONCATENATE(A2)"
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)

    parsed = parse_workbook(stream)
    assert [p.cell for p in parsed.errors] == ["D2"]
    assert "Formula" in parsed.errors[0].message


# ----------------------------------------------------------------- campi obbligatori


@pytest.mark.parametrize(
    ("override", "cell", "atteso"),
    [
        ({"note": ""}, "D2", "Descrizione obbligatoria"),
        ({"note": "x" * 301}, "D2", "301 caratteri"),
        ({"collaborator": ""}, "B2", "Collaboratore mancante"),
        ({"project": ""}, "A2", "Progetto mancante"),
        ({"days": None}, "E2", "Giornate mancanti"),
        ({"days": "mezza"}, "E2", "non numeriche"),
        ({"days": 0}, "E2", "maggiori di zero"),
        ({"days": -0.5}, "E2", "maggiori di zero"),
    ],
)
def test_campi_invalidi_sono_errori_ancorati_alla_cella(override, cell, atteso):
    parsed = parse_workbook(progetti(one_row(**override)))
    errors = parsed.errors
    assert [p.cell for p in errors] == [cell]
    assert atteso in errors[0].message
    assert errors[0].sheet == "Progetti"
    assert errors[0].excel_row == 2
    assert parsed.sheet(Section.PROGETTI).rows == []


def test_riferimento_cella_segue_lo_spostamento_delle_colonne():
    """Il riferimento viene dalla cella reale, non da una posizione presunta."""
    stream = build_workbook(
        {
            "Progetti": [
                ["gg tot", "Note", "Data", "Collaboratore", "Progetto"],
                [None, "SAL", dt.date(2026, 11, 3), "Venturi Simone", "IM26294"],
            ]
        }
    )
    parsed = parse_workbook(stream)
    assert [p.cell for p in parsed.errors] == ["A2"]


# -------------------------------------------------------------------- destinazioni


def test_wallet_tiene_progetto_e_sottoprogetto():
    stream = build_workbook(
        {
            "Wallet": [
                HEADERS[Section.WALLET],
                [
                    "IM26254-3313-BMED-ARCH-SOLUTION-DESIGN-GESTIONE-DOPPIO-CR",
                    "Wallet 2026 Migrazione OSB14 POC",
                    "Nicoletti Pietro",
                    dt.date(2026, 10, 30),
                    "Build componenti osb14",
                    0.375,
                ],
            ]
        }
    )
    row = parse_workbook(stream).sheet(Section.WALLET).rows[0]
    assert row.subproject == "Wallet 2026 Migrazione OSB14 POC"
    assert row.destination_label.endswith("/ Wallet 2026 Migrazione OSB14 POC")


def test_le_sezioni_restano_indipendenti():
    """La stessa voce nei due fogli genera due righe: nessuna esclusione (§3.5)."""
    comune = {
        "collaborator": "Nicoletti Pietro",
        "period": dt.date(2026, 10, 30),
        "days": 0.375,
    }
    stream = build_workbook(
        {
            "Progetti": [
                HEADERS[Section.PROGETTI],
                ["IM26254", comune["collaborator"], comune["period"], "Build", comune["days"]],
            ],
            "Wallet": [
                HEADERS[Section.WALLET],
                [
                    "IM26254",
                    "Wallet 2026 Migrazione OSB14 POC",
                    comune["collaborator"],
                    comune["period"],
                    "Build",
                    comune["days"],
                ],
            ],
        }
    )
    parsed = parse_workbook(stream)
    assert len(parsed.rows) == 2
    assert {row.section for row in parsed.rows} == {Section.PROGETTI, Section.WALLET}
    assert parsed.days_total == Decimal("0.7500")


# --------------------------------------------------------------- workbook reale


@pytest.fixture(scope="module")
def parsed():
    if not REAL_WORKBOOK.exists():
        pytest.skip("estratto reale non presente")
    return parse_workbook(REAL_WORKBOOK)


@pytest.mark.skipif(not REAL_WORKBOOK.exists(), reason="estratto reale non presente")
class TestWorkbookReale:
    """Numeri verificati sul file in docs/, allineati al §2.1 del piano."""

    @pytest.mark.parametrize(
        ("section", "righe", "giornate", "formule"),
        [
            (Section.PROGETTI, 21, "8.6875", 0),
            (Section.WALLET, 7, "3.1250", 1),
            (Section.ORGANICO, 17, "5.7500", 1),
        ],
    )
    def test_conteggi_per_foglio(self, parsed, section, righe, giornate, formule):
        sheet = parsed.sheet(section)
        assert sheet.rows_valid == righe
        assert sheet.days_total == Decimal(giornate)
        assert sheet.rows_formula == formule

    def test_totale_workbook(self, parsed):
        assert len(parsed.rows) == 45
        assert parsed.days_total == Decimal("17.5625")

    def test_nessun_errore(self, parsed):
        assert [str(p) for p in parsed.errors] == []

    def test_stringhe_inline_lette(self, parsed):
        """Il workbook non ha sharedStrings.xml: senza supporto inline tutto sarebbe vuoto."""
        progetti_rows = parsed.sheet(Section.PROGETTI).rows
        assert progetti_rows[0].project.startswith("IM26018-3313-BMED-ARCH")
        assert progetti_rows[0].collaborator == "Venturi Simone"
        assert progetti_rows[0].note == "SAL"

    def test_date_e_intervallo_della_settimana(self, parsed):
        periods = {row.period for row in parsed.rows}
        assert min(periods) == dt.date(2026, 10, 30)
        assert max(periods) == dt.date(2026, 11, 5)

    def test_valori_grezzi_non_arrotondati_a_due_decimali(self, parsed):
        """La colonna è formattata a 2 decimali: 0,38 a schermo vale 0,375."""
        wallet = parsed.sheet(Section.WALLET).rows
        assert Decimal("0.3750") in {row.days for row in wallet}
        assert Decimal("0.0625") in {row.days for row in wallet}
        assert Decimal("0.1875") in {row.days for row in wallet}
        assert all(row.days.as_tuple().exponent == -4 for row in parsed.rows)

    def test_sovrapposizione_progetti_wallet_conservata(self, parsed):
        """Tutte le righe Wallet ricompaiono in Progetti: entrambe vanno importate."""
        chiave = lambda row: (row.collaborator, row.period, row.days, row.note)  # noqa: E731
        progetti_keys = {chiave(r) for r in parsed.sheet(Section.PROGETTI).rows}
        wallet_keys = [chiave(r) for r in parsed.sheet(Section.WALLET).rows]
        assert all(k in progetti_keys for k in wallet_keys)
        assert len(wallet_keys) == 7

    def test_destinazioni_organico_allargato(self, parsed):
        titoli = {row.subproject for row in parsed.sheet(Section.ORGANICO).rows}
        assert "Assestment dismissione FileNet" in titoli
        assert "[EA] Standardizzazione dei BBA" in titoli
        assert len(titoli) == 7
