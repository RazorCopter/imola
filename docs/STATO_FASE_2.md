# Stato della Fase 2 — Import seed (lavoro interrotto)

Scritto per: chi riprende il lavoro (me stesso o un altro sviluppatore) alla prossima sessione.
Aggiornato al 20/10/2026, fine giornata. La Fase 1 è chiusa e committata (`Fase 1 — fondamenta`).

## Dove si riparte in due comandi

```bash
scripts/pg-local.sh start                      # PostgreSQL 16 portatile su 127.0.0.1:5433
cd backend && ../.venv/Scripts/python.exe -m pytest -q
```

Atteso: **158 passati**. Il venv è `.venv/` (Python 3.13 locale, Django 5.2.18); Docker su
questa macchina non parte perché manca WSL2, quindi si usa l'istanza portatile.

## Cosa è già fatto della Fase 2

| File | Stato |
|---|---|
| `backend/importers/__init__.py` | fatto |
| `backend/importers/report.py` | fatto — `ImportReport` / `EntityReport`: creati, aggiornati, invariati, scartati, errori per entità; `as_dict()` per il `JSONField` del batch e `render_text()` per il terminale. I Decimal diventano stringhe, mai float. |
| `backend/importers/schema.py` | fatto — validazione contro `seed_schema_v1.json` (Draft 2020-12 + `FormatChecker`), elenco **completo** dei problemi e controllo di `schema_version == "1.0.0"`. |

Verificato sul seed reale: validazione superata, decimali preservati come `Decimal`, conteggi
letti dal file 16 persone / 40 progetti / 2 canoni / 21 attività / 24 allocazioni /
1 snapshot / 11 anomalie, e **130,89 − 120,79 = 10,10** (caso 11.4) già confermato in lettura.

## Cosa resta da scrivere

1. `importers/seed_json.py` — il cuore: mappatura e upsert idempotente.
2. `importers/supersession.py` — mappa D-05 (sotto) e collegamento anomalia seed → anomalia automatica.
3. `importers/batch.py` — orchestrazione `ImportBatch`: dry-run, apply, rollback.
4. `imports/management/commands/import_seed.py` — CLI con `--dry-run`.
5. API: `POST /imports` (upload + dry-run), `/imports/{id}/apply`, `/imports/{id}/rollback`,
   `GET /imports`, `GET /review-queue`.
6. Test: unitari sull'importer con una fixture demo anonimizzata + accettazione sul seed reale
   (marcati `@pytest.mark.seedfile`, già predisposti in `conftest.py`).

## Decisioni di progetto già prese (non ridiscuterle)

- **Dry-run e apply sono lo stesso codice.** Si esegue dentro `transaction.atomic()` e, se è
  una simulazione, si solleva un'eccezione sentinella per annullare tutto. Così il diff
  mostrato è per costruzione quello che l'applicazione farebbe, non una stima.
- **Due letture del JSON.** `jsonschema` riconosce come `number` solo int e float: un
  `Decimal` fallirebbe la validazione. Quindi si valida la lettura con i float e si importa
  da quella con i `Decimal` (già implementato in `schema.py`).
- **Consuntivi a zero: nessuna riga.** Il vincolo `timesheet_days_not_zero` vieta le righe a
  0 gg, quindi `gg_consumati_su_progetto = 0` non genera nulla.
- **Consuntivi append-only anche in reimport.** Se esiste già una riga `SEED_INIZIALE` per
  quel bersaglio e quel periodo, non si tocca. Se il file nel frattempo riporta un valore
  diverso, si scrive un **avviso** nel report ("differenza non applicata, usare un import
  PPM") invece di divergere in silenzio. Il trigger `timesheets_append_only` rende questa
  non una scelta di stile ma l'unica strada.
- **Il rollback del batch** deve usare `timesheets.mutations.allow_ledger_mutation(motivazione)`:
  è la sola finestra che il trigger concede (D-14).
- **I progetti `CHIUSO` senza data** passano solo perché il check constraint ammette
  l'eccezione quando `import_batch` è valorizzato: l'importer deve quindi impostare il batch
  su ogni record creato (serve comunque al rollback).
- **Niente `full_clean()` sui record importati**: i dati entrano come sono e le incoerenze
  diventano anomalie, altrimenti metà del seed verrebbe rifiutata.

## Chiavi naturali per l'idempotenza

| Entità | Chiave |
|---|---|
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

## Mappa di sostituzione D-05 (analisi già svolta sulle 11 anomalie del seed)

Sette anomalie manuali sono coperte da una regola automatica e andranno chiuse come
"sostituite" quando il motore controlli (Fase 4) le rileva; quattro restano aperte perché
descrivono incoerenze dell'Excel che la webapp elimina per costruzione, e vanno chiuse a mano.

| Seed | Regola automatica | Entità attesa |
|---|---|---|
| AN-003 | `CHK_RESIDUAL_UNALLOCATED_CLOSED` | qualunque istanza |
| AN-004 | `CHK_OVERRUN_PROJECT` | IM26292 (OSB14 POC: 24,8 su 17) |
| AN-005 | `CHK_DOUBLE_COUNT` | RM-300228 / RM-300229 |
| AN-006 | `CHK_MISSING_IN_PPM` | IM25379 |
| AN-007 | `CHK_RECON_DELTA` | qualunque istanza (elenca 7 progetti) |
| AN-008 | `CHK_CANONE_UNDERUSE` | canone IM26179 (2026-S2) |
| AN-009 | `CHK_DATE_ORDER` | qualunque istanza |
| AN-001, AN-002 | nessuna | totali wallet incoerenti fra fogli: risolti dal ricalcolo |
| AN-010, AN-011 | nessuna | divergenze fra i fogli Progetti e Capacity, riga duplicata |

## Criteri di accettazione da verificare al checkpoint

Import del seed reale: **40** progetti, **2** canoni, **48** sotto-attività, **21** attività
wallet, **24** allocazioni (wallet 2026), **1** snapshot con **11** righe, **11** anomalie
seed, **16** persone, **54** milestone. Più, a parte: **6** allocazioni tecniche `STORICO-*`
nel wallet 2025, con **3 scarti motivati** (IM25270 a zero; IM25151 e IM25236 perché
duplicano W26-012 e W26-005, vedi D-04).

Secondo import dello stesso file: **0 creazioni e 0 modifiche**.

Da mostrare al checkpoint, come concordato: tabella dei conteggi per entità e report completo
del dry-run.
