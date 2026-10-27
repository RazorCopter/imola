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
        IF batch_kind NOT IN ('SEED_JSON', 'WORKBOOK_JSON') THEN
            RAISE EXCEPTION
                'project_closed_requires_date: progetto CHIUSO senza data ammesso solo per seed'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$function$;
"""

RESTORE_FUNCTION = """
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


class Migration(migrations.Migration):
    dependencies = [("projects", "0003_historicalproject_released_to_wallet_days_and_more")]

    operations = [migrations.RunSQL(sql=CREATE_FUNCTION, reverse_sql=RESTORE_FUNCTION)]
