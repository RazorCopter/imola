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

- ridurre l'allocazione al consumato;
- chiudere un'allocazione;
- consultare lo storico modifiche dell'allocazione tramite le API di audit.

![Wallet demo](screenshots/demo-wallet.png)

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
