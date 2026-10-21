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

from imports.models import ImportKind

logger = logging.getLogger(__name__)

SESSION_FLAG = "supplier_ledger.allow_ledger_mutation"


@contextmanager
def allow_ledger_mutation(reason: str, batch: object | None = None) -> Iterator[None]:
    """Consente UPDATE e DELETE sui consuntivi per la transazione corrente.

    `SET LOCAL` limita l'effetto alla transazione, quindi la finestra si chiude da sé al
    commit o al rollback, anche in caso di errore.

    D-14: la mutazione diretta del ledger è consentita esclusivamente se il batch associato
    è di tipo SEED_JSON. Per batch PPM o altri tipi futuri, la cancellazione e la mutazione
    diretta del ledger sono rifiutate (i batch PPM di Fase 5 si annullano esclusivamente con
    storni contabili append-only).
    """
    if not reason or not reason.strip():
        raise ValueError("Serve una motivazione per modificare i consuntivi.")
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError(
            "allow_ledger_mutation richiede una transazione: usalo dentro transaction.atomic()."
        )

    if batch is not None:
        batch_kind = getattr(batch, "kind", batch)
        if batch_kind != ImportKind.SEED_JSON:
            raise PermissionError(
                f"allow_ledger_mutation vietata per il batch di tipo '{batch_kind}': "
                "solo i batch SEED_JSON ammettono mutazioni dirette del ledger. "
                "I batch PPM e altri tipi richiedono storni contabili append-only (D-14)."
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
