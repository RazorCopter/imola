# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/it/1.1.0/). Una voce per fase del piano.

## [Non rilasciato]

### Fase 7 — Rifiniture evolutive e conformità operativa (7 Tranche)

**Aggiunto**

- **Tranche 1 (Contratti e Autorizzazioni Granulari)**: introdotto catalogo di 13 capability granulari (`backend/core/capabilities.py`), modello di autorizzazione su API REST e controllo di concorrenza ottimistica (`ETag` / `expected_version` con HTTP 428/409).
- **Tranche 2 (UX Amministrazione e Allineamenti Nomenclatura)**:
  - Tasto "Conferma e applica" evidenziato, incorniciato e verde nella sezione amministrazione.
  - Ridenominazione di interfaccia "CANONE" in "ORGANICO ALLARGATO".
  - Preselezione automatica dell'ultimo semestre movimentato.
  - Visualizzazione colonna `nome_progetto` nella tabella di riconciliazione PPM.
- **Tranche 3 (Gestione Utenti e Matrice Privilegi)**:
  - Tab dedicato per gestione CRUD utenti, reset password e assegnazione ruoli.
  - Tab "Ruoli e Privilegi" per configurare a runtime le capability per ciascun ruolo (`RoleCapabilityOverride`).
  - Protezione per utente Admin (privilegi pieni immutabili) e audit trail amministrativo (`AdminAuditEvent`).
- **Tranche 4 (Editing Progetti con Pulsante Arancione EDIT)**:
  - Pulsante arancione **EDIT** su ogni riga di `ProjectsPage` e nella testata di `ProjectDetailPage`.
  - Modale di editing completa con blocco read-only esplicito del codice progetto e controllo optimistic locking.
- **Tranche 5 (Editing Wallet e Rettifiche Append-Only)**:
  - Pulsante arancione **EDIT** sulle allocazioni in `WalletPage`.
  - Modale di modifica giornate, assegnatario architetto e note.
  - Sezione di rettifica contabile append-only tramite storno (`TimesheetEntry.build_reversal()`) e nuova registrazione senza violazione dei trigger PostgreSQL.
- **Tranche 6 (Reset Dati Applicativi "ELIMINA DB")**:
  - Zona pericolosa in amministrazione con pulsante rosso **ELIMINA DB**.
  - Dialog di controverifica con anteprima conteggi, token di sicurezza effimero e digitazione obbligatoria di `ELIMINA`.
  - Pulizia atomica delle sole tabelle operative (progetti, consuntivi, wallet, canoni, import, anomalie), preservando utenti, gruppi, ruoli e impostazioni.

### Fase 5 — Import PPM ed export

**Aggiunto**

- Parser Excel tollerante in `backend/importers/ppm.py` per estratti PPM (ricerca header prime 15 righe, estrazione data via regex, quadratura totali declared ±0.01 gg).
- Supporto estratti PPM PDF via `pdfplumber` con messaggio d'errore esplicito e indicazione di utilizzare l'Excel originale.
- Aggiornamento consuntivi append-only **a differenza** rispetto al totale interno del progetto: delta positivo genera `TimesheetEntry` con `source=PPM_IMPORT`; delta negativo genera storno con `source=STORNO`. Nessuna sovrascrittura o cancellazione fisica.
- Rollback transazionale dei batch PPM tramite righe di storno che puntano alle entry generate (`reverses`), preservando l'integrità del ledger e il divieto di DELETE (D-14).
- Comando di gestione `manage.py import_ppm` (dry-run e apply) e `manage.py rollback_ppm`.
- Modulo di export `backend/exporters.py` ed endpoint REST:
  - `GET /api/v1/export/excel`: fogli `Progetti`, `Wallet`, `Canone`, `Riconciliazione`, `Anomalie`.
  - `GET /api/v1/export/csv/<entity>`: export CSV per entità singola.
  - `GET /api/v1/export/json`: payload JSON conforme a schema 1.0.0.
- Configurazione volume `data/ppm/` in sola lettura in `docker-compose.override.yml` e pattern `.gitignore` per file PPM reali.

**Verificato**

- Accettazione sul seed reale con l'estratto `data/ppm/Progetti_Gruppo_Progetto_Banca_Mediolanum_Wallet_2026.xlsx`:
  - Dry-run: 11 righe riconosciute, 0 non riconosciute, quadratura totali OK (199.1250 gg), data estrazione `2026-10-16 11:05:18`.
  - Apply: 8 movimenti creati (5 `PPM_IMPORT`, 3 `STORNO`) per i soli progetti KO con i delta esatti (IM24133 +1,5; IM25244 +1,115; IM25306 +1,4175; IM26022 +0,865; IM25198 +0,4975; IM25197 −0,38; IM25216 −0,3725; IM26125 −0,0625).
  - Re-import: 0 nuove entry create (idempotenza verificata).
  - Post-apply: riconciliazione con 11 progetti OK su 11.
  - Export: JSON schema 1.0.0 (40 progetti, 30 allocazioni wallet, 2 canoni, 40 righe riconciliazione), CSV ed Excel a 5 fogli generati e validati.
- Tutti i gate superati: 273 test pytest backend, Ruff, Black, Mypy, `check --deploy`, ESLint, Vitest (13 passed), build Vite ed E2E Playwright Chromium (3 passed).

### Fase 4 — Controlli e riconciliazione

**Aggiunto**

- Catalogo delle 18 regole di controllo automatico `CHK_*` esattamente aderenti alla specifica (§4 PLAN.md): `CHK_DATE_ORDER`, `CHK_END_PASSED_ACTIVE`, `CHK_CLOSED_NO_DATE`, `CHK_OVERRUN_PROJECT`, `CHK_OVERRUN_ALLOCATION`, `CHK_ALLOC_EXCEEDS_RESIDUAL`, `CHK_RESIDUAL_EXPIRING`, `CHK_RESIDUAL_UNALLOCATED_CLOSED`, `CHK_ALLOC_FROM_EXPIRED`, `CHK_RECON_DELTA`, `CHK_MISSING_IN_PPM`, `CHK_DOUBLE_COUNT`, `CHK_CANONE_UNDERUSE`, `CHK_CANONE_OVERUSE`, `CHK_ACTIVE_WITHOUT_OFFER`, `CHK_ALLOC_NO_SOURCE`, `CHK_UNVERIFIED_DATA`, `CHK_MILESTONE_SLIPPED`.
- Rimosse le regole sperimentali e documentata la proposta D-17 in `docs/DECISIONI_APERTE.md` per estensioni future non attivate in v1.
- Allineata la supersessione di `AN-003` su `CHK_UNVERIFIED_DATA` per i 9 progetti in stato DA_VERIFICARE.
- Runner idempotente in `backend/anomalies/runner.py` con fingerprinting stabile, deduplica, risoluzione automatica delle condizioni non più rilevate e gestione deroghe.
- Supersessione completa delle anomalie seed secondo D-05 (chiusura uno-a-uno e uno-a-molti a copertura integrale).
- Comando di gestione `manage.py run_checks` ed endpoint REST `POST /api/v1/checks/run` e `POST /api/v1/anomalies/{id}/{take,resolve,accept}`.
- Schermate UI per Inbox anomalie e Riconciliazione PPM con flussi browser verificati.
- Test negativi e positivi delle regole, test del runner e test E2E Playwright dedicati.

**Verificato**

- Esecuzione sul seed reale (as_of 2026-10-16): 44 anomalie create e 6 anomalie seed sostituite al primo passaggio; 0 create/aggiornate/risolte al secondo passaggio (deduplicazione completa).
- Riscontri verificati:
  - `CHK_OVERRUN_ALLOCATION`: W26-014, W26-016, W26-019 (3 istanze).
  - `CHK_END_PASSED_ACTIVE`: 11 progetti con data fine prevista superata alla data di riferimento.
  - `CHK_RESIDUAL_EXPIRING`: 0 sul seed attuale; test sintetico verificato su IM24517 chiuso al 2025-05-30 con scadenza 31/12/2026.
  - `CHK_RESIDUAL_UNALLOCATED_CLOSED`: 0 sul seed attuale (i progetti chiusi senza data non sono considerati residui validi).
  - `CHK_ALLOC_EXCEEDS_RESIDUAL`: 2 istanze su IM25318 (allocazioni W26-006 e W26-022).
  - `CHK_OVERRUN_PROJECT`: IM24133 MEDIA (da PPM), IM26292 ALTA (da ledger interno).
  - `CHK_MISSING_IN_PPM`: IM25379 MEDIA.
  - `CHK_DOUBLE_COUNT`: RM-300228 e RM-300229 MEDIA.
  - `CHK_ALLOC_NO_SOURCE`: W26-008 ALTA.
  - `CHK_CLOSED_NO_DATE`: IM26034, IM26047, IM26075 ALTA.
  - `CHK_RECON_DELTA`: 8 KO (IM24133, IM25197, IM25198, IM25216, IM25244, IM25306, IM26022, IM26125); IM25138 allineato OK.
- Supersessione osservata sul seed reale: `AN-003` (CHK_UNVERIFIED_DATA), `AN-004` (CHK_OVERRUN_PROJECT), `AN-005` (CHK_DOUBLE_COUNT), `AN-006` (CHK_MISSING_IN_PPM), `AN-007` (CHK_RECON_DELTA), `AN-008` (CHK_CANONE_UNDERUSE) marcate RISOLTA con nota "sostituita da <rule_code>".
- Credenziali E2E parametrizzate da variabili di ambiente `E2E_USERNAME` e `E2E_PASSWORD`.
- Gate di qualità superati nel container Docker: 268 test backend, ruff, black, mypy, check deploy, lint/build frontend ed E2E Chromium completi.

### Fase 3 — UI core

**Aggiunto**

- Layout applicativo responsive con sidebar collassabile, topbar, tema light/dark e command palette con ricerca API di progetti, attività wallet e anomalie.
- Componenti condivisi per KPI, stati distinti, giornate, tabelle virtualizzate e stati loading/empty/error.
- Dashboard operativa con KPI e azioni basati esclusivamente sui valori pre-calcolati dall'API.
- Schermate Progetti (lista, filtri, dettaglio a 8 tab e wizard), Wallet (flussi e residui per validità) e Canone (selettore semestre, andamento e riepilogo uffici).
- Test API per indice canoni, creazione progetto e ricerca globale; test componenti e flussi Playwright per dashboard e progetti.

**Verificato**

- Suite backend completa, gate Ruff/Black/mypy/check deploy, lint/test/build frontend ed E2E Chromium in container dedicato.
- Sul seed reale: 40 progetti, 2 canoni, 48 sotto-attività, 21 attività wallet non tecniche, 24 allocazioni 2026 e 11 anomalie; wallet 10.1000 gg, budget in corso 60.9150 gg e sforamenti -8.2400 gg.

### Fase 2 — budget in corso senza doppio conteggio

**Modificato**

- `budget_residuo_progetti_in_corso`: ora sottrae la quota `released_to_wallet_days` per ciascun progetto ATTIVO, evitando il doppio conteggio sul seed (60.9150 gg).
- Esposto `sforamenti_progetti_in_corso`: somma dei residui negativi dei progetti ATTIVI (-8.2400 gg).
- Aggiornati test di accettazione sul seed reale e test di dominio del saldo wallet.

### Fase 2 — verifica seed in Docker

**Verificato**

- Presenza del file seed reale `data/seed/seed_imola_2026-10-16.json` montato in sola lettura nel container.
- Suite di accettazione completa: 235 test superati, 0 skipped, inclusi i 4 test marcati `seedfile`.
- PASSO 5: simulazione dry-run, applicazione, reimport idempotente (0 creati, 0 aggiornati), rollback atomico e reimport finale con 348 record creati e 13 scarti.
- PASSO 6: verifiche SQL sul database PostgreSQL 16 del container e violazione tentativi UPDATE/DELETE bloccati dal trigger append-only dei consuntivi.
- PASSO 7: autenticazione via nginx con sessione 401 per richieste anonime, bilancio wallet 2026 con 130.8900 allocati, 120.7900 consumati, 10.1000 disponibili, 10.0000 residui validi non allocati, 42.5400 potenziali e 70.9150 progetti in corso; coda di revisione con 12 progetti senza avvisi per residui non positivi; 11 anomalie seed con external_ref `AN-001`…`AN-011`; riconciliazione PPM con 40 righe analizzate.

### Fase 2 — rifiniture residui e coda di revisione

**Aggiunto**

- Modello `Project`: aggiunto il campo `released_to_wallet_days` con tracciamento storico e default 0.
- Endpoint `POST /api/v1/projects/{id}/release-to-wallet`: rilascia quote di residuo al wallet per soli progetti ATTIVI, con motivazione obbligatoria e controllo di capienza sul residuo disponibile.
- Dominio wallet: calcolo di `residui_validi_non_allocati` su progetti CHIUSO non scaduti con data certa più quote rilasciate da progetti ATTIVI al netto delle allocazioni uscite; esposta la metrica informativa `budget_residuo_progetti_in_corso` e rinominato il campo in `capienza_wallet_potenziale`.
- Decisione D-16 in `docs/DECISIONI_APERTE.md`: quota del residuo di IM26254 impostata a 10 gg in fase di import seed.
- Modello `Anomaly`: aggiunto `external_ref` per memorizzare l'`id_import` del seed (`AN-001`…`AN-011`), esposto in API e admin.
- Coda di revisione: soppressi gli avvisi di scadenza per progetti con residuo non positivo (`<= 0`).
- Script PowerShell `scripts/pg-local.ps1` (`start`, `stop`, `status`, `psql`) per fallback su Windows, documentato in `README.md`.
- Test di regressione dedicati per rilascio wallet, coda di revisione, anomalie seed e accettazione seedfile su `IM26254` e `IM24517`.

### Verifica ambiente Docker

**Corretto**

- Aggiunto `.dockerignore` per escludere segreti, dati reali, ambienti locali, dipendenze e volumi persistenti dal contesto di build.
- Limitato il mount del seed reale al solo override di sviluppo, in sola lettura sotto `/app/data/seed`; il seed resta escluso dalle immagini.
- Incluso il solo `seed_schema_v1.json` versionato nelle immagini backend dev e prod, necessario all'importer e alla suite eseguita nel container.
- Reso affidabile l'healthcheck nginx usando l'indirizzo IPv4 esplicito `127.0.0.1`.

**Verificato**

- Build Docker pulita, stack healthy con nginx, backend e PostgreSQL 16, health endpoint HTTP 200.
- Suite backend su Python 3.12/PostgreSQL 16, controlli Ruff/Black, check migrazioni e check deploy; lint, typecheck e test frontend nel container.

### Fase 2 — Import seed JSON

**Aggiunto**

- Cuore importer seed in `backend/importers/seed_json.py` (~1029 righe) suddiviso in 5 blocchi atomici e idempotenti: configurazione/organizzazioni/persone, progetti/milestone/consuntivi diretti, canoni/sotto-attività/consuntivi canone, wallet 2026/attività/allocazioni/movimenti e storico 2025, snapshot PPM e anomalie seed.
- Strategia di upsert basata su chiavi naturali con ownership del batch assegnata esclusivamente in creazione; consuntivi append-only con causale `SEED_INIZIALE`, gestione degli scarti motivati su wallet storico (D-04) e popolamento della coda di revisione.
- Orchestratore batch in `backend/importers/batch.py`: lettura protetta dei file, digest SHA-256 (`content_hash`), validazione schema tramite doppia lettura (float per validazione schema, Decimal per importazione dati), ciclo di vita `ImportBatch`, persistenza strutturata degli `ImportIssue` (avvisi ed errori) e integrazione report.
- Management command CLI `import_seed` (`backend/imports/management/commands/import_seed.py`): modalità `--dry-run` transazionale senza persistenza (rollback con eccezione sentinella), modalità `--apply` atomica, flag `--schema` per validazione isolata, output testuale e formattato `--json`, codici di uscita distinti.
- Modulo di rollback sicuro in `backend/importers/rollback.py` e relativo management command `rollback_seed`: eliminazione esclusiva dei record generati dal batch, ordine FK sicuro a cascata, acquisizione lock pessimista (`select_for_update`), verifica bloccante contro batch successivi o già rollbackati, autorizzazione bypass trigger append-only tramite `allow_ledger_mutation()` e tracciamento audit.
- Meccanismo di supersessione anomalie (D-05) in `backend/anomalies/models.py`: campo `superseded_by`, metodo `mark_superseded()`, mappa dichiarativa `SEED_SUPERSESSION_MAP` (7 anomalie mappate su regole automatiche di Fase 4 e 4 incoerenze manuali non mappate), protezione da sovrascritture di stato nei reimport.
- Estensione modello `ImportBatch` con `content_hash` e nuovo modello `ImportIssue` per la registrazione degli scarti/avvisi nel database; migrazione `0002_historicalimportbatch_content_hash_and_more.py` e inline in `imports/admin.py`.

**Test e verifiche**

- Suite estesa a 214 test passati (158 test di Fase 1 + 56 nuovi test dedicati: 20 per `importers/seed_json.py`, 10 per il command `import_seed`, 12 per il modulo e command di rollback, 10 per la supersessione D-05).
- Controlli di qualità del codice superati: Ruff, Black, `python manage.py check` e verifica migrazioni senza problemi.

### Fase 1 - Fondamenta

**Aggiunto**

- Scaffolding del repository: backend Django 5 / DRF / PostgreSQL 16, frontend React 18 +
  TypeScript + Vite + Tailwind, Docker Compose (db, backend, frontend, nginx) con porte non
  privilegiate, volumi bind e healthcheck su ogni servizio, `.env.example` completo.
- Modello dati completo con migrazioni iniziali: organizzazioni e persone, progetti e
  milestone, canone e sotto-attività, wallet (anni, attività, allocazioni), consuntivi,
  snapshot PPM e profili di import, anomalie, batch di import, impostazioni globali.
- Tracciatura su tutte le entità: UUID, timestamp, autore, `version` per il lock ottimistico
  e storico delle modifiche con django-simple-history.
- Invarianti contabili a livello di database: budget non negativo, fine prevista dopo
  l'inizio, data di chiusura obbligatoria per i progetti chiusi (salvo import, vedi D-03),
  consuntivi append-only con esattamente un bersaglio e giornate diverse da zero.
- `domain/` con le formule, in un punto solo: `money.py` (Decimal a 4 cifre, mai float),
  `residuals.py` (R2 e R3), `wallet_balance.py` (R3 lato wallet), `canone_status.py` (R4),
  `reconciliation.py` (R6).
- API v1 di autenticazione a sessione con CSRF, astrazione del provider pronta per Entra ID
  ma non attiva, e endpoint delle viste calcolate (bilanci progetti, wallet, canone,
  riconciliazione) con errori in formato RFC 7807 in italiano.
- Ruoli applicativi (admin, responsabile BMED, referente BMED, fornitore) con permessi
  applicati lato API, comando `bootstrap_roles` e comando `backup` per Synology.
- Frontend: tema chiaro e scuro con rispetto della preferenza di sistema, sidebar
  collassabile, Command Palette (Ctrl/Cmd+K), catalogo i18n italiano con scheletro inglese,
  formattazione italiana dei numeri (`1.234,56 gg`) e modale di sessione scaduta che
  conserva il lavoro in corso invece di eseguire il logout.
- Qualità: ruff, black, mypy, eslint, prettier, pre-commit e una guardia che impedisce di
  versionare il seed con i dati reali del fornitore.

**Corretto durante la verifica**

- Le richieste non autenticate rispondevano 403: DRF declassa `NotAuthenticated` quando
  l'autenticazione è a sessione. Ora tornano **401** con `code=session_expired`, che è la
  condizione su cui il frontend apre il modale di re-login senza perdere il lavoro.
- I Decimal inseriti direttamente in una Response uscivano come float (7.5 invece di
  "7.5000"): `COERCE_DECIMAL_TO_STRING` vale solo per i serializer. Aggiunto
  `api/renderers.py`, che serializza ogni Decimal come stringa.
- L'applicazione `core` era priva del pacchetto migrazioni: le sue tabelle venivano create
  via syncdb prima di `auth`, rompendo la chiave esterna dello storico. Migrazione aggiunta.

**Test**

- 142 test backend, tutti verdi su PostgreSQL 16.4, copertura di `domain/` al **97%**
  (gate 85%). Fra questi i casi obbligatori del par. 11: 11.1 (progetto
  del 2024 ancora attivo, residuo 0), 11.3 (chiuso il 15/11/2025: valido al 31/12/2026,
  in scadenza il 02/10/2026, scaduto dal 01/01/2027), 11.4 (wallet 2026: allocato 130,89 -
  consumato 120,79 = 10,10 disponibili, residui da verificare esclusi), 11.5 (residuo da
  10 gg con allocazione a zero), 11.7 (canone S2: target 102,35 e delta +2,08), 11.9
  (riconciliazione IM25138 entro tolleranza).
- 8 test sulla formattazione lato frontend (Vitest); build di produzione e lint puliti.
- Verifica manuale degli endpoint: `/health`, sessione anonima 401, login, impostazioni,
  bilancio wallet, riconciliazione e PATCH con permessi.

**Nota sull'ambiente di questa macchina**

- Docker non parte perché WSL2 non è installato: lo sviluppo e i test usano un PostgreSQL 16
  portatile avviato da `scripts/pg-local.sh`. Lo stack Docker Compose resta quello previsto
  per il deploy su Synology, ma su questa macchina non è ancora stato eseguito.
