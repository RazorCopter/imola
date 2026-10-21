"""Vincolo D-14 a livello database: lo stato CHIUSO senza data è consentito SOLO per SEED_JSON.

I progetti con timesheet_status = 'CHIUSO' privi di actual_closure_date sono ammessi
esclusivamente se associati a un batch di tipo SEED_JSON (D-03 / D-14). Se associati a
batch PPM o creati manualmente senza data, l'inserimento/aggiornamento viene rifiutato.
"""

from django.db import migrations

CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION check_project_closed_requires_seed_batch()
RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    batch_kind varchar(20);
BEGIN
    IF NEW.timesheet_status = 'CHIUSO' AND NEW.actual_closure_date IS NULL THEN
        IF NEW.import_batch_id IS NULL THEN
            RAISE EXCEPTION
                'project_closed_requires_date: data di chiusura obbligatoria per progetto CHIUSO'
                USING ERRCODE = '23514';
        END IF;

        SELECT kind INTO batch_kind FROM imports_importbatch WHERE id = NEW.import_batch_id;
        IF batch_kind IS DISTINCT FROM 'SEED_JSON' THEN
            RAISE EXCEPTION
                'project_closed_requires_date: progetto CHIUSO senza data ammesso SOLO per batch SEED_JSON (D-14)'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$function$;
"""

CREATE_TRIGGER = """
DROP TRIGGER IF EXISTS trg_project_closed_requires_seed_batch ON projects_project;
CREATE TRIGGER trg_project_closed_requires_seed_batch
    BEFORE INSERT OR UPDATE ON projects_project
    FOR EACH ROW EXECUTE FUNCTION check_project_closed_requires_seed_batch();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS trg_project_closed_requires_seed_batch ON projects_project;
DROP FUNCTION IF EXISTS check_project_closed_requires_seed_batch();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0001_initial"),
        ("imports", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_FUNCTION + CREATE_TRIGGER,
            reverse_sql=DROP_TRIGGER,
        ),
    ]
