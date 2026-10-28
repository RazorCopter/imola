# Visual review reale - Supplier Ledger

28 ottobre 2026. Sono stati osservati i 121 screenshot originali attraverso le tavole in review-sheets, con apertura degli originali per Dashboard, Wallet, dialog, errori e correzioni critiche. Le tavole sono composizioni degli screenshot reali, non immagini sintetiche. Le versioni dopo correzione sono state rigenerate e riesaminate. Le ultime catture del cambio canone portano errore e nuova attivita entro il viewport.

## Problemi osservati e corretti

| Problema osservato | Correzione | Evidenza finale |
|---|---|---|
| Accento dark poco leggibile nella navigazione e nei link | Token accent piu chiaro | nove viste dark; audit axe |
| Badge ok/warn/danger poco leggibili in light | Token light piu scuri | progetti/reconciliation light; axe |
| Pulsanti verdi con testo bianco insufficienti | Fondo emerald-700 | Wallet e preview import |
| Link nella KPI residui troppo compresso fra i testi | Hint e azione in colonna | dashboard-dark-1440x900.png |
| Legenda del grafico Organico scura | Testo legenda foreground, marcatori conservati | organico-dark-1024x768.png |
| Ctrl K su due righe a 1024 | shrink-0 e whitespace-nowrap | nove viste 1024 |
| Cornice doppia nella ricerca Progetti | Input interno senza bordo | progetti-dark-1440x900.png |
| Titoli e motivazioni in Revisione troncati | A capo nella cella | revisione-light-1440x900.png |
| Pulsante Bloccato nel dialog progetto poco contrastato in light | Token warn | progetti-edit-light-1024.png |
| Attivita Organico centrate nel controllo condiviso | Colonna con items-start/justify-start | organico-dark-bottom.png |
| Aggregazione vuota mostrata come sole intestazioni | Messaggio esplicito nella tabella | costi-aggregazione-vuota.png |
| Dettaglio Wallet rendeva difficile conservare la tabella larga | Drawer con scroll e ritorno alla riga | wallet-drawer.png e 1024-bottom |
| Rischio di mostrare il precedente canone mentre cambia selezione | Loading e stato errore per il dettaglio corrente | organico-detail-error.png / cambio-selezione |

## Esame delle nove pagine

- Dashboard: KPI con una priorita chiara; valori e hint distinti; grafici contenuti, legenda leggibile; dati testuali e fatturazioni raggiungibili scorrendo. A 1024 i grafici sono su una colonna.
- Progetti: titolo e codice insieme; numeri allineati; budget zero e residuo negativo distinguibili. La tabella resta un contenitore con scroll; il test a 24 righe porta l'ultima azione nel viewport.
- Wallet: KPI ordinati, filtro vicino alla lista; il drawer lascia distinguibile il contesto. Note e pulsanti finali sono raggiungibili con scroll interno nei due temi.
- Organico: capacita, canoni e dettaglio separati; attivita cliccabili con titolo e metadati su righe distinte; Panoramica e Consuntivi, form contestuale e conferma eliminazione leggibili.
- Costi: grafico orizzontale e ranking testuale; date e Top N separati; tabelle per progetto, fornitore, fonte e mese popolate con fixture, piu caso di singola aggregazione vuota.
- Riconciliazione: stato snapshot prima delle KPI; ricerca/esito sopra la tabella; esiti espressi anche con testo, numeri leggibili e dati assenti dichiarati.
- Anomalie: rilievo, gravita, stato e azioni leggibili; scadenza deroga vicina alla voce; errore non elimina i dati del form.
- Revisione: motivazione visibile nella riga; conferma contestuale con stato e data; campi e azioni vanno a capo entro la cella.
- Admin: tab secondari coerenti, import in fasi, storico tabellare, backup/restore visibili. Utenti, referenti, ruoli e configurazione esaminati anche a 1024 nei due temi. Reset osservato senza inviarlo.

Il confronto con le precedenti catture Terra di Dashboard e Wallet conferma la direzione visiva; il confronto riguarda layout e leggibilita, poiche i dataset di prova differiscono. Nessuna pretesa di confronto numerico o golden pixel test.

## Registro delle catture esaminate

Il manifest separato contiene dimensioni e SHA256. Tutti i file seguenti sono originali Chromium.

| Originale | Esame | Stato |
|---|---|---|
| [admin-Configurazione-dark-1024.png](<admin-Configurazione-dark-1024.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [admin-Configurazione-light-1024.png](<admin-Configurazione-light-1024.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [admin-import-result.png](<admin-import-result.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [admin-preview-enabled.png](<admin-preview-enabled.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [admin-Referenti-dark-1024.png](<admin-Referenti-dark-1024.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [admin-Referenti-light-1024.png](<admin-Referenti-light-1024.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [admin-reset-dark.png](<admin-reset-dark.png>) | Dialog: larghezza, altezza, etichette, focus e possibilita di scroll | DONE |
| [admin-reset-light.png](<admin-reset-light.png>) | Dialog: larghezza, altezza, etichette, focus e possibilita di scroll | DONE |
| [admin-Ruoli e privilegi-dark-1024.png](<admin-Ruoli e privilegi-dark-1024.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [admin-Ruoli e privilegi-light-1024.png](<admin-Ruoli e privilegi-light-1024.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [admin-utente-dialog.png](<admin-utente-dialog.png>) | Dialog: larghezza, altezza, etichette, focus e possibilita di scroll | DONE |
| [admin-Utenti-dark-1024.png](<admin-Utenti-dark-1024.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [admin-Utenti-light-1024.png](<admin-Utenti-light-1024.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [amministrazione-dark-1024x768.png](<amministrazione-dark-1024x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [amministrazione-dark-1366x768.png](<amministrazione-dark-1366x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [amministrazione-dark-1440x900.png](<amministrazione-dark-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [amministrazione-dark-1600x900.png](<amministrazione-dark-1600x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [amministrazione-dark-1920x1080.png](<amministrazione-dark-1920x1080.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [amministrazione-dark-bottom.png](<amministrazione-dark-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [amministrazione-empty.png](<amministrazione-empty.png>) | Assenza di righe comunicata nel contesto, senza sostituzioni di valori | DONE |
| [amministrazione-error.png](<amministrazione-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [amministrazione-light-1440x900.png](<amministrazione-light-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [amministrazione-light-bottom.png](<amministrazione-light-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [anomalie-dark-1024x768.png](<anomalie-dark-1024x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [anomalie-dark-1366x768.png](<anomalie-dark-1366x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [anomalie-dark-1440x900.png](<anomalie-dark-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [anomalie-dark-1600x900.png](<anomalie-dark-1600x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [anomalie-dark-1920x1080.png](<anomalie-dark-1920x1080.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [anomalie-deroga.png](<anomalie-deroga.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [anomalie-empty.png](<anomalie-empty.png>) | Assenza di righe comunicata nel contesto, senza sostituzioni di valori | DONE |
| [anomalie-error.png](<anomalie-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [anomalie-light-1440x900.png](<anomalie-light-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [anomalie-mutation-error.png](<anomalie-mutation-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [costi-aggregazione-vuota.png](<costi-aggregazione-vuota.png>) | Assenza di righe comunicata nel contesto, senza sostituzioni di valori | DONE |
| [costi-dark-1024x768.png](<costi-dark-1024x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [costi-dark-1366x768.png](<costi-dark-1366x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [costi-dark-1440x900.png](<costi-dark-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [costi-dark-1600x900.png](<costi-dark-1600x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [costi-dark-1920x1080.png](<costi-dark-1920x1080.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [costi-dark-bottom.png](<costi-dark-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [costi-empty.png](<costi-empty.png>) | Assenza di righe comunicata nel contesto, senza sostituzioni di valori | DONE |
| [costi-error.png](<costi-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [costi-light-1440x900.png](<costi-light-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [costi-light-bottom.png](<costi-light-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [costi-top5.png](<costi-top5.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [dashboard-dark-1024x768.png](<dashboard-dark-1024x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [dashboard-dark-1366x768.png](<dashboard-dark-1366x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [dashboard-dark-1440x900.png](<dashboard-dark-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [dashboard-dark-1600x900.png](<dashboard-dark-1600x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [dashboard-dark-1920x1080.png](<dashboard-dark-1920x1080.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [dashboard-dark-bottom.png](<dashboard-dark-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [dashboard-empty.png](<dashboard-empty.png>) | Assenza di righe comunicata nel contesto, senza sostituzioni di valori | DONE |
| [dashboard-error.png](<dashboard-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [dashboard-light-1440x900.png](<dashboard-light-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [dashboard-light-bottom.png](<dashboard-light-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [dashboard-source-error.png](<dashboard-source-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [organico-cambio-selezione.png](<organico-cambio-selezione.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [organico-conferma-eliminazione.png](<organico-conferma-eliminazione.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [organico-consuntivo.png](<organico-consuntivo.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [organico-dark-1024x768.png](<organico-dark-1024x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [organico-dark-1366x768.png](<organico-dark-1366x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [organico-dark-1440x900.png](<organico-dark-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [organico-dark-1600x900.png](<organico-dark-1600x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [organico-dark-1920x1080.png](<organico-dark-1920x1080.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [organico-dark-bottom.png](<organico-dark-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [organico-detail-error.png](<organico-detail-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [organico-empty.png](<organico-empty.png>) | Assenza di righe comunicata nel contesto, senza sostituzioni di valori | DONE |
| [organico-entire-page.png](<organico-entire-page.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [organico-error.png](<organico-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [organico-light-1440x900.png](<organico-light-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [organico-light-bottom.png](<organico-light-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [progetti-consuntivi.png](<progetti-consuntivi.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [progetti-dark-1024x768.png](<progetti-dark-1024x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [progetti-dark-1366x768.png](<progetti-dark-1366x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [progetti-dark-1440x900.png](<progetti-dark-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [progetti-dark-1600x900.png](<progetti-dark-1600x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [progetti-dark-1920x1080.png](<progetti-dark-1920x1080.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [progetti-edit-dark-1024.png](<progetti-edit-dark-1024.png>) | Dialog: larghezza, altezza, etichette, focus e possibilita di scroll | DONE |
| [progetti-edit-light-1024.png](<progetti-edit-light-1024.png>) | Dialog: larghezza, altezza, etichette, focus e possibilita di scroll | DONE |
| [progetti-empty.png](<progetti-empty.png>) | Assenza di righe comunicata nel contesto, senza sostituzioni di valori | DONE |
| [progetti-error.png](<progetti-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [progetti-ledger-error.png](<progetti-ledger-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [progetti-light-1440x900.png](<progetti-light-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [progetti-modifica-dialog.png](<progetti-modifica-dialog.png>) | Dialog: larghezza, altezza, etichette, focus e possibilita di scroll | DONE |
| [progetti-stress-scroll.png](<progetti-stress-scroll.png>) | Tabella scorsa a destra/in basso; ultima azione raggiungibile; nessun overflow documento | DONE |
| [progetti-validazione.png](<progetti-validazione.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [revisione-dark-1024x768.png](<revisione-dark-1024x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [revisione-dark-1366x768.png](<revisione-dark-1366x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [revisione-dark-1440x900.png](<revisione-dark-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [revisione-dark-1600x900.png](<revisione-dark-1600x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [revisione-dark-1920x1080.png](<revisione-dark-1920x1080.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [revisione-empty.png](<revisione-empty.png>) | Assenza di righe comunicata nel contesto, senza sostituzioni di valori | DONE |
| [revisione-error.png](<revisione-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [revisione-form.png](<revisione-form.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [revisione-light-1440x900.png](<revisione-light-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [ricerca-globale.png](<ricerca-globale.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [riconciliazione-dark-1024x768.png](<riconciliazione-dark-1024x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [riconciliazione-dark-1366x768.png](<riconciliazione-dark-1366x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [riconciliazione-dark-1440x900.png](<riconciliazione-dark-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [riconciliazione-dark-1600x900.png](<riconciliazione-dark-1600x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [riconciliazione-dark-1920x1080.png](<riconciliazione-dark-1920x1080.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [riconciliazione-empty.png](<riconciliazione-empty.png>) | Assenza di righe comunicata nel contesto, senza sostituzioni di valori | DONE |
| [riconciliazione-error.png](<riconciliazione-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [riconciliazione-light-1440x900.png](<riconciliazione-light-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [wallet-dark-1024x768.png](<wallet-dark-1024x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [wallet-dark-1366x768.png](<wallet-dark-1366x768.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [wallet-dark-1440x900.png](<wallet-dark-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [wallet-dark-1600x900.png](<wallet-dark-1600x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [wallet-dark-1920x1080.png](<wallet-dark-1920x1080.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [wallet-dark-bottom.png](<wallet-dark-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [wallet-drawer-dark-1024-bottom.png](<wallet-drawer-dark-1024-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [wallet-drawer-dark-1024.png](<wallet-drawer-dark-1024.png>) | Drawer: contesto, fonti FIFO, campi e scroll interno | DONE |
| [wallet-drawer-light-1024-bottom.png](<wallet-drawer-light-1024-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [wallet-drawer-light-1024.png](<wallet-drawer-light-1024.png>) | Drawer: contesto, fonti FIFO, campi e scroll interno | DONE |
| [wallet-drawer.png](<wallet-drawer.png>) | Drawer: contesto, fonti FIFO, campi e scroll interno | DONE |
| [wallet-empty.png](<wallet-empty.png>) | Assenza di righe comunicata nel contesto, senza sostituzioni di valori | DONE |
| [wallet-error.png](<wallet-error.png>) | Errore esplicito e differenziato dallo stato vuoto | DONE |
| [wallet-light-1440x900.png](<wallet-light-1440x900.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
| [wallet-light-bottom.png](<wallet-light-bottom.png>) | Parte inferiore dopo scroll; contenuti e azioni finali raggiungibili | DONE |
| [wallet-nuovo-dialog.png](<wallet-nuovo-dialog.png>) | Dialog: larghezza, altezza, etichette, focus e possibilita di scroll | DONE |
| [wallet-reopened.png](<wallet-reopened.png>) | Gerarchia, tipografia, spazi, allineamenti, contrasto e limiti del viewport | DONE |
