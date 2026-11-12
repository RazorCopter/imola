"""Test su database dell'importazione dell'estratto operativo.

Coprono ciò che il test del parser non può vedere: risoluzione delle destinazioni,
censimento dei collaboratori, capienze cumulative, atomicità dell'applicazione e
sovrapposizione con i movimenti già registrati.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth.models import User
from openpyxl import Workbook

from canone.models import CanoneSubactivity
from core import roles
from directory.models import Person
from importers.operational_batch import ApplyError, apply_batch, content_fingerprint, preview
from importers.operational_excel import Level, parse_workbook
from importers.operational_mapping import Resolver
from imports.models import (
    ImportMapping,
    ImportRowSection,
    ImportRowStatus,
    ImportStatus,
    MappingKind,
    OperationalImportRow,
)
from tests.factories import (
    CanoneFactory,
    CanoneSubactivityFactory,
    ProjectFactory,
    TimesheetEntryFactory,
    UserFactory,
    WalletActivityFactory,
    WalletAllocationFactory,
    WalletYearFactory,
)
from timesheets.models import TimesheetEntry, TimesheetSource

pytestmark = pytest.mark.django_db

PROGETTI_HEADERS = ["Progetto", "Collaboratore", "Data", "Note", "gg tot"]
WALLET_HEADERS = ["Progetto", "Sottoprogetto", "Collaboratore", "Data", "Note", "gg tot"]
ORGANICO_HEADERS = ["Sotto progetto", "Collaboratore", "Data", "Note", "gg tot"]


@pytest.fixture(autouse=True)
def media_in_tmp(settings, tmp_path):
    """Il batch allega il file: non va a finire nella media reale del progetto."""
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def operatore(db):
    return UserFactory(username="admin.importazioni")


def workbook_bytes(sheets: dict[str, list[list]]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for title, rows in sheets.items():
        sheet = book.create_sheet(title)
        for row in rows:
            sheet.append(row)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def progetti_workbook(*rows: list) -> bytes:
    return workbook_bytes({"Progetti": [PROGETTI_HEADERS, *rows]})


def run_preview(payload: bytes, operatore: User):
    return preview(upload=payload, filename="estratto.xlsx", user=operatore)


def messages(result, level: Level | None = None) -> list[str]:
    problems = (
        result.problems if level is None else [p for p in result.problems if p.level is level]
    )
    return [p.message for p in problems]


# ------------------------------------------------------------------ destinazioni


def test_progetto_risolto_per_codice_esatto(operatore):
    project = ProjectFactory(code="IM26294-3313-BMED-ARCH-SELEZIONE-SOFTWARE-RISK")
    autore = UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")

    result = run_preview(
        progetti_workbook(
            [project.code, "Venturi Simone", dt.date(2026, 11, 3), "Redazione paragrafo", 0.25]
        ),
        operatore,
    )

    assert result.errors == []
    row = OperationalImportRow.objects.get()
    assert row.project_id == project.pk
    assert row.author_id == autore.pk
    assert row.status == ImportRowStatus.PRONTA
    assert row.days == Decimal("0.2500")
    assert row.period == dt.date(2026, 11, 3)


def test_progetto_sconosciuto_va_in_riconciliazione(operatore):
    UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")

    result = run_preview(
        progetti_workbook(
            ["IM-INESISTENTE", "Venturi Simone", dt.date(2026, 11, 3), "Lavoro", 0.25]
        ),
        operatore,
    )

    assert any("non trovato fra i codici censiti" in m for m in messages(result, Level.ERROR))
    row = OperationalImportRow.objects.get()
    assert row.status == ImportRowStatus.DA_ASSOCIARE
    assert row.project_id is None
    assert result.candidates  # la pagina deve poter proporre le destinazioni


def test_associazione_confermata_aggancia_senza_match_esatto(operatore):
    """Una volta associato in Riconciliazione, il valore Excel non torna a chiedere."""
    project = ProjectFactory(code="IM26294-3313-BMED-ARCH-SELEZIONE-SOFTWARE-RISK")
    UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")
    ImportMapping.objects.create(
        kind=MappingKind.PROGETTO,
        external_value="Selezione software risk",
        external_key="selezionesoftwarerisk",
        project=project,
    )

    result = run_preview(
        progetti_workbook(
            ["Selezione software risk", "Venturi Simone", dt.date(2026, 11, 3), "Lavoro", 0.25]
        ),
        operatore,
    )

    assert result.errors == []
    assert OperationalImportRow.objects.get().project_id == project.pk


def test_sottoprogetto_wallet_con_prefisso_dell_anno(operatore):
    """Nell'estratto reale il valore è `Wallet <anno> <titolo dell'attività>`."""
    year = WalletYearFactory(year=2026)
    project = ProjectFactory(code="IM26254-3313-BMED-ARCH-SOLUTION-DESIGN-GESTIONE-DOPPIO-CR")
    activity = WalletActivityFactory(code="ATT-OSB14", title="Migrazione OSB14 POC")
    allocation = WalletAllocationFactory(
        wallet_year=year, activity=activity, allocated_days=Decimal("10.0000")
    )
    UserFactory(username="p.nicoletti", first_name="Pietro", last_name="Nicoletti")

    result = run_preview(
        workbook_bytes(
            {
                "Wallet": [
                    WALLET_HEADERS,
                    [
                        project.code,
                        "Wallet 2026 Migrazione OSB14 POC",
                        "Nicoletti Pietro",
                        dt.date(2026, 11, 2),
                        "rilascio artifactory",
                        1.0,
                    ],
                ]
            }
        ),
        operatore,
    )

    assert result.errors == []
    row = OperationalImportRow.objects.get()
    assert row.wallet_allocation_id == allocation.pk
    assert row.section == ImportRowSection.WALLET


def test_canone_dedotto_dal_semestre_della_data(operatore):
    """Lo stesso titolo esiste in due semestri: la data decide, senza chiedere."""
    primo = CanoneFactory(
        semester="2026-S1", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 6, 30)
    )
    secondo = CanoneFactory(
        semester="2026-S2", start_date=dt.date(2026, 7, 1), end_date=dt.date(2026, 12, 31)
    )
    titolo = "Assestment dismissione FileNet"
    CanoneSubactivityFactory(canone=primo, title=titolo, reserved_days=Decimal("5.0000"))
    attesa = CanoneSubactivityFactory(canone=secondo, title=titolo, reserved_days=Decimal("5.0000"))
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")

    result = run_preview(
        workbook_bytes(
            {
                "Organico_Allargato": [
                    ORGANICO_HEADERS,
                    [titolo, "Ravagli Andrea", dt.date(2026, 11, 2), "Revisione", 0.375],
                ]
            }
        ),
        operatore,
    )

    assert result.errors == []
    assert OperationalImportRow.objects.get().canone_subactivity_id == attesa.pk


def test_finestra_temporale_dell_attivita_e_un_errore(operatore):
    """Vincolo che solo l'organico allargato ha: la data deve stare nel periodo."""
    canone = CanoneFactory(
        semester="2026-S2", start_date=dt.date(2026, 7, 1), end_date=dt.date(2026, 12, 31)
    )
    CanoneSubactivityFactory(
        canone=canone,
        title="Attività con finestra",
        reserved_days=Decimal("5.0000"),
        start_date=dt.date(2026, 11, 10),
        end_date=dt.date(2026, 12, 31),
    )
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")

    result = run_preview(
        workbook_bytes(
            {
                "Organico_Allargato": [
                    ORGANICO_HEADERS,
                    [
                        "Attività con finestra",
                        "Ravagli Andrea",
                        dt.date(2026, 11, 2),
                        "Troppo presto",
                        0.5,
                    ],
                ]
            }
        ),
        operatore,
    )

    errori = messages(result, Level.ERROR)
    assert any("fuori dal periodo" in m for m in errori)
    assert any("10/11/2026" in m for m in errori)


# ----------------------------------------------------------------- collaboratori


def test_collaboratore_riconosciuto_con_nome_invertito(operatore):
    ProjectFactory(code="IM-A")
    autore = UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")

    result = run_preview(
        progetti_workbook(["IM-A", "Ravagli Andrea", dt.date(2026, 11, 3), "SAL", 0.25]),
        operatore,
    )

    assert result.errors == []
    assert OperationalImportRow.objects.get().author_id == autore.pk


def test_collaboratore_assente_censito_con_avviso(operatore):
    """Censito come Nome Cognome, utilizzabile come autore ma non come accesso."""
    ProjectFactory(code="IM-A")

    result = run_preview(
        progetti_workbook(["IM-A", "Nicoletti Pietro", dt.date(2026, 11, 3), "Build", 0.375]),
        operatore,
    )

    assert result.errors == []
    assert any("censito come 'Pietro Nicoletti'" in m for m in messages(result, Level.WARNING))

    creato = User.objects.get(first_name="Pietro", last_name="Nicoletti")
    assert creato.is_active is True, "disattivato spariria da assignable_authors()"
    assert creato.has_usable_password() is False
    assert [g.name for g in creato.groups.all()] == [roles.SUPPLIER]

    persona = Person.objects.get(full_name="Pietro Nicoletti")
    assert persona.needs_review is True
    assert persona.organization.code == "IMOLA"

    row = OperationalImportRow.objects.get()
    assert row.status == ImportRowStatus.PRONTA
    assert row.author_id == creato.pk


def test_collaboratore_censito_una_volta_sola(operatore):
    ProjectFactory(code="IM-A")
    payload = progetti_workbook(
        ["IM-A", "Nicoletti Pietro", dt.date(2026, 11, 3), "Build", 0.375],
        ["IM-A", "Nicoletti Pietro", dt.date(2026, 11, 4), "Rilascio", 0.5],
    )

    run_preview(payload, operatore)

    assert User.objects.filter(first_name="Pietro", last_name="Nicoletti").count() == 1


def test_collaboratore_ambiguo_richiede_una_scelta(operatore):
    ProjectFactory(code="IM-A")
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")
    UserFactory(username="a.ravagli.2", first_name="Andrea", last_name="Ravagli")

    result = run_preview(
        progetti_workbook(["IM-A", "Ravagli Andrea", dt.date(2026, 11, 3), "SAL", 0.25]),
        operatore,
    )

    assert any("corrisponde a più utenti" in m for m in messages(result, Level.ERROR))
    assert OperationalImportRow.objects.get().status == ImportRowStatus.DA_ASSOCIARE


def test_non_attribuisce_mai_all_operatore(operatore):
    ProjectFactory(code="IM-A")

    run_preview(
        progetti_workbook(["IM-A", "Nicoletti Pietro", dt.date(2026, 11, 3), "Build", 0.375]),
        operatore,
    )

    assert OperationalImportRow.objects.get().author_id != operatore.pk


# --------------------------------------------------------------------- capienze


def test_capienza_cumulativa_sul_batch_non_riga_per_riga(operatore):
    """Due righe che passerebbero singolarmente ma insieme sfondano il budget."""
    ProjectFactory(code="IM-BUDGET", budget_days=Decimal("10.0000"))
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")

    result = run_preview(
        progetti_workbook(
            ["IM-BUDGET", "Ravagli Andrea", dt.date(2026, 11, 3), "Primo blocco", 6.0],
            ["IM-BUDGET", "Ravagli Andrea", dt.date(2026, 11, 4), "Secondo blocco", 6.0],
        ),
        operatore,
    )

    errori = messages(result, Level.ERROR)
    assert any("il batch porta 12.0000 gg" in m for m in errori)
    assert result.can_apply is False


def test_avviso_quando_il_residuo_scende_sotto_mezza_giornata(operatore):
    ProjectFactory(code="IM-STRETTO", budget_days=Decimal("1.0000"))
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")

    result = run_preview(
        progetti_workbook(["IM-STRETTO", "Ravagli Andrea", dt.date(2026, 11, 3), "Quasi", 0.9]),
        operatore,
    )

    assert result.errors == []
    assert any("resta 0.1000 gg di residuo" in m for m in messages(result, Level.WARNING))


def test_capienza_dell_allocazione_wallet(operatore):
    year = WalletYearFactory(year=2026)
    activity = WalletActivityFactory(code="ATT-OSB14", title="Migrazione OSB14 POC")
    allocation = WalletAllocationFactory(
        wallet_year=year, activity=activity, allocated_days=Decimal("1.0000")
    )
    TimesheetEntryFactory(
        wallet_allocation=allocation,
        project=None,
        days=Decimal("0.8000"),
        period=dt.date(2026, 10, 1),
    )
    project = ProjectFactory(code="IM-W")
    UserFactory(username="p.nicoletti", first_name="Pietro", last_name="Nicoletti")

    result = run_preview(
        workbook_bytes(
            {
                "Wallet": [
                    WALLET_HEADERS,
                    [
                        project.code,
                        "Migrazione OSB14 POC",
                        "Nicoletti Pietro",
                        dt.date(2026, 11, 2),
                        "Sforamento",
                        0.5,
                    ],
                ]
            }
        ),
        operatore,
    )

    assert any("Allocazione Migrazione OSB14 POC" in m for m in messages(result, Level.ERROR))


# ----------------------------------------------------------------------- preview


def test_preview_non_crea_consuntivi(operatore):
    ProjectFactory(code="IM-A")
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")

    result = run_preview(
        progetti_workbook(["IM-A", "Ravagli Andrea", dt.date(2026, 11, 3), "SAL", 0.25]),
        operatore,
    )

    assert TimesheetEntry.objects.count() == 0
    assert result.batch.status == ImportStatus.DRY_RUN
    assert OperationalImportRow.objects.count() == 1


def test_preview_registra_i_problemi_con_la_cella(operatore):
    ProjectFactory(code="IM-A")
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")

    result = run_preview(
        progetti_workbook(["IM-A", "Ravagli Andrea", dt.date(2026, 11, 3), "SAL", None]),
        operatore,
    )

    from imports.models import ImportIssueLevel

    issue = result.batch.issues.get(level=ImportIssueLevel.ERROR)
    assert issue.key == "E2"
    assert issue.entity == "Progetti"
    assert "Giornate mancanti" in issue.message


def test_report_contiene_i_riepiloghi_per_sezione(operatore):
    ProjectFactory(code="IM-A")
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")

    result = run_preview(
        progetti_workbook(["IM-A", "Ravagli Andrea", dt.date(2026, 11, 3), "SAL", 0.25]),
        operatore,
    )

    result.batch.refresh_from_db()
    sezioni = {s["sezione"]: s for s in result.batch.report["sezioni"]}
    assert sezioni["PROGETTI"]["righe_importabili"] == 1
    assert sezioni["PROGETTI"]["giornate"] == "0.2500"
    assert result.batch.report["impronta_contenuto"]


def test_impronta_indipendente_dall_ordine_delle_righe():
    prima = parse_workbook(
        BytesIO(
            workbook_bytes(
                {
                    "Progetti": [
                        PROGETTI_HEADERS,
                        ["IM-A", "Ravagli Andrea", dt.date(2026, 11, 3), "Uno", 0.25],
                        ["IM-A", "Ravagli Andrea", dt.date(2026, 11, 4), "Due", 0.5],
                    ]
                }
            )
        )
    )
    dopo = parse_workbook(
        BytesIO(
            workbook_bytes(
                {
                    "Progetti": [
                        PROGETTI_HEADERS,
                        ["IM-A", "Ravagli Andrea", dt.date(2026, 11, 4), "Due", 0.5],
                        ["IM-A", "Ravagli Andrea", dt.date(2026, 11, 3), "Uno", 0.25],
                    ]
                }
            )
        )
    )
    assert content_fingerprint(prima) == content_fingerprint(dopo)


# ---------------------------------------------------------------- sovrapposizioni


def test_riga_gia_presente_e_un_avviso_non_uno_scarto(operatore):
    """§9.4: la sovrapposizione si mostra, non si deduplica in silenzio."""
    project = ProjectFactory(code="IM-A", budget_days=Decimal("10.0000"))
    autore = UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")
    TimesheetEntryFactory(
        project=project,
        period=dt.date(2026, 11, 3),
        days=Decimal("0.2500"),
        note="Revisione dei BBA",
        created_by=autore,
    )

    result = run_preview(
        progetti_workbook(
            ["IM-A", "Ravagli Andrea", dt.date(2026, 11, 3), "Revisione dei BBA", 0.25]
        ),
        operatore,
    )

    assert result.errors == []
    assert any("già presente" in m for m in messages(result, Level.WARNING))
    assert OperationalImportRow.objects.get().status == ImportRowStatus.PRONTA


def test_sovrapposizione_con_autore_diverso_lo_dichiara(operatore):
    project = ProjectFactory(code="IM-A", budget_days=Decimal("10.0000"))
    altro = UserFactory(username="p.nicoletti", first_name="Pietro", last_name="Nicoletti")
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")
    TimesheetEntryFactory(
        project=project,
        period=dt.date(2026, 11, 4),
        days=Decimal("0.1875"),
        note="Partecipazione al SAL",
        created_by=altro,
    )

    result = run_preview(
        progetti_workbook(
            ["IM-A", "Ravagli Andrea", dt.date(2026, 11, 4), "Partecipazione al SAL", 0.1875]
        ),
        operatore,
    )

    avvisi = messages(result, Level.WARNING)
    assert any("autore sbagliato" in m for m in avvisi)


def test_data_diversa_non_e_una_sovrapposizione(operatore):
    """Stessa descrizione in un altro giorno è lavoro nuovo, non un duplicato."""
    project = ProjectFactory(code="IM-A", budget_days=Decimal("10.0000"))
    autore = UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")
    TimesheetEntryFactory(
        project=project,
        period=dt.date(2026, 10, 25),
        days=Decimal("0.2500"),
        note="Redazione paragrafo 4.1.2.1 Clonazione Campagne",
        created_by=autore,
    )

    result = run_preview(
        progetti_workbook(
            [
                "IM-A",
                "Venturi Simone",
                dt.date(2026, 11, 3),
                "Redazione paragrafo 4.1.2.1 Clonazione Campagne",
                0.25,
            ]
        ),
        operatore,
    )

    assert not any("già presente" in m for m in messages(result, Level.WARNING))
    assert result.can_apply is True


# ------------------------------------------------------------------------- apply


def test_apply_crea_i_consuntivi_tracciabili(operatore):
    project = ProjectFactory(code="IM-A", budget_days=Decimal("10.0000"))
    autore = UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")

    result = run_preview(
        progetti_workbook(
            ["IM-A", "Venturi Simone", dt.date(2026, 11, 3), "Redazione paragrafo", 0.25]
        ),
        operatore,
    )
    batch = apply_batch(batch_id=result.batch.pk, user=operatore)

    entry = TimesheetEntry.objects.get()
    assert entry.project_id == project.pk
    assert entry.period == dt.date(2026, 11, 3), "la data è quella del giorno, non del mese"
    assert entry.days == Decimal("0.2500")
    assert entry.source == TimesheetSource.EXCEL_IMPORT
    assert entry.created_by_id == autore.pk
    assert entry.import_batch_id == batch.pk

    row = OperationalImportRow.objects.get()
    assert row.entry_id == entry.pk, "ogni movimento risale alla riga Excel"
    assert batch.status == ImportStatus.APPLIED
    assert batch.applied_by_id == operatore.pk


def test_apply_somma_ai_consuntivi_preesistenti(operatore):
    project = ProjectFactory(code="IM-A", budget_days=Decimal("10.0000"))
    UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")
    TimesheetEntryFactory(project=project, days=Decimal("2.0000"), period=dt.date(2026, 10, 1))

    result = run_preview(
        progetti_workbook(["IM-A", "Venturi Simone", dt.date(2026, 11, 3), "Nuovo", 0.25]),
        operatore,
    )
    apply_batch(batch_id=result.batch.pk, user=operatore)

    assert TimesheetEntry.objects.count() == 2
    totale = sum(e.days for e in TimesheetEntry.objects.all())
    assert totale == Decimal("2.2500")


def test_apply_e_atomica(operatore):
    """Una riga non pronta blocca tutto: nessun aggiornamento parziale."""
    ProjectFactory(code="IM-A", budget_days=Decimal("10.0000"))
    UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")

    result = run_preview(
        progetti_workbook(
            ["IM-A", "Venturi Simone", dt.date(2026, 11, 3), "Buona", 0.25],
            ["IM-INESISTENTE", "Venturi Simone", dt.date(2026, 11, 4), "Senza destinazione", 0.5],
        ),
        operatore,
    )

    with pytest.raises(ApplyError, match="non sono pronte"):
        apply_batch(batch_id=result.batch.pk, user=operatore)

    assert TimesheetEntry.objects.count() == 0
    result.batch.refresh_from_db()
    assert result.batch.status == ImportStatus.DRY_RUN


def test_apply_due_volte_e_bloccato(operatore):
    ProjectFactory(code="IM-A", budget_days=Decimal("10.0000"))
    UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")

    result = run_preview(
        progetti_workbook(["IM-A", "Venturi Simone", dt.date(2026, 11, 3), "Una volta", 0.25]),
        operatore,
    )
    apply_batch(batch_id=result.batch.pk, user=operatore)

    with pytest.raises(ApplyError, match="già stato applicato"):
        apply_batch(batch_id=result.batch.pk, user=operatore)

    assert TimesheetEntry.objects.count() == 1


def test_stesso_file_ricaricato_non_si_applica_due_volte(operatore):
    ProjectFactory(code="IM-A", budget_days=Decimal("10.0000"))
    UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")
    payload = progetti_workbook(["IM-A", "Venturi Simone", dt.date(2026, 11, 3), "Una volta", 0.25])

    primo = run_preview(payload, operatore)
    apply_batch(batch_id=primo.batch.pk, user=operatore)

    secondo = run_preview(payload, operatore)
    with pytest.raises(ApplyError, match="già stato applicato"):
        apply_batch(batch_id=secondo.batch.pk, user=operatore)

    assert TimesheetEntry.objects.count() == 1


def test_apply_sincronizza_il_wallet(operatore):
    year = WalletYearFactory(year=2026)
    activity = WalletActivityFactory(code="ATT-OSB14", title="Migrazione OSB14 POC")
    allocation = WalletAllocationFactory(
        wallet_year=year, activity=activity, allocated_days=Decimal("10.0000")
    )
    project = ProjectFactory(code="IM-W")
    UserFactory(username="p.nicoletti", first_name="Pietro", last_name="Nicoletti")

    result = run_preview(
        workbook_bytes(
            {
                "Wallet": [
                    WALLET_HEADERS,
                    [
                        project.code,
                        "Migrazione OSB14 POC",
                        "Nicoletti Pietro",
                        dt.date(2026, 11, 2),
                        "rilascio",
                        1.0,
                    ],
                ]
            }
        ),
        operatore,
    )
    apply_batch(batch_id=result.batch.pk, user=operatore)

    entry = TimesheetEntry.objects.get()
    assert entry.wallet_allocation_id == allocation.pk
    allocation.refresh_from_db()
    consumate = sum(e.days for e in allocation.timesheet_entries.all())
    assert consumate == Decimal("1.0000")


# ------------------------------------------------------- indipendenza dei fogli


def test_le_due_sezioni_generano_due_movimenti(operatore):
    """§3.5: la stessa voce in Progetti e in Wallet va importata due volte."""
    project = ProjectFactory(code="IM26254", budget_days=Decimal("10.0000"))
    year = WalletYearFactory(year=2026)
    activity = WalletActivityFactory(code="ATT-OSB14", title="Migrazione OSB14 POC")
    WalletAllocationFactory(wallet_year=year, activity=activity, allocated_days=Decimal("10.0000"))
    UserFactory(username="p.nicoletti", first_name="Pietro", last_name="Nicoletti")

    result = run_preview(
        workbook_bytes(
            {
                "Progetti": [
                    PROGETTI_HEADERS,
                    [project.code, "Nicoletti Pietro", dt.date(2026, 11, 2), "Build", 0.375],
                ],
                "Wallet": [
                    WALLET_HEADERS,
                    [
                        project.code,
                        "Migrazione OSB14 POC",
                        "Nicoletti Pietro",
                        dt.date(2026, 11, 2),
                        "Build",
                        0.375,
                    ],
                ],
            }
        ),
        operatore,
    )
    apply_batch(batch_id=result.batch.pk, user=operatore)

    assert TimesheetEntry.objects.count() == 2
    assert TimesheetEntry.objects.filter(project__isnull=False).count() == 1
    assert TimesheetEntry.objects.filter(wallet_allocation__isnull=False).count() == 1


def test_resolver_non_interroga_il_database_per_ogni_riga(operatore, django_assert_max_num_queries):
    """Gli indici si caricano una volta: 45 righe non fanno 45 query per destinazione."""
    ProjectFactory(code="IM-A")
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")
    rows = [
        ["IM-A", "Ravagli Andrea", dt.date(2026, 11, 3), f"Riga {n}", 0.0625] for n in range(20)
    ]
    parsed = parse_workbook(BytesIO(progetti_workbook(*rows)))
    resolver = Resolver()

    with django_assert_max_num_queries(12):
        resolutions = resolver.resolve_all(parsed.rows)

    assert len(resolutions) == 20
    assert all(r.project is not None for r in resolutions)


def test_sotto_attivita_senza_capienza_e_un_errore(operatore):
    canone = CanoneFactory(
        semester="2026-S2", start_date=dt.date(2026, 7, 1), end_date=dt.date(2026, 12, 31)
    )
    CanoneSubactivityFactory(
        canone=canone, title="Attività satura", reserved_days=Decimal("0.1000")
    )
    UserFactory(username="a.ravagli", first_name="Andrea", last_name="Ravagli")

    result = run_preview(
        workbook_bytes(
            {
                "Organico_Allargato": [
                    ORGANICO_HEADERS,
                    ["Attività satura", "Ravagli Andrea", dt.date(2026, 11, 2), "Oltre", 0.5],
                ]
            }
        ),
        operatore,
    )

    assert any("Attività Attività satura" in m for m in messages(result, Level.ERROR))
    assert CanoneSubactivity.objects.get().timesheet_entries.count() == 0


def test_nome_preso_dall_anagrafica_quando_la_persona_esiste(operatore):
    """Tre token: l'ordine non è deducibile, ma l'anagrafica lo sa già.

    Senza questo, "Vignati Pier Mauro" creerebbe un utente con il nome nell'ordine
    dell'Excel, divergente dalla persona "Pier Mauro Vignati" già censita.
    """
    from tests.factories import PersonFactory, SupplierOrganizationFactory

    ProjectFactory(code="IM-A")
    PersonFactory(full_name="Pier Mauro Vignati", organization=SupplierOrganizationFactory())

    run_preview(
        progetti_workbook(["IM-A", "Vignati Pier Mauro", dt.date(2026, 11, 4), "SAL EA", 0.0625]),
        operatore,
    )

    creato = User.objects.get(username="pier.vignati")
    assert creato.get_full_name() == "Pier Mauro Vignati"
    assert (
        Person.objects.filter(full_name="Pier Mauro Vignati").count() == 1
    ), "non deve nascere una seconda persona per lo stesso collaboratore"
