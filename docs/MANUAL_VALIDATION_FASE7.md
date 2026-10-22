# Validazione manuale Fase 7

## Prerequisiti

1. Avviare lo stack Docker locale con `make up`.
2. Caricare esclusivamente i dati demo sintetici e deterministici con `make demo`.
3. Usare il frontend diretto all'indirizzo `http://localhost:5173` oppure l'ingresso nginx `http://localhost:8080`. Il backend è esposto su `http://localhost:8000` (API sotto `/api/v1`).
4. Per cambiare ruolo, disconnettersi e accedere con l'utente indicato. Tutti gli utenti demo usano la password `Demo-Local-2026!`.

> Stato: checklist predisposta ma **non eseguita**. Le caselle devono essere selezionate dall'utente durante la verifica personale da browser.

## Checklist

- [ ] Login admin
  - **URL/percorso GUI:** `http://localhost:5173/` oppure `http://localhost:8080/`, schermata di login.
  - **Utente demo da utilizzare:** `demo_admin` / `Demo-Local-2026!`.
  - **Azione da effettuare:** inserire le credenziali e confermare l'accesso.
  - **Risultato atteso:** autenticazione riuscita, apertura della dashboard e navigazione applicativa disponibile con ruolo amministratore.

- [ ] Login responsabile BMED
  - **URL/percorso GUI:** `http://localhost:5173/` oppure `http://localhost:8080/`, schermata di login.
  - **Utente demo da utilizzare:** `demo_responsabile` / `Demo-Local-2026!`.
  - **Azione da effettuare:** inserire le credenziali e confermare l'accesso.
  - **Risultato atteso:** autenticazione riuscita, apertura della dashboard e interfaccia coerente con il ruolo responsabile BMED.

- [ ] Login referente
  - **URL/percorso GUI:** `http://localhost:5173/` oppure `http://localhost:8080/`, schermata di login.
  - **Utente demo da utilizzare:** `demo_referente` / `Demo-Local-2026!`.
  - **Azione da effettuare:** inserire le credenziali e confermare l'accesso.
  - **Risultato atteso:** autenticazione riuscita, apertura della dashboard e interfaccia coerente con il ruolo referente BMED.

- [ ] Login fornitore
  - **URL/percorso GUI:** `http://localhost:5173/` oppure `http://localhost:8080/`, schermata di login.
  - **Utente demo da utilizzare:** `demo_fornitore` / `Demo-Local-2026!`.
  - **Azione da effettuare:** inserire le credenziali e confermare l'accesso.
  - **Risultato atteso:** autenticazione riuscita, apertura della dashboard e interfaccia coerente con il ruolo fornitore.

- [ ] Dashboard
  - **URL/percorso GUI:** `http://localhost:5173/` oppure `http://localhost:8080/`.
  - **Utente demo da utilizzare:** `demo_responsabile` / `Demo-Local-2026!`.
  - **Azione da effettuare:** aprire la pagina iniziale dopo il login e controllare indicatori, riepiloghi, avvisi e collegamenti operativi.
  - **Risultato atteso:** la dashboard si carica senza errori, mostra dati demo e consente di raggiungere le aree progetti, wallet e revisione.

- [ ] Progetti (lista)
  - **URL/percorso GUI:** `http://localhost:5173/progetti` oppure `http://localhost:8080/progetti`.
  - **Utente demo da utilizzare:** `demo_referente` / `Demo-Local-2026!`.
  - **Azione da effettuare:** aprire la lista, verificare la presenza di progetti demo, applicare almeno un filtro disponibile e selezionare una riga.
  - **Risultato atteso:** la lista visualizza i progetti demo, i filtri aggiornano coerentemente i risultati e la selezione apre il dettaglio del progetto.

- [ ] Dettaglio progetto
  - **URL/percorso GUI:** dalla lista `/progetti`, selezionare un progetto; percorso risultante `/progetti/<UUID>`.
  - **Utente demo da utilizzare:** `demo_responsabile` / `Demo-Local-2026!`.
  - **Azione da effettuare:** controllare intestazione, stati e metriche; aprire le schede Panoramica, Consuntivi, Wallet, Milestone, Residuo, Anomalie e Documenti.
  - **Risultato atteso:** il progetto selezionato viene mostrato con codice, titolo, stati e valori demo coerenti; tutte le schede sono raggiungibili senza errori.

- [ ] Wallet
  - **URL/percorso GUI:** `http://localhost:5173/wallet` oppure `http://localhost:8080/wallet`.
  - **Utente demo da utilizzare:** `demo_responsabile` / `Demo-Local-2026!`.
  - **Azione da effettuare:** aprire il wallet, controllare riepilogo annuale, flussi/allocazioni e valori di allocato, consumato e residuo.
  - **Risultato atteso:** la pagina mostra i dati demo del wallet senza errori e i valori di consumo e residuo risultano leggibili e coerenti tra riepilogo e righe.

- [ ] Anomalie
  - **URL/percorso GUI:** `http://localhost:5173/anomalie` oppure `http://localhost:8080/anomalie`.
  - **Utente demo da utilizzare:** `demo_referente` / `Demo-Local-2026!`.
  - **Azione da effettuare:** aprire la coda anomalie, controllare le righe demo e provare i filtri disponibili per stato, severità o ambito.
  - **Risultato atteso:** le anomalie demo sono visibili, i filtri restringono correttamente l'elenco e non compaiono errori di caricamento o autorizzazione inattesi.

- [ ] Revisione
  - **URL/percorso GUI:** `http://localhost:5173/revisione` oppure `http://localhost:8080/revisione`.
  - **Utente demo da utilizzare:** `demo_responsabile` / `Demo-Local-2026!`.
  - **Azione da effettuare:** aprire la coda di revisione, ispezionare gli elementi da verificare e i dettagli disponibili senza confermare dati non esaminati.
  - **Risultato atteso:** la coda mostra gli elementi demo da verificare con motivazione e azioni coerenti con i permessi del responsabile.

- [ ] Riconciliazione
  - **URL/percorso GUI:** `http://localhost:5173/riconciliazione` oppure `http://localhost:8080/riconciliazione`.
  - **Utente demo da utilizzare:** `demo_responsabile` / `Demo-Local-2026!`.
  - **Azione da effettuare:** aprire la pagina, esaminare il confronto tra dati gestionali e snapshot PPM e utilizzare gli eventuali filtri presenti.
  - **Risultato atteso:** il prospetto di riconciliazione carica i dati demo, evidenzia scostamenti e stati in modo comprensibile e non presenta errori.

- [ ] Audit — storico modifiche nel dettaglio progetto
  - **URL/percorso GUI:** dalla lista `/progetti`, aprire un progetto e selezionare la scheda **Storico modifiche** nel percorso `/progetti/<UUID>`.
  - **Utente demo da utilizzare:** `demo_admin` / `Demo-Local-2026!`.
  - **Azione da effettuare:** aprire la scheda Storico modifiche e controllare data, tipo evento, utente e campi modificati delle righe disponibili.
  - **Risultato atteso:** lo storico viene caricato dal dettaglio progetto, è ordinato e leggibile e attribuisce gli eventi disponibili senza esporre errori applicativi.

## Esito

La verifica manuale resta intenzionalmente **pendente**: questo documento definisce soltanto i passi da eseguire e non certifica alcun esito.