"""I consuntivi sono append-only anche a livello di database.

La protezione in `TimesheetEntry.save()` e `.delete()` copre solo le istanze: un
`queryset.update()`, un `queryset.delete()` o una `UPDATE` scritta a mano in psql la
aggirerebbero senza accorgersene. Trattandosi di dati contabili, il divieto vive qui, in un
trigger, dove nessuna strada lo scavalca.

Resta una sola via d'uscita, esplicita e tracciata: il parametro di sessione
`supplier_ledger.allow_ledger_mutation`, che il rollback di un batch di import imposta
dentro la propria transazione (vedi `timesheets.mutations.allow_ledger_mutation` e la voce
D-14 in docs/DECISIONI_APERTE.md). Serve perche annullare un import deve poter rimuovere le
righe che quell-import ha creato.
"""

from django.db import migrations

CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION timesheets_append_only() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
    IF current_setting('supplier_ledger.allow_ledger_mutation', true) = 'on' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;
    RAISE EXCEPTION
        'I consuntivi sono append-only: per correggere, registrare uno storno (operazione % negata su %).',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = '42501',
              HINT = 'Usa TimesheetEntry.build_reversal(); il rollback di un import imposta supplier_ledger.allow_ledger_mutation.';
END;
$function$;
"""

CREATE_TRIGGERS = """
CREATE TRIGGER timesheet_entry_no_update
    BEFORE UPDATE ON timesheets_timesheetentry
    FOR EACH ROW EXECUTE FUNCTION timesheets_append_only();

CREATE TRIGGER timesheet_entry_no_delete
    BEFORE DELETE ON timesheets_timesheetentry
    FOR EACH ROW EXECUTE FUNCTION timesheets_append_only();
"""

DROP = """
DROP TRIGGER IF EXISTS timesheet_entry_no_update ON timesheets_timesheetentry;
DROP TRIGGER IF EXISTS timesheet_entry_no_delete ON timesheets_timesheetentry;
DROP FUNCTION IF EXISTS timesheets_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("timesheets", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=CREATE_FUNCTION, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(sql=CREATE_TRIGGERS, reverse_sql=DROP),
    ]
