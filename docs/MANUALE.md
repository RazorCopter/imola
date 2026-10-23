# Manuale operativo — Supplier Ledger

> Le immagini e gli esempi di questo manuale usano esclusivamente una fixture dimostrativa sintetica. Non contengono codici progetto, persone o valori provenienti da ambienti reali.

## Accesso e dashboard

1. Aprire l'applicazione nel browser.
2. Inserire le credenziali fornite dall'amministratore.
3. La dashboard mostra indicatori sintetici per progetti, wallet, canone e riconciliazione.

![Dashboard demo](screenshots/demo-dashboard.png)

## Import PPM

1. Accedere come amministratore, responsabile oppure fornitore.
2. Selezionare un file `.xlsx` o `.pdf` entro il limite configurato.
3. Il primo passaggio è sempre un **dry-run**: controllare data estrazione, quadratura e righe non riconosciute.
4. Solo amministratore e responsabile possono applicare il batch.
5. Il fornitore può caricare file, ma il risultato resta in dry-run.

![Import PPM demo](screenshots/demo-import-ppm.png)

## Amministrazione utenti e privilegi

La pagina **Amministrazione**, disponibile agli account autorizzati, è divisa in **Import ed export**, **Utenti** e **Ruoli e privilegi**.

Nel tab **Utenti** è possibile creare un account con password iniziale, aggiornare anagrafica/email/ruolo/stato, impostare una nuova password e disattivare l'account. La cancellazione definitiva viene rifiutata quando l'account ha riferimenti applicativi: in quel caso usare **Disattiva**. Non è possibile disattivare o eliminare il proprio account né lasciare il sistema senza un amministratore attivo.

Nel tab **Ruoli e privilegi** le checkbox Admin e le capability riservate sono bloccate. Per gli altri privilegi modificare la matrice e usare il pulsante **Salva** del ruolo: la variazione vale dalla richiesta successiva.

## Coda di revisione

La pagina **Coda di revisione** mostra i progetti con dati incompleti o da confermare. Per ciascun progetto:

1. selezionare `ATTIVO` o `CHIUSO`;
2. inserire la data proposta;
3. usare **Conferma revisione** e poi **Salva**.

![Revisione demo](screenshots/demo-review-queue.png)

## Progetti

Nel dettaglio progetto sono disponibili:

- panoramica contabile;
- stati indipendenti;
- aggiornamento data fine prevista;
- tab **Storico modifiche** con data, utente e campi cambiati.

![Dettaglio progetto demo](screenshots/demo-project-history.png)

## Wallet

La pagina wallet mostra il flusso progetto origine → attività. Gli utenti autorizzati possono:

- modificare l'allocazione tramite il pulsante arancione **EDIT** (giornate allocate, assegnatario architetto, note);
- rettificare i consuntivi collegati in modalità append-only (storno automatico dell'entry originale ed eventuale nuova registrazione a conguaglio);
- ridurre l'allocazione al consumato;
- chiudere un'allocazione;
- consultare lo storico modifiche dell'allocazione tramite le API di audit.

![Wallet demo](screenshots/demo-wallet.png)

## Zona Pericolosa: Funzione "ELIMINA DB"

In fondo alla pagina di **Amministrazione** gli utenti autorizzati (con capability `data.reset`) visualizzano la sezione **Zona Pericolosa — Reset Completo DB**.

1. Cliccare sul pulsante rosso **ELIMINA DB**.
2. Il sistema apre un dialog di controverifica che mostra il conteggio esatto dei record operativi presenti per categoria (progetti, consuntivi, wallet, organico allargato, importazioni, anomalie).
3. Viene generato un token di sicurezza crittografico effimero e monouso a scadenza.
4. Per confermare, l'amministratore deve digitare esattamente la parola chiave **ELIMINA** nel campo di testo dedicato.
5. Al clic su **Conferma eliminazione DB**, la transazione rimuove tutte le entità operative tramite procedura certificata, preservando integralmente utenti, password, ruoli, permessi configurati e impostazioni di sistema.

## Anomalie

Nell'inbox è possibile:

- prendere in carico un'anomalia;
- risolverla con motivazione;
- accettarla in deroga indicando motivazione e scadenza.

![Anomalie demo](screenshots/demo-anomalies.png)

## Export

Sono disponibili:

- Excel multi-foglio: Progetti, Wallet, Canone, Riconciliazione, Anomalie;
- CSV per singola entità;
- JSON schema `1.0.0`.

## Backup e restore

```bash
python manage.py backup --output-dir /srv/backups
python manage.py restore /srv/backups/db-YYYYMMDD-HHMMSS.sql.gz --database supplier_ledger_restore_test --confirm
```

Il restore deve essere eseguito su database vuoto o dedicato. Il comando non cancella automaticamente il database target.
