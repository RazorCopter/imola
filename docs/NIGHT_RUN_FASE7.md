# NIGHT RUN — FASE 7 — ESECUZIONE AUTONOMA NON SUPERVISIONATA

> Specifica completa e vincolante. L'ultima riga del file è `FINE SPECIFICA`.
> Se non la trovi, il file è troncato: scrivilo nel log e lavora solo sulla sezione 1.

## 0. MODALITÀ DI ESECUZIONE

Lavorerai **tutta la notte senza supervisione**. Nessuno risponderà alle tue domande.

- **NON fare domande all'utente** e non attendere conferme. Davanti a una scelta: prendi
  l'opzione più conservativa e reversibile, registrala in `docs/NIGHT_RUN_LOG.md` sezione
  "DECISIONI PRESE IN AUTONOMIA" e prosegui.
- **NON fermarti** a fine blocco: passa al blocco successivo dell'elenco (sezione 4).
- Ti fermi solo quando: (a) tutti i blocchi sono chiusi o marcati BLOCCATO, oppure
  (b) si verifica una condizione della sezione 7.
- Se il contesto si esaurisce o la sessione riparte: **rileggi questo file e
  `docs/NIGHT_RUN_LOG.md`** e riprendi dal primo blocco non chiuso. Il log è la tua memoria.
- Quando deleghi a sotto-agenti, passa il **percorso di questo file** e il numero di
  sezione, non copiare il testo (i messaggi lunghi vengono troncati).

Fonti di verità, in quest'ordine:
1. questo file;
2. `docs/FUNCTIONAL_GAP_ANALYSIS.md` (numerazione FG ufficiale — non usare numerazioni
   prese da report di audit, alcuni sono risultati errati);
3. `docs/PLAN.md`, `docs/DECISIONI_APERTE.md`, `docs/WALLET_ARCHITECTURE_ANALYSIS.md`,
   `docs/HISTORICAL_IMPORT_ANALYSIS.md`, `docs/MATRICE_PERMESSI_RUOLI.md`.

## 1. BLOCCO N0 — FORENSE GIT (OBBLIGATORIO, PRIMA DI TUTTO)

Un audit recente riporta HEAD `fb61b7c` e working tree pulito, mentre il checkpoint del
Blocco 0 elencava 22 file modificati e 14 non tracciati (riconciliazione, permessi GUI,
E2E reali, load_demo_data, documenti di analisi). Il lavoro potrebbe essere stato
committato altrove, messo in stash o perso.

1. Esegui e riporta nel log: `git status`, `git branch -a`, `git log --oneline -25 --all`,
   `git stash list`, `git reflog -30`.
2. Verifica l'esistenza di: `backend/core/management/commands/load_demo_data.py`,
   `frontend/src/lib/permissions.ts`, `docs/WALLET_ARCHITECTURE_ANALYSIS.md`,
   `docs/HISTORICAL_IMPORT_ANALYSIS.md`, `docs/MATRICE_PERMESSI_RUOLI.md`,
   `docs/MANUAL_VALIDATION_FASE7.md`.
3. Se il lavoro del Blocco 0 è in uno stash o in un commit irraggiungibile: **recuperalo**
   su un branch `recovery/blocco0` senza distruggere nulla, poi integralo nel branch di lavoro.
4. Se è definitivamente perso: scrivilo nel log in evidenza e **rifai il Blocco 0**
   secondo `docs/FASE7_BLOCCO0.md` come primo blocco di lavoro.
5. Crea il tag `pre-night-run` sullo stato di partenza e lavora sul branch
   `fase7/night-run`. Non lavorare mai direttamente su `main`.

## 2. AMBIENTE E BASELINE VERDE

- La suite backend si esegue **solo nello stack Docker**:
  `docker compose exec -T backend python -m pytest -q`.
  I 240 errori da venv host sono dovuti a `DB_HOST=db` non risolvibile fuori da Docker:
  **non sono una regressione**. Rendi esplicito questo nel README e nel Makefile
  (target `test-backend` che usa Docker). Non modificare i settings per farli girare sull'host.
- Test seedfile: eseguili nel container dove il seed reale è montato read-only.
- Se lo stack non è su: `docker compose up -d --build`, `migrate`,
  `load_demo_data --run-checks`. Se Docker non risponde, attendi 2 minuti e riprova
  fino a 5 volte prima di dichiarare BLOCCATO.

Baseline da raggiungere e committare prima di qualunque nuova feature:
- ruff 0 errori, black --check pulito, mypy 0 errori;
- pytest in Docker: 0 failed, 0 error;
- vitest, tsc, eslint, build frontend: verdi;
- E2E: **ogni test indipendente** (crea i propri dati o parte da reset deterministico),
  nessuna dipendenza dall'ordine; la suite E2E reale eseguita **3 volte di fila** con
  risultato identico, 0 failed, 0 skipped. `phase3.spec.ts` usa `page.route`: lascialo,
  ma va etichettato come test di UI con mock e non vale come evidenza E2E.
- Pulizia: eliminare `docs/BLOCCO0_PIANO_OPERATIVO.md` e `scripts/load_demo.py`
  (unico loader: `load_demo_data`); rimuovere `tsconfig.app.tsbuildinfo` da git e
  aggiungerlo a `.gitignore`; `load_demo_data` deve rifiutarsi di girare con settings prod.
- Fix `ppm.py` (chiusura workbook openpyxl): mantenuto, commit separato.

## 3. DEFINITION OF DONE DI UNA SLICE (VINCOLANTE)

Una slice è CHIUSA solo se:
1. API reale con permessi per ruolo (backend applica sempre l'autorizzazione) e test backend;
2. GUI con form, validazione, conferma, feedback; niente placeholder né valori hardcoded;
3. E2E Playwright **senza page.route**, su backend e DB reali, che esegue la mutation e
   verifica il dato dopo reload (UI) e via API; almeno un caso negativo per ruolo;
4. valori in giornate/importi sempre Decimal lato backend e stringhe lato API; il frontend
   formatta e non ricalcola;
5. sezione aggiunta in `docs/MANUAL_VALIDATION_FASE7.md`: utente demo, URL, passi numerati,
   risultato atteso;
6. riga FG aggiornata in `FUNCTIONAL_GAP_ANALYSIS.md` con riferimenti file:riga a test
   **realmente eseguiti e passati**. Stato massimo raggiungibile: **PARZIALE**, con nota
   "Implementazione completa — in attesa di verifica manuale". **COMPLETA la assegna solo
   l'utente** dopo il collaudo manuale.
7. tutta la suite (backend + frontend + E2E) ancora verde dopo la slice.

## 4. ELENCO DEI BLOCCHI, IN ORDINE

Esegui in quest'ordine. Un blocco BLOCCATO non ferma i successivi, salvo dipendenza diretta.

**N1 — Baseline verde e pulizia** (sezione 2).

**N2 — Wallet: assegnazione e residuo per architetto (FG-013, FG-014).**
Decisione presa: **Opzione A** di `WALLET_ARCHITECTURE_ANALYSIS.md`.
- FK `assignee` → Person su `WalletAllocation`, nullable per lo storico esistente,
  obbligatoria per le nuove allocazioni create da GUI.
- Un'allocazione = un solo architetto. Due architetti = due allocazioni.
- Riassegnazione = riduzione dell'allocazione al consumato + nuova allocazione
  (meccanismo append-only esistente), con audit.
- Consumo per architetto = somma dei consumi delle sue allocazioni; residuo =
  allocato − consumato, calcolato nel dominio.
- GUI: creazione nuova allocazione (origine, progetto/attività, architetto, giornate,
  data, note) con anteprima e conferma; vista per architetto con allocato/consumato/residuo.
- Vincolo: non si può allocare più del disponibile del wallet; errore chiaro in GUI.
- Migrazione reversibile. Annota in `DECISIONI_APERTE.md` che la scelta A va confermata
  dall'utente.

**N3 — Amministrazione (FG-038) + import da GUI (FG-023…FG-025 e correlate).**
Ripristina la voce `/amministrazione` solo con funzioni reali, visibile solo ad admin:
- import seed JSON: upload → validazione schema → dry-run con riepilogo
  (conteggi, errori, warning) → conferma → apply → esito e storico import;
- import PPM: upload → anteprima → apply → esito;
- export già esistenti esposti come download;
- utenti e ruoli: elenco e assegnazione ruolo (no gestione password custom: usa i
  meccanismi Django esistenti).
Ciò che non è ragionevole fare in GUI resta in Django admin, documentato.

**N4 — Completamento flussi PARZIALI ad alto valore**, nell'ordine:
coda di revisione con flusso completo; dettaglio progetto con azioni operative;
riconciliazione con azioni di risoluzione; canone con dettaglio semestre;
navigazione e menu filtrati per ruolo (FG-034); dashboard con KPI coerenti.
Per ognuno applica la DoD della sezione 3.

**N5 — Capability SOLO BACKEND rimanenti** di `FUNCTIONAL_GAP_ANALYSIS.md`
(incluso il ledger consuntivi in sola consultazione, se presente in matrice):
esporle in GUI solo se previste da `PLAN.md`. Se non previste, non implementarle e
scrivilo nel log.

**N6 — Import storico Excel (FG-026).**
- Se in `data/seed/` sono presenti file `.xlsx` storici: analizza fogli/colonne
  **senza copiare dati reali nei documenti o nei test**, completa la colonna
  "origine Excel" di `HISTORICAL_IMPORT_ANALYSIS.md`, implementa un converter
  Excel → seed JSON 1.0.0 con report di riconciliazione dei conteggi sorgente/destinazione
  e dry-run obbligatorio. Test solo con fixture sintetiche con la stessa struttura.
- Se non ci sono: non implementare nulla, segna N6 come BLOCCATO (input mancante).

**N7 — Scheduler controlli (FG-037)**: solo se previsto in `PLAN.md`; altrimenti salta
e annotalo.

**NON fare**: FG-039 (verifica manuale: la esegue l'utente), push, deploy.

## 5. CICLO DI LAVORO PER OGNI BLOCCO

```
leggi log → scrivi nel log "INIZIO Nx" con obiettivo e piano breve
→ implementa a piccoli passi
→ esegui test pertinenti → se rossi: correggi
→ suite completa (backend Docker + frontend + E2E)
→ commit(s) con messaggio convenzionale (feat/fix/test/docs/chore)
→ aggiorna FUNCTIONAL_GAP_ANALYSIS.md e MANUAL_VALIDATION_FASE7.md
→ scrivi nel log "FINE Nx" con evidenze (comandi, numeri, commit)
→ passa al blocco successivo
```

Regola anti-loop: se lo stesso problema resiste a **3 tentativi con approcci diversi**
o a circa **60 minuti**:
1. salva il lavoro su un branch `wip/Nx-<descrizione>` con commit "WIP — non funzionante";
2. riporta `fase7/night-run` all'ultimo commit verde (`git switch` + `git restore`,
   mai `reset --hard` su commit già validi di altri blocchi);
3. scrivi nel log: sintomo, ipotesi, tentativi, ultimo errore completo;
4. marca il blocco BLOCCATO e passa al successivo.

## 6. DIVIETI ASSOLUTI

- Mai indebolire i test per farli passare: niente `skip`, `xfail`, `only`, timeout
  gonfiati, asserzioni rimosse o rese generiche, `page.route` negli E2E reali.
  Se un test è davvero sbagliato, correggilo motivando nel log.
- Mai modificare, spostare o committare `data/seed/` o dati aziendali reali.
  Nessun dato reale in test, fixture, documenti, log o screenshot.
- Mai `git push`, `git push --force`, `reset --hard` su main, riscrittura della storia,
  cancellazione di branch o tag.
- Mai `docker system prune`, `docker volume rm` o cancellazione dei volumi del DB.
- Mai cambiare stack, introdurre framework o librerie non indispensabili
  (se indispensabile: motivazione nel log).
- Mai float per giornate o importi.
- Mai modificare formule contabili non coinvolte dal blocco; le regole di business
  restano: residui validi anno corrente + precedente; i progetti in corso
  (es. Protection Model) non generano residuo scadente; fatturazione "facility" su Imola
  con consuntivazione parallela.
- Mai segnare COMPLETA alcuna capability.
- Mai comandi fuori dal repository `C:\dev\supplier-ledger`, salvo Docker.

## 7. CONDIZIONI DI ARRESTO ANTICIPATO

Fermati, scrivi il report finale e non fare altro se:
- rilevi che `data/seed/` o il DB con dati reali sarebbero modificati o cancellati;
- la suite che era verde diventa rossa e non riesci a ripristinarla tornando all'ultimo
  commit verde;
- Docker resta indisponibile dopo 5 tentativi distanziati (in quel caso puoi comunque
  proseguire con lavoro che non richiede Docker, marcandolo "non verificato E2E");
- lo spazio disco scende sotto 5 GB.

## 8. LOG E REPORT FINALE

`docs/NIGHT_RUN_LOG.md` — aggiornato e committato a ogni INIZIO/FINE blocco, con orario.

`docs/NIGHT_RUN_REPORT.md` — a fine lavoro, contenente:
1. esito di N0 (lavoro del Blocco 0 trovato / recuperato / rifatto);
2. tabella blocchi: stato (CHIUSO / BLOCCATO / SALTATO), commit, FG coinvolte;
3. ultimi risultati: ruff, black, mypy, pytest Docker, vitest, tsc, eslint, build,
   3 run E2E (numeri esatti, non aggettivi);
4. conteggi matrice FG prima/dopo e righe cambiate;
5. decisioni prese in autonomia;
6. blocchi BLOCCATI con causa e branch `wip/`;
7. migrazioni create e se sono reversibili;
8. comandi esatti per avviare lo stack e URL;
9. **percorso di collaudo per l'utente**, ordinato per priorità, che rimanda alle sezioni
   di `MANUAL_VALIDATION_FASE7.md`;
10. `git log --oneline` dal tag `pre-night-run`, `git status`.

Nel report usa "funziona/verificato" solo con l'evidenza accanto.

Lascia lo stack Docker acceso con i dati demo caricati, così l'utente può collaudare subito.

FINE SPECIFICA
