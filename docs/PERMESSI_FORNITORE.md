# Operatività del ruolo Fornitore

Il ruolo `fornitore` può creare nuovi progetti, inserire consuntivi e rettificare
o annullare consuntivi manuali di qualsiasi utente su Progetti e Organico Allargato.
Può creare, modificare ed eliminare attività dell'Organico Allargato e gestire
le voci del wallet, comprese nuove attività e allocazioni. Può rettificare i
consumi del wallet tramite il totale progressivo, con erogazione FIFO invariata.

Il nuovo permesso `timesheets.edit` autorizza le rettifiche dei consuntivi senza
attribuire il più ampio `accounting.adjust`. Restano validi i controlli sui
residui, sulle allocazioni chiuse, sulle versioni e sulle dipendenze dei dati.
Le rettifiche continuano a produrre storni e nuove registrazioni, conservando
lo storico. Gli endpoint dei consuntivi diretti restano dedicati alle voci manuali;
non viene introdotta la modifica delle registrazioni provenienti da import.

Il ruolo non riceve permessi di amministrazione, gestione utenti, modifica
privilegi, reset del database o applicazione degli import. La creazione di progetti
non concede la modifica indiscriminata dell'anagrafica dei progetti esistenti.
Amministrazione è nascosta dal menu e dalla palette di navigazione; l'accesso
diretto alla pagina reindirizza alla Dashboard. Le API amministrative continuano
a verificare i privilegi lato server.

La migrazione `core.0006_supplier_operational_permissions` abilita sul ruolo
esistente i permessi `projects.create`, `timesheets.create`, `timesheets.edit`,
`wallet.edit` e `canone.manage`, aggiornando anche eventuali vecchi override
negativi per questi soli permessi. Non modifica gli override degli altri ruoli
o degli altri permessi. I permessi configurati restano persistenti in caso di
rollback della migrazione.

Applicare le migrazioni durante il deploy e aggiornare la sessione (ricaricando
l'applicazione o accedendo nuovamente) per aggiornare i controlli dell'interfaccia.
Non sono state eseguite migrazioni sul database locale.

Sono stati aggiornati gli scenari di regressione per i nuovi permessi, senza
eseguire test, build o screenshot, come richiesto dall'utente.
