"""API dell'importazione: completare un'associazione dalla pagina e poi confermare.

Il caso coperto è quello che si incontra ogni settimana: il codice scritto nell'Excel non
coincide con il codice censito (il nome applicativo lo contiene, con il titolo davanti). Il
confronto del backend è esatto per scelta (docs/importazione_plan.md §3), quindi la riga
resta da associare: la pagina deve poter proporre le destinazioni, salvare la scelta e
rigenerare l'anteprima senza farsi ricaricare il file.
"""

from __future__ import annotations

import datetime as dt
from io import BytesIO

import pytest
from openpyxl import Workbook

from core import roles
from imports.models import ImportMapping, ImportRowStatus, MappingKind, OperationalImportRow
from tests.factories import ProjectFactory, UserFactory
from tests.test_roles_object_permissions import make_client_for_role
from timesheets.models import TimesheetEntry

pytestmark = pytest.mark.django_db

CODICE_EXCEL = "144659 - RdA dinamico (TE200 asset sede e rete)"
CODICE_CENSITO = "ASSET SEDE E RETE (144659 - RdA dinamico (TE200 asset sede e rete))"


@pytest.fixture(autouse=True)
def media_in_tmp(settings, tmp_path):
    """La preview allega il file al batch: non va a finire nella media reale."""
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


def estratto(*righe: list) -> BytesIO:
    book = Workbook()
    book.remove(book.active)
    sheet = book.create_sheet("Progetti")
    for riga in (["Progetto", "Collaboratore", "Data", "Note", "gg tot"], *righe):
        sheet.append(riga)
    stream = BytesIO()
    book.save(stream)
    stream.seek(0)
    stream.name = "estratto.xlsx"
    return stream


def test_associazione_dalla_pagina_rende_la_riga_importabile_e_resta_per_dopo():
    client, _ = make_client_for_role(roles.ADMIN)
    progetto = ProjectFactory(code=CODICE_CENSITO, budget_days="14.0000")
    UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")

    anteprima = client.post(
        "/api/v1/imports/operational/preview",
        {"file": estratto([CODICE_EXCEL, "Venturi Simone", dt.date(2026, 11, 3), "Lavoro", 0.25])},
        format="multipart",
    )
    assert anteprima.status_code == 201, anteprima.data
    batch = anteprima.json()
    assert batch["confermabile"] is False
    assert batch["righe"][0]["stato"] == ImportRowStatus.DA_ASSOCIARE

    gruppi = batch["report"]["da_associare"]
    assert len(gruppi) == 1
    gruppo = gruppi[0]
    assert gruppo["tipo"] == MappingKind.PROGETTO
    assert gruppo["valore"] == CODICE_EXCEL
    assert gruppo["righe"] == ["Progetti!2"]
    # Il progetto censito contiene il codice dell'Excel: va proposto per primo e
    # preselezionato, pur restando una scelta dell'utente.
    assert gruppo["candidati"][0]["id"] == str(progetto.pk)
    assert gruppo["suggerito"] == str(progetto.pk)

    associato = client.patch(
        f"/api/v1/imports/operational/{batch['id']}/mappings",
        {
            "associazioni": [
                {
                    "tipo": gruppo["tipo"],
                    "valore": gruppo["valore"],
                    "destinazione": gruppo["suggerito"],
                    "anno": gruppo["anno"],
                    "semestre": gruppo["semestre"],
                }
            ]
        },
        format="json",
    )
    assert associato.status_code == 200, associato.data
    ricalcolato = associato.json()
    assert ricalcolato["report"]["da_associare"] == []
    assert ricalcolato["righe"][0]["stato"] == ImportRowStatus.PRONTA
    assert ricalcolato["righe"][0]["destinazione_risolta"]
    assert ricalcolato["confermabile"] is True
    # L'anteprima è stata rifatta sullo stesso file: nessuna riga duplicata in staging.
    assert OperationalImportRow.objects.count() == 1

    conferma = client.post(
        f"/api/v1/imports/operational/{batch['id']}/apply",
        {"impronta": ricalcolato["impronta"]},
        format="json",
    )
    assert conferma.status_code == 200, conferma.data
    movimento = TimesheetEntry.objects.get()
    assert movimento.project_id == progetto.pk

    # L'associazione è nel registro: la settimana dopo lo stesso codice non torna a chiedere.
    mapping = ImportMapping.objects.get(kind=MappingKind.PROGETTO)
    assert mapping.project_id == progetto.pk
    assert mapping.context_year is None and mapping.context_semester == ""

    seconda = client.post(
        "/api/v1/imports/operational/preview",
        {"file": estratto([CODICE_EXCEL, "Venturi Simone", dt.date(2026, 11, 10), "Altro", 0.25])},
        format="multipart",
    )
    assert seconda.status_code == 201, seconda.data
    assert seconda.json()["report"]["da_associare"] == []
    assert seconda.json()["righe"][0]["stato"] == ImportRowStatus.PRONTA


def test_associazione_rifiutata_se_la_destinazione_non_esiste():
    client, _ = make_client_for_role(roles.ADMIN)
    ProjectFactory(code=CODICE_CENSITO)
    UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")

    batch = client.post(
        "/api/v1/imports/operational/preview",
        {"file": estratto([CODICE_EXCEL, "Venturi Simone", dt.date(2026, 11, 3), "Lavoro", 0.25])},
        format="multipart",
    ).json()

    risposta = client.patch(
        f"/api/v1/imports/operational/{batch['id']}/mappings",
        {
            "associazioni": [
                {
                    "tipo": MappingKind.PROGETTO.value,
                    "valore": CODICE_EXCEL,
                    "destinazione": "00000000-0000-0000-0000-000000000000",
                }
            ]
        },
        format="json",
    )
    assert risposta.status_code == 404
    assert not ImportMapping.objects.exists()


def test_capienza_sfondata_disabilita_la_conferma_e_la_spiega():
    """Righe tutte `PRONTA` ma budget insufficiente: la conferma non deve sembrare viva.

    Le capienze sono cumulative sulla destinazione, non una proprietà della riga: senza
    guardare gli errori del batch la vista dichiarava `confermabile: true` e l'apply
    rispondeva 409 sotto lock. Dal punto di vista di chi clicca era un pulsante che non
    faceva nulla.
    """
    client, _ = make_client_for_role(roles.ADMIN)
    progetto = ProjectFactory(code="IM26294-CAPIENZA", budget_days="1.0000")
    UserFactory(username="s.venturi", first_name="Simone", last_name="Venturi")

    risposta = client.post(
        "/api/v1/imports/operational/preview",
        {
            "file": estratto(
                [progetto.code, "Venturi Simone", dt.date(2026, 11, 3), "Lavoro", 1.0],
                [progetto.code, "Venturi Simone", dt.date(2026, 11, 4), "Lavoro", 0.5],
            )
        },
        format="multipart",
    )
    assert risposta.status_code == 201, risposta.data
    batch = risposta.json()

    # Le righe sono risolte: il problema non è l'associazione.
    assert [r["stato"] for r in batch["righe"]] == [ImportRowStatus.PRONTA] * 2
    assert batch["report"]["da_associare"] == []
    assert batch["confermabile"] is False
    assert any("Capienza superata" in m for m in batch["errori_bloccanti"])

    # E se qualcuno ci prova comunque, l'apply rifiuta senza scrivere nulla.
    conferma = client.post(
        f"/api/v1/imports/operational/{batch['id']}/apply",
        {"impronta": batch["impronta"]},
        format="json",
    )
    assert conferma.status_code == 409
    assert "oltre il residuo" in conferma.json()["detail"]
    assert not TimesheetEntry.objects.exists()
