# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/it/1.1.0/). Una voce per fase del piano.

## [Non rilasciato]

### Fase 4 — Controlli e riconciliazione

**Aggiunto**

- Catalogo delle 18 regole di controllo automatico `CHK_*` in `backend/domain/checks.py`.
- Runner idempotente in `backend/anomalies/runner.py` con fingerprinting stabile, deduplica, risoluzione automatica delle condizioni non più rilevate e gestione deroghe.
- Supersessione completa delle anomalie seed secondo D-05 (chiusura uno-a-uno e uno-a-molti a copertura integrale).
- Comando di gestione `manage.py run_checks` ed endpoint REST `POST /api/v1/checks/run` e `POST /api/v1/anomalies/{id}/{take,resolve,accept}`.
- Schermate UI per Inbox anomalie e Riconciliazione PPM con flussi browser verificati.
- Test negativi e positivi delle regole, test del runner e test E2E Playwright dedicati.

**Verificato**

- Esecuzione sul seed reale con 34 anomalie create e 6 anomalie seed sostituite al primo passaggio, e 0 anomalie create/aggiornate/risolte al secondo passaggio (deduplicazione completa).
- Verificati sul campo i casi cardine: `CHK_OVERRUN_PROJECT` (IM24133 MEDIA da PPM, IM26292 ALTA), `CHK_MISSING_IN_PPM` (IM25379), `CHK_DOUBLE_COUNT` (RM-300228 / RM-300229), `CHK_ALLOC_NO_SOURCE` (W26-008), `CHK_CLOSED_NO_DATE` (IM26034, IM26047, IM26075), `CHK_RECON_DELTA` (8 KO) e IM25138 OK.
- Supersessione osservata sul seed reale: `AN-004`, `AN-005`, `AN-006`, `AN-008` (uno-a-uno) e `AN-003`, `AN-007` (uno-a-molti) chiuse con nota "sostituita da <rule_code>".
- Gate di qualità superati nel container Docker: 262 test backend, ruff, black, mypy, check deploy, lint/build frontend ed E2E Chromium completi.

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
