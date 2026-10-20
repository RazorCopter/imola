# Supplier Ledger — piano di implementazione

## Context

L'ufficio Architetture IT di Banca Mediolanum (BMED) gestisce il rapporto con Imola
Informatica su un Excel condiviso multi-foglio. Quell'Excel non è affidabile: totali
calcolati male, stato progetto mescolato con stato fattura, date/budget/referenti incoerenti
tra fogli, giornate potenzialmente contate due volte.

Serve una webapp production-ready che diventi la fonte di verità per **pianificazione,
allocazioni wallet e regole**, mentre il PPM di Imola resta la fonte di verità per i
**consuntivi** (importati periodicamente e riconciliati). Esiti attesi: residui e wallet
sempre derivati da formula unica (R3), stato consuntivazione separato da stato fatturazione
(R1), scadenza residui governata (R2), anomalie rilevate automaticamente, export Excel pulito
da dare a Imola in sostituzione del vecchio file.

Bootstrap dati da `seed_imola_2026-10-16.json` (validato contro `seed_schema_v1.json`).
Deploy finale su Synology Container Manager.

**Decisioni già prese con l'utente**
- Repo in `C:\dev\supplier-ledger` (fuori da OneDrive, per npm/docker). I due file seed
  vengono **copiati** in `data/seed/`; gli originali restano in `Documenti\Progetti\ImolaManager`.
- **Checkpoint a fine Fase 1 e a fine Fase 2**: mi fermo e ti mostro esito dei test, conteggi
  per entità e report completo del dry-run prima di proseguire. Dalla Fase 3 alla 6 procedo
  senza fermarmi.
- Il seed reale **non** va in git (`.gitignore`): nel repo solo `seed_schema_v1.json` e una
  fixture demo anonimizzata. I test di accettazione §10/§11 sul file reale sono marcati
  `@pytest.mark.seedfile` e si skippano se il file non c'è.

---

## Cosa dicono i dati reali del seed (verificato)

Conteggi: 16 persone · 40 progetti · 2 canoni · 48 sottoattività (25 in S1, 23 in S2) ·
54 milestone · 21 attività wallet · 24 allocazioni · 1 snapshot PPM_WALLET (11 righe) ·
11 anomalie. Somme: budget 933 · consumato diretto 574,305 · allocato 130,89 · consumato
wallet 120,79 → **disponibile 10,10** (test §11.4 ✔) · canone S1 177,40 / S2 100,27 (test §11.7 ✔).

Tre contraddizioni spec↔dati, risolte così (tutte annotate in `docs/DECISIONI_APERTE.md`):

| # | Problema | Risoluzione conservativa |
|---|---|---|
| 1 | §11.1 pretende `CHK_OVERRUN_PROJECT` su IM24133, ma il consumato interno è esattamente 85 su budget 85 (non >) — lo sforamento esiste solo nel PPM (86,5) | La regola valuta `max(consumato_interno, gg_totali ultimo snapshot PPM)`, coerente con R6 (PPM = fonte dei consuntivi). Severità dal rapporto: 86,5/85 = +1,8% → MEDIA; IM26292 24,8/17 = +45,9% → ALTA (§11.8 ✔). Il messaggio dice sempre da quale fonte arriva lo sforamento. |
| 2 | 4 progetti `CHIUSO` ma solo 1 ha `data_chiusura_consuntivazione`; 3 hanno solo `anno_riferimento_residuo=2026` | Import crea i 3 progetti chiusi + anomalia `CHK_CLOSED_NO_DATE` (ALTA). `residual_reference_year` resta **null** (è readonly, derivato dalla data); l'anno dichiarato va in `declared_residual_year` solo per display. Senza data la scadenza non è calcolabile → stato residuo `DA_VERIFICARE`, **escluso** dal disponibile ufficiale e contato nel KPI "residui potenziali da verificare". Si sblocca dalla coda di revisione inserendo la data. |
| 3 | `gg_wallet_storico_gia_usati` esiste su 9 progetti (tutti `DA_VERIFICARE`), uno vale 0 e due duplicano allocazioni 2026 già presenti; le allocazioni tecniche `STORICO-*` andrebbero in un wallet anno precedente che non esiste nel seed | Creo `WalletYear 2025` + **6** attività/allocazioni tecniche `STORICO-<codice>` (CHIUSA, DA_VERIFICARE). Escluse: IM25270 (valore 0) e — per decisione dell'utente — **IM25151 (5 gg) e IM25236 (2,06 gg), che duplicano le allocazioni W26-012 e W26-005**. I due valori ignorati sono elencati nel report del batch come "scartati: duplicato di <id_import>". Le STORICO sono contate a parte, così i numeri di accettazione §10 (21/24) restano quelli del wallet 2026. |

Altri dettagli che il codice deve gestire: `persone[].email` è **sempre null** → match persone
solo per nome normalizzato; `snapshot_ppm[].data_estrazione` è datetime ISO mentre tutte le
altre date sono `YYYY-MM-DD`; un progetto ha codice fuori pattern (`PPM-144659-ASSET-SEDE-E-RETE`);
5 righe snapshot hanno `gg_residui` negativo; 3 allocazioni sono già in sforamento; 4 hanno
`gg_allocati = 0` (una è IM26254, test §11.5); `#300228` compare in sottoattività canone S2,
attività wallet `RM-300228` e allocazione W26-019 → `CHK_DOUBLE_COUNT` (test §11.6);
1 allocazione (W26-008) senza progetto di origine → `CHK_ALLOC_NO_SOURCE`.

---

## Architettura

Monorepo, tre container applicativi + db, nessun Celery in v1 (gli import sono piccoli:
seed 84 KB, estratti PPM poche centinaia di righe → transazione sincrona con cap di
dimensione; annotato in DECISIONI_APERTE).

```
supplier-ledger/
├─ backend/                 Python 3.12 · Django 5 · DRF · PostgreSQL 16
│  ├─ config/               settings/{base,dev,prod}.py, urls, wsgi
│  ├─ core/                 base model (UUID, timestamps, created_by, version, history),
│  │                        Settings singleton, auth providers, permessi, problem+json handler
│  ├─ directory/            Organization, Person (+ normalizzazione nomi)
│  ├─ projects/             Project, BillingMilestone
│  ├─ canone/               Canone, CanoneSubactivity
│  ├─ wallet/               WalletYear, WalletActivity, WalletAllocation
│  ├─ timesheets/           TimesheetEntry (append-only, solo storni)
│  ├─ ppm/                  PpmSnapshot, PpmSnapshotRow, ImportProfile
│  ├─ anomalies/            Anomaly
│  ├─ domain/               ⚠ logica pura, coverage ≥85%
│  │   ├─ money.py          Decimal(8,4), quantize, parsing da stringa
│  │   ├─ residuals.py      R2 (scadenza) + R3 (residuo progetto)
│  │   ├─ wallet_balance.py R3 (disponibile anno)
│  │   ├─ canone_status.py  R4 (target, delta, forecast)
│  │   ├─ reconciliation.py R6 (delta vs ultimo snapshot, tolleranza)
│  │   └─ checks/           una regola per file + registry + runner (fingerprint/dedup)
│  ├─ importers/            ⚠ coverage ≥85%: seed_json.py, ppm_xlsx.py, ppm_pdf.py,
│  │                        legacy_excel.py, batch.py (dry-run / apply / rollback)
│  ├─ exports/              excel.py, csv.py, seed_json.py
│  ├─ api/v1/               router, serializer, filtri, ETag/If-Match, OpenAPI
│  └─ tests/                unit, integration, acceptance (§11)
├─ frontend/                React 18 · TS · Vite · Tailwind · shadcn/ui · TanStack
├─ deploy/                  nginx.conf, Dockerfile.*, synology/ (cron backup, README)
├─ docs/                    PLAN.md, DECISIONI_APERTE.md, MANUALE.md, CHANGELOG.md
├─ data/seed/               (gitignored) seed reale
└─ docker-compose.yml + docker-compose.override.yml + .env.example + Makefile
```

**Scelte tecniche portanti**

- **Formula unica.** Le formule R2/R3/R4/R6 esistono **una sola volta**, come builder di
  annotazioni ORM in `domain/` (`project_balance_qs()`, `wallet_year_balance()`,
  `canone_status()`, `reconciliation_qs()`), con `Coalesce(Sum(...), Decimal("0"))` e
  `output_field=DecimalField(max_digits=12, decimal_places=4)`. Niente duplicazione in SQL:
  le "viste calcolate" del §3.2 sono questi builder, esposti da API e usati dagli export.
  Nessun totale è mai una colonna scrivibile.
- **Decimal end-to-end.** JSON letto con `json.load(..., parse_float=Decimal)`, numeri Excel
  convertiti via `str()`, mai `float`. Arrotondamento `ROUND_HALF_UP` a 4 decimali in scrittura,
  a 2 solo in UI/export.
- **Append-only contabile.** `TimesheetEntry` senza update/delete: una correzione è una entry
  di storno con `reverses`. Check constraint: esattamente uno fra `project`,
  `canone_subactivity`, `wallet_allocation`.
- **Audit.** `django-simple-history` su tutte le entità + middleware che popola
  `created_by`/`updated_by`; tab "Storico modifiche" per entità.
- **Concorrenza.** Campo `version` su entità modificabili, `ETag` in GET e `If-Match`
  obbligatorio in PATCH → `412`/`428` in problem+json italiano.
- **Checks idempotenti.** `fingerprint = sha256(rule_code + ref entità)` — **senza** i valori,
  così un valore che cambia aggiorna la descrizione invece di creare un duplicato. Il runner
  fa diff: nuove → create; non più rilevate → RISOLTA automatica con nota; `ACCETTATA` con
  deroga → rispettata fino alla scadenza della deroga.
- **Anomalie seed sostituite dalle regole.** Quando una regola automatica rileva la stessa
  situazione di un'anomalia `SEED_MANUALE`, le due vengono collegate (`supersedes` /
  `superseded_by`) e quella seed passa a RISOLTA con nota "sostituita da `<rule_code>`
  (anomalia <id>)", restando navigabile dall'anomalia automatica. Il riconoscimento usa una
  mappa dichiarativa in `importers/seed_json.py` (`AN-001…AN-011` → `rule_code` + entità
  attesa, ricavata da `ambito` + `codice_progetto`), perché le descrizioni seed sono prosa e
  non sono matchabili in modo affidabile. Le anomalie seed non mappabili restano aperte e la
  coda di revisione offre l'azione "collega e chiudi come sostituita" manuale.
- **Import a 3 stadi.** validate → dry-run (diff per entità: crea/aggiorna/invariato/errore)
  → apply in **una** transazione, con `import_batch` FK su ogni record creato per rollback
  completo del batch. Idempotenza sulle chiavi naturali del §5.1 (`external_ref` per le
  allocazioni). Secondo import dello stesso file → 0 creazioni.
- **Sessione scaduta.** Nessun interceptor che fa logout: il 401 con
  `code=session_expired` alza un flag globale → modale di re-login che **ritenta** la
  richiesta fallita conservando il form in corso.

---

## Modello dati

Come §3, senza scostamenti, con queste aggiunte minime:

| Entità | Aggiunte rispetto al §3 |
|---|---|
| `core.Settings` | singleton: `hours_per_day`, `ppm_granularity_days`, `reconciliation_tolerance_days`, `residual_years_after_closure` |
| `Project` | `declared_residual_year` (da `anno_riferimento_residuo`, readonly/display), `external_ref`, `import_batch`, `version` |
| `WalletAllocation` | `external_ref` (= `id_import`), `requires_source_attribution`, `override_reason` + `override_by` (sforamento residuo autorizzato da Admin) |
| `Anomaly` | `accepted_until` (scadenza della deroga), `fingerprint` unique, `superseded_by` FK self (anomalia seed chiusa perché coperta da una regola automatica) |
| `ImportProfile` (ppm) | mapping colonne configurabile da UI, versionato |

Vincoli DB come da §3.1 (`planned_end_date >= start_date`, `budget_days >= 0`,
`actual_closure_date NOT NULL` se `timesheet_status=CHIUSO`), più `allocated_days >= 0`,
`days != 0` su TimesheetEntry, unique `(full_name, organization)`, unique `Project.code`,
unique `WalletActivity.code`, unique `(canone, semester)`.

---

## API (`/api/v1/`)

CRUD con paginazione cursor, `django-filter`, ordinamenti, ETag/If-Match su:
`projects`, `projects/{id}/milestones`, `people`, `canoni`, `canoni/{id}/subactivities`,
`wallet/years`, `wallet/activities`, `wallet/allocations`, `timesheet-entries`
(POST/storno), `anomalies`, `imports`, `ppm/snapshots`, `import-profiles`, `settings`, `users`.

Endpoint di dominio:

| Metodo | Path | Nota |
|---|---|---|
| POST | `/projects/{id}/close` | data obbligatoria, restituisce anteprima residuo + scadenza |
| PATCH | `/projects/{id}/billing-status` | indipendente da consuntivazione (R1) |
| POST | `/projects/{id}/milestones/{mid}/move` | motivazione obbligatoria |
| GET | `/projects/{id}/balance` · `/projects/balances` | R3 |
| GET | `/wallet/{year}/balance` · `/wallet/{year}/flow` | R3 + dati Sankey |
| POST | `/wallet/allocations` · `/{id}/close` · `/{id}/reassign` | blocco >residuo, override Admin |
| GET | `/canoni/{id}/status` | R4, con breakdown della formula per il tooltip |
| GET | `/reconciliation/latest` · `/reconciliation/{snapshot}` | R6 |
| POST | `/checks/run` → GET `/anomalies` | + `/anomalies/{id}/{take,resolve,accept}` |
| GET | `/review-queue` | §6.7 unificata |
| POST | `/imports` (upload+dry-run) · `/{id}/apply` · `/{id}/rollback` | Imola resta in DRY_RUN |
| GET | `/export/excel` · `/export/json` · `/export/csv/{entity}` | |
| GET | `/health`, `/api/docs` (solo Admin) | |

Errori RFC 7807 in italiano con `type` stabile (es. `/errors/residuo-insufficiente`) e campo
`errors[]` per i problemi di validazione.

---

## Schermate

Dashboard (KPI §6.1 + 4 grafici + box "Cosa fare ora") · Progetti (tabella virtualizzata,
filtri salvabili, dettaglio a 8 tab, wizard nuovo progetto) · Wallet (Sankey origine→attività,
tabella allocazioni, pannello residui per validità, nuova allocazione con origini **ordinate
per scadenza crescente**) · Canone (selettore semestre, burn-down, tabella per ufficio con
subtotali ed editing inline di stima/forecast) · Riconciliazione PPM · Anomalie (inbox) ·
Coda di revisione · Amministrazione

Nella **coda di revisione**, per i progetti `CHIUSO` senza data di chiusura il campo è
**precompilato con `data_fine_prevista`** (evidenziato come proposta, con l'origine del dato
visibile) e si conferma con un clic; la data resta modificabile e, se anche
`data_fine_prevista` è nulla, il campo è vuoto e obbligatorio. La conferma ricalcola residuo
e scadenza e chiude l'anomalia `CHK_CLOSED_NO_DATE`. (import, batch+rollback, profili, impostazioni, utenti).

Design: sidebar collassabile, Command Palette `Ctrl/Cmd+K` (cmdk) su progetti/attività/anomalie/azioni,
dark+light con preferenza di sistema, palette zinc + accento indigo, verde/ambra/rosso semantici,
Inter + JetBrains Mono, `tabular-nums`, formato `1.234,56 gg`, densità tabella regolabile,
skeleton/empty state/toast, micro-animazioni 150–200 ms con `prefers-reduced-motion`,
**tooltip che mostra sempre il calcolo** (`25 − 10,50 − 11,00 = 3,50 gg`), WCAG 2.1 AA,
stringhe in `i18n/it.json` (+ `en.json` scheletro).

Ruoli (enforced in API, non solo UI): `admin`, `responsabile_bmed`, `referente_bmed`
(lettura + note/verifiche sui propri progetti, via object permission), `fornitore`
(lettura + upload PPM che resta DRY_RUN).

---

## Fasi

Ogni fase chiude con: test verdi, `docker compose up` funzionante, `docs/CHANGELOG.md` aggiornato.

**Fase 1 — Fondamenta.** Scaffolding backend+frontend, Docker Compose (db/backend/frontend/nginx,
porte non privilegiate, volumi bind, healthcheck, `.env.example`), auth sessione+CSRF con
astrazione OIDC inattiva, tutti i modelli e le migrazioni, admin Django, `domain/` completo
con R2/R3/R4/R6, pre-commit (ruff/black/mypy/eslint/prettier).
*Accettazione*: i casi §11.3 (15/11/2025 → valido al 31/12/2026, scaduto al 01/01/2027,
"in scadenza" al 02/10/2026), §11.4, §11.7 e §11.9 passano come test di dominio su fixture.
**Checkpoint**: ti mostro `make test` con il report di coverage e lo stack in esecuzione
prima di passare alla Fase 2.

**Fase 2 — Import seed.** Validazione JSON Schema, dry-run con diff, apply transazionale,
rollback, idempotenza, coda di revisione, `manage.py import_seed <file> [--dry-run]`.
*Accettazione*: l'import del seed reale crea 40 progetti, 2 canoni, 48 sottoattività,
21 attività wallet, 24 allocazioni (2026), 1 snapshot con 11 righe, 11 anomalie seed, 16 persone;
le allocazioni tecniche `STORICO-*` (6, wallet 2025) sono riportate a parte con i 3 valori
scartati motivati; il secondo import produce 0 creazioni e 0 modifiche.
**Checkpoint**: ti mostro output dei test, tabella dei conteggi per entità e il report
completo del dry-run prima di passare alla Fase 3.

**Fase 3 — UI core.** Design system, layout, command palette, dashboard, progetti (lista+dettaglio),
wallet, canone, i18n, modale sessione scaduta.

**Fase 4 — Controlli e riconciliazione.** Le 18 regole del §4 con test positivi/negativi,
runner + dedup, `manage.py run_checks`, inbox anomalie, schermata riconciliazione.
*Accettazione*: sul seed reale scattano `CHK_OVERRUN_PROJECT` su IM24133 (MEDIA, da PPM) e
IM26292 (ALTA), `CHK_MISSING_IN_PPM` su IM25379, `CHK_DOUBLE_COUNT` su RM-300228,
`CHK_ALLOC_NO_SOURCE` su W26-008, `CHK_CLOSED_NO_DATE` ×3; IM25138 riconcilia OK (delta 0,0025).

**Fase 5 — Import PPM ed export.** Parser Excel tollerante (header cercato nelle prime 15 righe,
data via regex, riga totali usata per quadratura ±0,01), match codice normalizzato
(ignora il segmento `BMED-`), righe non riconosciute con azione associa/crea, aggiornamento
consuntivi **a differenza** (delta negativo → storno), PPM_CANONE con sottoattività nuove in
coda di revisione, profili di import, PDF via `pdfplumber` con messaggio chiaro al fallimento,
export Excel multi-foglio/CSV/JSON (schema 1.0.0).
*Accettazione*: §11.10 — reimport dello stesso estratto → 0 nuove TimesheetEntry.

**Fase 6 — Hardening.** Ruoli e permessi object-level, audit UI, 5 flussi E2E Playwright
(login→dashboard; import seed dry-run→apply; chiusura progetto con anteprima scadenza;
nuova allocazione wallet; risoluzione anomalia), performance (lista 500 progetti < 300 ms API,
con test di carico e indici), sicurezza §9 (cookie Secure/HttpOnly/SameSite, whitelist upload,
rate limit login, log JSON), `manage.py backup` + cron Synology, `docs/MANUALE.md` con
screenshot generati da Playwright.

---

## Verifica end-to-end

```bash
cp .env.example .env && make up          # db+backend+frontend+nginx, http://localhost:8080
make migrate && make superuser
make seed                                # import_seed data/seed/seed_imola_2026-10-16.json
make test                                # pytest + vitest; gate coverage 85% su domain/ e importers/
make e2e                                 # Playwright, 5 flussi
```

Controlli manuali attesi: dashboard mostra wallet disponibile **10,10 gg**, canone S2
100,27/102,35 con delta **+2,08**, 11+ anomalie aperte e i residui potenziali da verificare
separati; `/api/v1/reconciliation/latest` mostra IM24133 a −1,5 e IM25138 entro tolleranza;
`make seed` eseguito due volte non crea duplicati; export Excel apribile con i 5 fogli.
