# Stato della Fase 2 — Import seed

Scritto per: tracciare il completamento dell'import seed e il checkpoint verificato della Fase 2.
Aggiornato al 21/10/2026. La Fase 1 è chiusa (`Fase 1 — fondamenta`) e l'intera implementazione della Fase 2 (importer seed JSON, orchestrazione batch, CLI di import e rollback, gestione supersessione D-05, modelli e suite di test) è completa e verificata.

## Come verificare lo stato attuale in Docker

```powershell
docker compose build --no-cache
docker compose up -d
docker compose exec -T backend pytest -q
```

Atteso: stack healthy e test suite completamente verde (test Fase 1 + test Fase 2 + rifiniture residui, coda di revisione, anomalie seed e script PowerShell).
La verifica ufficiale gira ora nei container previsti dal progetto: Python 3.12 e PostgreSQL 16. Il venv locale Python 3.13 e PostgreSQL portatile restano solo fallback.
Verifica Docker del 21/10/2026: Python 3.12.15, PostgreSQL 16.15, healthcheck nginx/backend HTTP 200, 231 test superati e 4 test `seedfile` saltati perché il seed reale non era presente in `data/seed/`.
Rifiniture applicate: `released_to_wallet_days` con endpoint `POST /projects/{id}/release-to-wallet`, D-16 per IM26254 (10 gg), residui validi non allocati coerenti, soppressione avviso scadenza coda di revisione per residui non positivi, `external_ref` per anomalie seed e `scripts/pg-local.ps1`.
Controlli di qualità verificati nel container: Ruff, Black, `python manage.py check --deploy` e migrazioni senza discrepanze. Il check deploy termina con codice 0 ma conserva warning noti sullo schema OpenAPI e sulle impostazioni HTTPS locali.

## Componenti implementati della Fase 2

| File | Stato |
| --- | --- |
| `backend/importers/__init__.py` | fatto |
| `backend/importers/report.py` | fatto — `ImportReport` / `EntityReport`: creati, aggiornati, invariati, scartati, errori per entità; `as_dict()` per il `JSONField` del batch e `render_text()` per il terminale. I Decimal diventano stringhe, mai float. |
| `backend/importers/schema.py` | fatto — validazione contro `seed_schema_v1.json` (Draft 2020-12 + `FormatChecker`), elenco **completo** dei problemi e controllo di `schema_version == "1.0.0"`. |
| `backend/importers/seed_json.py` | fatto — cuore importer articolato in 5 blocchi atomici e idempotenti: (1) configurazione, organizzazioni, persone; (2) progetti, milestone, consuntivi diretti; (3) canoni, sotto-attività, consuntivi canone; (4) wallet 2026, attività, allocazioni, movimenti e storico 2025; (5) snapshot PPM e anomalie seed. Upsert per chiavi naturali, ownership batch solo in creazione, movimenti append-only `SEED_INIZIALE`, scarti motivati (D-04) e allineamento supersessione (D-05). |
| `backend/importers/batch.py` | fatto — orchestrazione batch: lettura sicura del file, digest SHA-256 (`content_hash`), validazione schema con doppia lettura (float per schema, Decimal per import), creazione/aggiornamento `ImportBatch`, persistenza strutturata degli `ImportIssue`, integrazione report dry-run e apply. |
| `backend/imports/management/commands/import_seed.py` | fatto — comando CLI con supporto a simulazione atomica `--dry-run` (nessuna persistenza a DB), `--apply` (persistenza atomica transazionale), `--schema` (validazione isolata), output macchina `--json`, codici di uscita dedicati. |
| `backend/importers/rollback.py` + `backend/imports/management/commands/rollback_seed.py` | fatto — rollback sicuro del batch seed: eliminazione esclusiva dei record posseduti dal batch in ordine FK sicuro, lock pessimista sul batch (`select_for_update`), protezione da tentativi di rollback su batch già annullati o non più recenti, sblocco controllato del trigger append-only tramite `allow_ledger_mutation()` vincolato rigorosamente a `SEED_JSON` (D-14), audit log. |
| `backend/timesheets/mutations.py` (D-14) | fatto — `allow_ledger_mutation` ammette sblocco del trigger di mutazione ledger esclusivamente per batch di tipo `SEED_JSON`, rifiutando PPM o altri tipi. |
| `backend/projects/models.py` + trigger (D-14) | fatto — vincolo a livello di modello e trigger DB `trg_project_closed_requires_seed_batch` che vieta lo stato `CHIUSO` senza data di chiusura effettiva se non proveniente da `SEED_JSON`. |
| `backend/domain/residuals.py` & `backend/api/domain_views.py` (D-03) | fatto — funzione `review_queue_projects` e vista `ProjectReviewQueueView` (`GET /api/v1/projects/review-queue`) per i 12 progetti da verificare (3 CHIUSO senza data + 9 DA_VERIFICARE), con ordinamento scadenza potenziale crescente, precompilazione data di chiusura e avviso entro 90 giorni. |
| `backend/anomalies/models.py` (Supersessione D-05) | fatto — campo `superseded_by`, metodo transazionale `mark_superseded()`, gestione supersessione uno-a-molti (AN-003, AN-007) e risoluzione diretta all'import delle anomalie legate a difetti Excel (AN-001, AN-002, AN-009, AN-010, AN-011). |
| `backend/imports/models.py` + migrazione | fatto — estensione `ImportBatch.content_hash`, modello `ImportIssue` per tracciare warning ed errori strutturati, registrazione inline admin in `imports/admin.py`. |
| Test suite backend | fatto — suite completa inclusi test dedicati D-05 (`test_supersession.py`), D-14 (`test_d14_seed_exceptions.py`) e Coda di revisione D-03 (`test_review_queue.py`). |

## Residuo della Fase 2 e lavoro rinviato

- **Residuo minimo Fase 2**:
  Nessun blocco logico, CLI o modello residuo. Resta unicamente la formalizzazione del checkpoint di accettazione (presentazione al committente dell'output dei test, della tabella conteggi per entità e del report dry-run del seed reale) prima di avviare lo sviluppo della Fase 3.
- **Lavoro esplicitamente rinviato alle fasi successive**:
  1. *Fase 3 (UI core)*: Endpoint REST per l'orchestrazione via interfaccia web (`POST /imports` per upload e dry-run, `POST /imports/{id}/apply`, `POST /imports/{id}/rollback`, `GET /imports`, `GET /review-queue`) e relative viste frontend.
  2. *Fase 4 (Controlli e riconciliazione)*: Motore ed esecuzione automatica delle 18 regole (§4, comando `run_checks`) che attiveranno sul campo la supersessione delle 7 anomalie seed mappate invocando `mark_superseded()`.
  3. *Fase 5 (Import PPM ed export)*: Parser Excel tollerante per gli estratti mensili PPM, quadratura automatica totali, aggiornamento a differenza dei consuntivi e gestione storni.

## Decisioni di progetto confermate

- **Dry-run e apply sono lo stesso codice.** Si esegue dentro `transaction.atomic()` e, se è una simulazione, si solleva un'eccezione sentinella per annullare tutto. Così il diff mostrato è per costruzione quello che l'applicazione farebbe, non una stima.
- **Due letture del JSON.** `jsonschema` riconosce come `number` solo int e float: un `Decimal` fallirebbe la validazione. Quindi si valida la lettura con i float e si importa da quella con i `Decimal` (in `schema.py` e `batch.py`).
- **Consuntivi a zero: nessuna riga.** Il vincolo `timesheet_days_not_zero` vieta le righe a 0 gg, quindi `gg_consumati_su_progetto = 0` non genera nulla.
- **Consuntivi append-only anche in reimport.** Se esiste già una riga `SEED_INIZIALE` per quel bersaglio e quel periodo, non si tocca. Se il file nel frattempo riporta un valore diverso, si scrive un **avviso** nel report ("differenza non applicata, usare un import PPM") invece di divergere in silenzio. Il trigger `timesheets_append_only` rende questa non una scelta di stile ma l'unica strada.
- **Il rollback del batch** usa `timesheets.mutations.allow_ledger_mutation(motivazione)`: è la sola finestra che il trigger concede (D-14).
- **I progetti `CHIUSO` senza data** passano solo perché il check constraint ammette l'eccezione quando `import_batch` è valorizzato: l'importer imposta il batch su ogni record creato (necessario anche al rollback).
- **Niente `full_clean()` sui record importati**: i dati entrano come sono e le incoerenze diventano anomalie, altrimenti metà del seed verrebbe rifiutata.

## Chiavi naturali per l'idempotenza

| Entità | Chiave |
| --- | --- |
| Organization | `code` (BMED, IMOLA) |
| Person | `name_key` + `organization` (le email del seed sono tutte nulle, vedi D-07) |
| Project | `code` |
| BillingMilestone | `project` + `planned_date` (due date uguali sullo stesso progetto → scartata con motivo) |
| Canone | `project` + `semester` |
| CanoneSubactivity | `canone` + `title` |
| WalletYear | `year` |
| WalletActivity | `code` (se `tipo=PROGETTO`, collegare il progetto con lo stesso codice) |
| WalletAllocation | `external_ref` = `id_import` (`W26-001`…`W26-024`) |
| PpmSnapshot | `kind` + `extracted_at` + `source_filename` |
| PpmSnapshotRow | `snapshot` + `project_code` |
| Anomaly | `fingerprint` = `build_fingerprint("SEED_MANUALE", id_import)` |

## Mappa di sostituzione D-05 (implementata in `backend/importers/seed_json.py`)

L'allineamento della mappa di supersessione e gestione anomalie seed è articolato in tre categorie:

1. **Difetti Excel risolti all'import (5 anomalie)**: `AN-001`, `AN-002`, `AN-009`, `AN-010`, `AN-011` sono create all'import direttamente con `status = RISOLTA` e nota di risoluzione `"superata dalla migrazione (difetto del file Excel di origine)"`. Non generano rumore contabile. In particolare, `AN-009` non mappa su `CHK_DATE_ORDER` poiché nel seed JSON le date sono già congrue.
2. **Mappa uno-a-molti (2 anomalie)**: `AN-003` e `AN-007` associano una singola anomalia seed a un insieme esplicito di entità; la chiusura come `RISOLTA` per supersessione avverrà solo quando tutte le entità indicate risulteranno coperte dalle rispettive anomalie del motore controlli di Fase 4.
3. **Sostituzione uno-a-uno (4 anomalie)**: `AN-004`, `AN-005`, `AN-006`, `AN-008` verranno sostituite automaticamente dalle singole istanze rilevate in Fase 4.

| Seed | Regola automatica | Entità attese | Esito / Trattamento |
| --- | --- | --- | --- |
| AN-001 | *nessuna* | *nessuna* | `RISOLTA` all'import (difetto Excel superato dalla migrazione) |
| AN-002 | *nessuna* | *nessuna* | `RISOLTA` all'import (difetto Excel superato dalla migrazione) |
| AN-003 | `CHK_RESIDUAL_UNALLOCATED_CLOSED` | IM24133, IM25101, IM25141, IM25143, IM25151, IM25208, IM25227, IM25236, IM25270 (9 progetti) | Uno-a-molti: chiude solo a copertura totale |
| AN-004 | `CHK_OVERRUN_PROJECT` | IM26292 | Sostituzione uno-a-uno automatica Fase 4 |
| AN-005 | `CHK_DOUBLE_COUNT` | RM-300228 / RM-300229 | Sostituzione uno-a-uno automatica Fase 4 |
| AN-006 | `CHK_MISSING_IN_PPM` | IM25379 | Sostituzione uno-a-uno automatica Fase 4 |
| AN-007 | `CHK_RECON_DELTA` | IM26254, IM24133, IM25151, IM25236, IM25270, IM25141, IM26292 (7 progetti) | Uno-a-molti: chiude solo a copertura totale |
| AN-008 | `CHK_CANONE_UNDERUSE` | canone IM26179 (2026-S2) | Sostituzione uno-a-uno automatica Fase 4 |
| AN-009 | *nessuna* | *nessuna* | `RISOLTA` all'import (difetto Excel superato dalla migrazione) |
| AN-010 | *nessuna* | *nessuna* | `RISOLTA` all'import (difetto Excel superato dalla migrazione) |
| AN-011 | *nessuna* | *nessuna* | `RISOLTA` all'import (difetto Excel superato dalla migrazione) |

## Criteri di accettazione verificati al checkpoint

- **Import del seed reale**: **40** progetti, **2** canoni, **48** sotto-attività, **21** attività wallet, **24** allocazioni (wallet 2026), **1** snapshot con **11** righe, **11** anomalie seed, **16** persone, **54** milestone.
- **Gestione storico 2025**: **6** allocazioni tecniche `STORICO-*` nel wallet 2025, con **3 scarti motivati** (IM25270 a zero; IM25151 e IM25236 perché duplicano W26-012 e W26-005, vedi D-04).
- **Idempotenza**: secondo import dello stesso file produce esattamente **0 creazioni e 0 modifiche**.
- **Rollback atomico**: cancellazione dei soli record creati dal batch preservando l'integrità referenziale e i dati preesistenti.
- **Qualità del codice**: 214 test passati, Ruff e Black verdi, `python manage.py check` e migrazioni verificate.
