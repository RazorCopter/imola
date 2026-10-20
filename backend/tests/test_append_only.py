"""I consuntivi non si modificano e non si cancellano, per nessuna strada.

Il modello protegge le istanze; il trigger PostgreSQL protegge la tabella. Qui si prova
che cadono anche le tre vie che aggirano il modello: `queryset.update()`,
`queryset.delete()` e l'SQL scritto a mano.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from tests.factories import ProjectFactory, TimesheetEntryFactory
from timesheets.models import TimesheetEntry, TimesheetSource
from timesheets.mutations import allow_ledger_mutation

pytestmark = pytest.mark.django_db
APPEND_ONLY_MESSAGE = "append-only"


@pytest.fixture
def entry() -> TimesheetEntry:
    return TimesheetEntryFactory(
        project=ProjectFactory(code="IM26-APPEND-ONLY", budget_days=Decimal("10.0000")),
        days=Decimal("3.5000"),
        period=date(2026, 10, 1),
    )


class TestProtezioneDelModello:
    """Prima linea: le istanze."""

    def test_save_su_riga_esistente_rifiutato(self, entry):
        entry.days = Decimal("99.0000")
        with pytest.raises(ValidationError, match=APPEND_ONLY_MESSAGE):
            entry.save()

    def test_delete_di_istanza_rifiutato(self, entry):
        with pytest.raises(ValidationError):
            entry.delete()

    def test_la_riga_resta_intatta(self, entry):
        with pytest.raises(ValidationError):
            entry.save()
        entry.refresh_from_db()
        assert entry.days == Decimal("3.5000")


class TestProtezioneDelDatabase:
    """Seconda linea: il trigger. Queste sono le vie che aggiravano il modello."""

    def test_queryset_update_bloccato_dal_trigger(self, entry):
        with pytest.raises(DatabaseError, match=APPEND_ONLY_MESSAGE), transaction.atomic():
            TimesheetEntry.objects.filter(pk=entry.pk).update(days=Decimal("99.0000"))

    def test_queryset_delete_bloccato_dal_trigger(self, entry):
        with pytest.raises(DatabaseError, match=APPEND_ONLY_MESSAGE), transaction.atomic():
            TimesheetEntry.objects.filter(pk=entry.pk).delete()

    def test_update_sql_diretta_bloccata(self, entry):
        with pytest.raises(DatabaseError, match=APPEND_ONLY_MESSAGE), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE timesheets_timesheetentry SET days = 99 WHERE id = %s", [str(entry.pk)]
                )

    def test_delete_sql_diretta_bloccata(self, entry):
        with pytest.raises(DatabaseError, match=APPEND_ONLY_MESSAGE), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM timesheets_timesheetentry WHERE id = %s", [str(entry.pk)]
                )

    def test_truncate_e_delete_massiva_bloccati(self, entry):
        """Anche una DELETE senza WHERE: il trigger è FOR EACH ROW."""
        with pytest.raises(DatabaseError, match=APPEND_ONLY_MESSAGE), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM timesheets_timesheetentry")

    def test_la_riga_sopravvive_al_tentativo(self, entry):
        with pytest.raises(DatabaseError), transaction.atomic():
            TimesheetEntry.objects.filter(pk=entry.pk).delete()
        assert TimesheetEntry.objects.filter(pk=entry.pk).exists()
        entry.refresh_from_db()
        assert entry.days == Decimal("3.5000")

    def test_l_inserimento_resta_consentito(self, entry):
        """Append-only vuol dire che si aggiunge: solo UPDATE e DELETE sono negate."""
        reversal = entry.build_reversal("Correzione da estratto PPM.")
        reversal.save()
        assert TimesheetEntry.objects.count() == 2
        assert reversal.days == Decimal("-3.5000")
        assert reversal.source == TimesheetSource.STORNO

    def test_il_messaggio_indica_lo_storno(self, entry):
        with pytest.raises(DatabaseError) as excinfo, transaction.atomic():
            TimesheetEntry.objects.filter(pk=entry.pk).update(days=Decimal("1.0000"))
        assert "storno" in str(excinfo.value)


class TestFinestraPerIlRollback:
    """La sola eccezione: annullare un import deve poter rimuovere le proprie righe."""

    def test_la_finestra_consente_la_cancellazione(self, entry):
        with transaction.atomic():
            with allow_ledger_mutation("rollback del batch di import di prova"):
                TimesheetEntry.objects.filter(pk=entry.pk).delete()
        assert not TimesheetEntry.objects.filter(pk=entry.pk).exists()

    def test_la_finestra_si_chiude_subito_dopo(self, entry):
        with transaction.atomic():
            with allow_ledger_mutation("rollback di prova"):
                pass
            with pytest.raises(DatabaseError, match=APPEND_ONLY_MESSAGE):
                TimesheetEntry.objects.filter(pk=entry.pk).update(days=Decimal("1.0000"))

    def test_la_finestra_si_chiude_anche_in_caso_di_errore(self, entry):
        with pytest.raises(RuntimeError), transaction.atomic():
            with allow_ledger_mutation("rollback che va male"):
                raise RuntimeError("errore durante il rollback")
        with pytest.raises(DatabaseError, match=APPEND_ONLY_MESSAGE), transaction.atomic():
            TimesheetEntry.objects.filter(pk=entry.pk).delete()

    def test_serve_una_motivazione(self, entry):
        with transaction.atomic(), pytest.raises(ValueError, match="motivazione"):
            with allow_ledger_mutation("   "):
                pass

    @pytest.mark.django_db(transaction=True)
    def test_serve_una_transazione(self):
        """Fuori da una transazione SET LOCAL non avrebbe effetto: meglio fallire subito.

        Il marcatore transaction=True disattiva la transazione con cui pytest-django
        avvolge i test, altrimenti ci si troverebbe sempre dentro un blocco atomico.
        """
        with pytest.raises(RuntimeError, match="transazione"):
            with allow_ledger_mutation("tentativo fuori transazione"):
                pass
