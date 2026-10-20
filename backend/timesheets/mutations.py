"""Unica via d'uscita dal divieto di modifica sui consuntivi.

Il trigger `timesheets_append_only` (migrazione 0002) blocca UPDATE e DELETE sulla tabella
dei consuntivi. Annullare un import, però, deve poter rimuovere le righe che quell'import ha
creato: per quel solo caso si apre una finestra esplicita, valida per la transazione in
corso e registrata nel log applicativo.

Regola d'uso: nient'altro che il rollback di un `ImportBatch` deve entrare qui. Ogni
correzione di merito si fa con uno storno (`TimesheetEntry.build_reversal`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection, transaction

logger = logging.getLogger(__name__)

SESSION_FLAG = "supplier_ledger.allow_ledger_mutation"


@contextmanager
def allow_ledger_mutation(reason: str) -> Iterator[None]:
    """Consente UPDATE e DELETE sui consuntivi per la transazione corrente.

    `SET LOCAL` limita l'effetto alla transazione, quindi la finestra si chiude da sé al
    commit o al rollback, anche in caso di errore.
    """
    if not reason or not reason.strip():
        raise ValueError("Serve una motivazione per modificare i consuntivi.")
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError(
            "allow_ledger_mutation richiede una transazione: usalo dentro transaction.atomic()."
        )

    logger.warning(
        "Finestra di modifica dei consuntivi aperta", extra={"motivazione": reason.strip()}
    )
    with connection.cursor() as cursor:
        cursor.execute(f"SET LOCAL \"{SESSION_FLAG}\" = 'on'")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL \"{SESSION_FLAG}\" = 'off'")
        logger.warning(
            "Finestra di modifica dei consuntivi chiusa", extra={"motivazione": reason.strip()}
        )
