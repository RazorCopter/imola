# Audit indipendente — Supplier Ledger, Blocco 0

**Data:** 2026-10-22 · **Tipo:** read-only, secondo audit indipendente  
**Scope:** production readiness, architettura, integrità dati, sicurezza, operatività, colli di bottiglia verso MVP

---

## 0. Convenzioni

| Simbolo | Significato |
|---------|-------------|
| **FATTO** | Evidenza osservabile nel workspace (codice, test, configurazione) |
| **INFERENZA** | Conclusione ragionevole ma non verificata direttamente (es. comportamento runtime) |
| 🔴 | Rischio **CRITICO** — blocca la production readiness |
| 🟠 | Rischio **ALTO** — degrada significativamente la fiducia |
| 🟡 | Rischio **MEDIO** — da risolvere prima o poco dopo il go-live |
| 🟢 | Punto di forza osservato |

---

## 1. Stato reale dei test — sfida al numero "293 + 30"

### 1.1 Il numero è fuorviante

**FATTO:** 293 test backend passano. Analizzando i file di test:

| File | Test (stima) | Cosa coprono realmente |
|------|-------------|----------------------|
| [`test_models.py`](backend/tests/test_models.py) | ~35 | Vincoli modello, tracciatura, validazione campi |
| [`test_phase2_refinements.py`](backend/tests/test_phase2_refinements.py) | ~30 | Raffinamenti dominio Fase 2 |
| [`test_phase3_api.py`](backend/tests/test_phase3_api.py) | ~15 | API canone, creazione progetti, permessi base |
| [`test_phase4_checks.py`](backend/tests/test_phase4_checks.py) | ~40 | 18 regole del motore anomalie |
| [`test_phase5.py`](backend/tests/test_phase5.py) | ~25 | Import/export PPM, CSV, Excel, JSON |
| [`test_api_auth.py`](backend/tests/test_api_auth.py) | ~25 | Sessione, 401/403, problem+json, CSRF |
| [`test_roles_object_permissions.py`](backend/tests/test_roles_object_permissions.py) | ~20 | RBAC per tutti e 4 i ruoli |
| [`test_review_queue.py`](backend/tests/test_review_queue.py) | ~15 | Coda di revisione D-03 |
| [`test_append_only.py`](backend/tests/test_append_only.py) | ~12 | Append-only modello + trigger DB |
| [`test_seedfile_acceptance.py`](backend/tests/test_seedfile_acceptance.py) | ~15 | Accettazione seed reale (skip senza file) |
| [`test_performance.py`](backend/tests/test_performance.py) | 1 | Benchmark 500 progetti < 300 ms |
| [`test_d14_seed_exceptions.py`](backend/tests/test_d14_seed_exceptions.py) | ~10 | Eccezioni D-14 seed |
| Sotto `backend/tests/domain/` | ~50+ | Logica residui, wallet, riconciliazione, canone |

**FATTO:** 30 test frontend passano. Analizzando i file:
- [`format.test.ts`](frontend/src/lib/__tests__/format.test.ts) — formattazione numerica
- [`permissions.test.ts`](frontend/src/lib/__tests__/permissions.test.ts) — utility permessi
- [`presentation.test.tsx`](frontend/src/components/__tests__/presentation.test.tsx) — componenti presentazionali
- [`ReconciliationPage.test.tsx`](frontend/src/features/reconciliation/__tests__/ReconciliationPage.test.tsx) — semantica riconciliazione
- [`WalletPage.test.tsx`](frontend/src/features/wallet/__tests__/WalletPage.test.tsx) — wallet UI
- [`role_permissions_ui.test.tsx`](frontend/src/features/auth/__tests__/role_permissions_ui.test.tsx) — RBAC UI

### 1.2 Cosa manca nelle 293+30

🟠 **Nessun test di integrazione database reale per le migrazioni.** I test usano `pytest-django` con transazioni atomiche; **INFERENZA**: nessun test verifica che `makemigrations --check` sia pulito o che le migrazioni si applichino in sequenza corretta su un database vergine.

🟠 **I test seedfile vengono silenziosamente skippati** in CI/ambienti senza il file seed reale ([`conftest.py:26-35`](backend/conftest.py:26)). Questo significa che le ~15 asserzioni sui dati reali del fornitore (valori esatti come `"130.8900"` in [`test_seedfile_acceptance.py:40`](backend/tests/test_seedfile_acceptance.py:40)) non girano mai nell'ambiente di sviluppo standard.

🔴 **Zero capability a COMPLETA nella gap analysis.** Su 39 capability, 0 soddisfano la Definition of Done stretta (API + GUI + E2E reale + verifica manuale). Questo significa che il numero 293+30 **non prova che il sistema sia usabile end-to-end da un utente reale**.

🟠 **E2E non deterministici.** L'ultima suite reale ([`phase6.spec.ts`](frontend/e2e/phase6.spec.ts)) ha prodotto 5 passati, 1 fallito, 2 saltati. I test sono `serial` (riga 32): il fallimento del test 6 (revisione) ha a cascata impedito i test 7-8. **FATTO** osservabile: il test 6 cerca un elemento nella coda di revisione che dipende dallo stato mutato dai test precedenti.

---

## 2. Architettura — punti di forza e rischi strutturali

### 2.1 Punti di forza 🟢

| # | Evidenza |
|---|---------|
| A | **Separazione domain/API/modelli** pulita: i calcoli sono in [`domain/`](backend/domain/) (residuals, wallet_balance, checks, canone_status, reconciliation), le view in [`api/domain_views.py`](backend/api/domain_views.py) non contengono logica di calcolo. |
| B | **Append-only sui consuntivi** con doppia protezione: modello ([`TimesheetEntry.save()`](backend/timesheets/models.py:34)) + trigger PostgreSQL + context manager [`allow_ledger_mutation()`](backend/timesheets/mutations.py:28) per il solo rollback seed. Test robusti in [`test_append_only.py`](backend/tests/test_append_only.py). |
| C | **Concorrenza ottimistica** implementata con ETag/If-Match in [`api/concurrency.py`](backend/api/concurrency.py). |
| D | **Tracciatura completa**: [`TrackedModel`](backend/core/models.py:22) con UUID, version, created_by/updated_by + `simple_history` su tutte le entità. |
| E | **Motore anomalie con fingerprint** stabile ([`build_fingerprint()`](backend/anomalies/models.py:43)) e supersessione D-05 nel [`runner.py`](backend/anomalies/runner.py). |
| F | **Problem+json RFC 7807** in italiano per tutti gli errori ([`core/exceptions.py`](backend/core/exceptions.py)). |

### 2.2 Rischi architetturali

🟠 **R1 — [`domain_views.py`](backend/api/domain_views.py) è un monolite da 753 righe.** Tutte le view di dominio (progetti, wallet, canone, anomalie, riconciliazione, import, export, review queue) sono in un singolo file. Nessun problema funzionale immediato, ma aumenta la probabilità di conflitti di merge e rende difficile la revisione incrementale.

🟡 **R2 — Nessun meccanismo di migrazione dati automatizzato per le evoluzioni schema.** Le migrazioni Django esistono, ma la migrazione [`0004_migrate_entity_ref_and_fingerprints.py`](backend/anomalies/migrations/0004_migrate_entity_ref_and_fingerprints.py) è l'unica data migration osservata. **INFERENZA**: eventuali cambiamenti ai dati seed richiedono operazioni manuali.

🟡 **R3 — `CurrentUserMiddleware` usa un thread-local** ([`core/middleware.py`](backend/core/middleware.py), [`core/current_user.py`](backend/core/current_user.py)). Funziona con gunicorn sync/gthread, ma **INFERENZA**: non è sicuro con worker async (uvicorn/ASGI). Il [`Dockerfile.backend`](deploy/Dockerfile.backend:39) usa gunicorn sync, quindi non è un problema oggi.

---

## 3. Integrità dati

### 3.1 Protezioni osservate 🟢

- **Check constraint** su [`TimesheetEntry`](backend/timesheets/models.py): esattamente uno fra `project`, `canone_subactivity`, `wallet_allocation` valorizzato.
- **Unique constraint** su `WalletYear.year`, `WalletActivity.code`, `Person` (normalizzazione in [`directory/normalization.py`](backend/directory/normalization.py)).
- **Singleton** per [`AppSettings`](backend/core/models.py:63) via `unique=True` su campo booleano.
- **Fingerprint SHA-256** per deduplica anomalie.
- **Content hash** su [`ImportBatch`](backend/imports/models.py:40) per idempotenza import.

### 3.2 Rischi integrità

🔴 **I1 — Nessuna validazione manuale è stata eseguita.** [`MANUAL_VALIDATION_FASE7.md`](docs/MANUAL_VALIDATION_FASE7.md:10) dichiara esplicitamente: *"checklist predisposta ma **non eseguita**"*. Tutte le 30+ caselle sono `[ ]`. Questo significa che nessun essere umano ha mai verificato che i dati visualizzati nella GUI corrispondano ai valori del database.

🟠 **I2 — I valori del seed reale hardcoded nei test** ([`test_seedfile_acceptance.py:40-46`](backend/tests/test_seedfile_acceptance.py:40)) sono fragili: se il seed cambia, i test vanno aggiornati manualmente. **INFERENZA**: non esiste un meccanismo che rigenera le asserzioni dai dati.

🟡 **I3 — Il campo `MEDIA_ROOT`** riceve file importati (seed JSON, PPM Excel/PDF) in [`imports/%Y/%m/`](backend/imports/models.py:38). **FATTO**: nginx serve `/media/` come `internal` ([`nginx.conf:50-53`](deploy/nginx.conf:50)), quindi i file non sono esposti direttamente. Ma **INFERENZA**: non c'è scansione malware né validazione del contenuto dei PDF caricati.

---

## 4. Sicurezza

### 4.1 Punti di forza 🟢

| # | Evidenza |
|---|---------|
| S1 | [`prod.py`](backend/config/settings/prod.py): HSTS 1 anno, cookie Secure/HttpOnly/SameSite, CSRF Secure, X-Frame-Options DENY, Content-Type nosniff, Referrer-Policy same-origin. |
| S2 | Password minima 12 caratteri con 4 validatori Django ([`base.py:86-94`](backend/config/settings/base.py:86)). |
| S3 | Rate limiting sul login: [`LoginRateThrottle`](backend/core/throttles.py:4) con scope `login`. |
| S4 | RBAC con 4 ruoli testati ([`test_roles_object_permissions.py`](backend/tests/test_roles_object_permissions.py)). Fornitore e referente non possono mutare il ledger. |
| S5 | Media serviti come `internal` da nginx — accesso solo tramite backend Django. |
| S6 | `SECRET_KEY` obbligatorio in produzione ([`prod.py:8`](backend/config/settings/prod.py:8) con `required=True`). |

### 4.2 Rischi sicurezza

🟠 **S7 — `CORS_ALLOWED_ORIGINS` è vuoto in produzione** ([`prod.py:27`](backend/config/settings/prod.py:27): `CORS_ALLOWED_ORIGINS: list[str] = []`). Con la lista vuota e senza `CORS_ALLOW_ALL_ORIGINS = True`, le richieste cross-origin saranno rifiutate. **INFERENZA**: o il frontend è servito dallo stesso dominio (tramite nginx, probabile dato il [`nginx.conf`](deploy/nginx.conf)) e non servono CORS, oppure c'è un bug di configurazione. Se il deploy avviene correttamente behind nginx, è corretto. Ma la mancanza di documentazione è un rischio operativo.

🟡 **S8 — Il default di `SECRET_KEY` in [`base.py:14`](backend/config/settings/base.py:14) è `"dev-only-insecure-key-change-me"`.** È protetto in prod da `required=True`, ma il default in base.py significa che un errore di configurazione (dimenticare `DJANGO_SETTINGS_MODULE=config.settings.prod`) avvierebbe il server con una chiave insicura. **INFERENZA**: il rischio è mitigato dal fatto che `docker-compose.yml:31` forza `config.settings.prod`.

🟡 **S9 — Nessuna Content Security Policy** osservata nelle configurazioni Django o nginx. **INFERENZA**: il frontend React potrebbe beneficiare di un CSP header per mitigare XSS.

🟡 **S10 — Upload: `ALLOWED_UPLOAD_EXTENSIONS`** definito in [`base.py:123`](backend/config/settings/base.py:123) (`.json`, `.xlsx`, `.pdf`) e in [`prod.py:26`](backend/config/settings/prod.py:26) (aggiunge `.csv`). **FATTO**: la validazione è dichiarata, ma non ho trovato evidenza nel codice che l'estensione venga effettivamente controllata negli endpoint di upload. **INFERENZA**: la setting potrebbe non essere applicata.

---

## 5. Operatività e deploy

### 5.1 Punti di forza 🟢

| # | Evidenza |
|---|---------|
| O1 | Healthcheck su tutti i servizi: PostgreSQL (`pg_isready`), backend (curl `/health` con check DB in [`core/views.py`](backend/core/views.py)), nginx (`/healthz`). |
| O2 | Backup automatizzato: [`manage.py backup`](backend/core/management/commands/backup.py) con pg_dump + tar media, rotazione configurabile (default 14). |
| O3 | Restore documentato: [`manage.py restore`](backend/core/management/commands/restore.py). |
| O4 | Logging strutturato JSON via `pythonjsonlogger` ([`base.py:173-189`](backend/config/settings/base.py:173)). |
| O5 | Docker multi-stage con utente non-root (`uid 10001`) e immagine slim ([`Dockerfile.backend`](deploy/Dockerfile.backend)). |
| O6 | Makefile con tutti i comandi operativi: `make up`, `make demo`, `make backup`, `make seed`, `make test` ([`Makefile`](Makefile)). |

### 5.2 Rischi operativi

🟠 **O7 — Nessun `collectstatic` nel Dockerfile o nell'entrypoint di produzione.** **FATTO**: il [`Dockerfile.backend`](deploy/Dockerfile.backend:29) non esegue `python manage.py collectstatic`. **INFERENZA**: il pannello Django Admin sarà privo di CSS/JS in produzione, e qualsiasi asset statico Django non sarà disponibile via nginx `/static/`.

🟠 **O8 — Nessun entrypoint di migrazione automatica in produzione.** **FATTO**: `docker-compose.override.yml:32` (dev) esegue `migrate --noinput` all'avvio, ma `docker-compose.yml` (prod) usa direttamente gunicorn senza migrare. **INFERENZA**: le migrazioni in produzione richiedono un comando manuale separato, non documentato nel README come procedura standard.

🟡 **O9 — Nessun monitoraggio o alerting.** Non ci sono configurazioni per Prometheus, Sentry, o simili. **INFERENZA**: in produzione, gli errori si vedranno solo nei log stdout del container.

🟡 **O10 — Assenza di CI/CD pipeline.** Non ci sono file `.github/workflows/`, `Jenkinsfile`, o equivalenti. **INFERENZA**: test, lint e deploy vengono eseguiti manualmente.

---

## 6. Colli di bottiglia verso MVP usabile

### 6.1 La piramide dei gap

**FATTO** dalla [gap analysis](docs/FUNCTIONAL_GAP_ANALYSIS.md):

| Stato | Conteggio | Significato |
|-------|-----------|-------------|
| COMPLETA | **0** | Nessuna capability soddisfa la DoD piena |
| PARZIALE | **22** | Backend ok, GUI presente, ma E2E reale o verifica manuale mancanti |
| SOLO BACKEND | **11** | API/CLI funzionanti, nessuna GUI |
| NON IMPLEMENTATA | **6** | Manca il percorso funzionale (FG-013, 014, 026, 033, 034, 035) |

### 6.2 I 6 non implementati

| ID | Capability | Impatto MVP |
|----|-----------|-------------|
| FG-013 | Assegnazione allocazione a persona/architetto | Basso se il workflow aziendale non lo richiede subito |
| FG-014 | Consumo per assegnatario | Basso, come sopra |
| FG-026 | Mappabilità Excel storico → seed | **ALTO** se è l'unica via per onboarding dati reali |
| FG-033 | Notifiche e avvisi di scadenza | Medio — impatta l'operatività quotidiana |
| FG-034 | Preferenze utente/personalizzazione | Basso |
| FG-035 | Multi-tenant / separazione mandati | Basso se è un singolo mandato |

### 6.3 Gli 11 SOLO BACKEND

Tutti import/export e operazioni amministrative CLI-only: seed import/rollback, PPM import/rollback, export Excel/CSV/JSON, rilascio residuo al wallet, validazione schema, audit trail. Un utente non tecnico **non può** eseguire queste operazioni senza accesso alla shell Docker.

---

## 7. Le 7 azioni che aumenterebbero davvero la fiducia

Ordinate per impatto sulla production readiness, non per facilità.

### Azione 1 🔴 — Eseguire la validazione manuale con utenti demo

**Perché:** Con 0 su 39 capability COMPLETE e la checklist in [`MANUAL_VALIDATION_FASE7.md`](docs/MANUAL_VALIDATION_FASE7.md) interamente vuota, oggi non c'è **nessuna prova** che un utente reale possa completare un flusso end-to-end. Nessun numero di test automatici sostituisce questa evidenza.

**Cosa:** Avviare lo stack con `make up && make demo`, accedere con ciascuno dei 4 utenti demo e completare ogni casella della checklist. Documentare screenshot e anomalie.

**Criterio:** Tutte le caselle `[x]` o issue aperte con motivazione.

### Azione 2 🔴 — Stabilizzare e isolare gli E2E

**Perché:** La suite [`phase6.spec.ts`](frontend/e2e/phase6.spec.ts) è `serial` e non idempotente: il fallimento del test 6 impedisce i test 7-8. I test dipendono dallo stato lasciato dai test precedenti e dai dati demo specifici.

**Cosa:** (a) Ogni test deve avere un setup/fixture indipendente. (b) Rimuovere la dipendenza dall'ordine. (c) Rieseguire fino a 3 run consecutivi verdi.

**Criterio:** 3 esecuzioni consecutive con 100% pass rate.

### Azione 3 🟠 — Aggiungere `collectstatic` e migrazione automatica al deploy prod

**Perché:** Senza [`collectstatic`](deploy/Dockerfile.backend) nel Dockerfile prod, l'admin Django è inutilizzabile. Senza migrate nell'entrypoint, il deploy richiede un passo manuale non documentato.

**Cosa:** Nel [`Dockerfile.backend`](deploy/Dockerfile.backend:29) target `prod`, aggiungere `RUN python manage.py collectstatic --noinput`. Nel [`docker-compose.yml`](docker-compose.yml) backend command, prefilare la migrazione prima di gunicorn (es. `sh -c "python manage.py migrate --noinput && gunicorn ..."`).

**Criterio:** `docker compose up` su un database vergine → admin Django con CSS → API funzionanti.

### Azione 4 🟠 — Implementare GUI minima per import seed e PPM

**Perché:** 11 capability SOLO BACKEND significano che l'utente Responsabile BMED deve avere accesso alla shell Docker per operazioni quotidiane come l'import PPM. Questo impedisce l'adozione come MVP.

**Cosa:** Implementare almeno la GUI di upload/dry-run/apply per seed (FG-023) e PPM (FG-027), con report e feedback. Le API backend esistono già.

**Criterio:** Un utente con ruolo `responsabile_bmed` può importare un file PPM dal browser senza accesso alla console.

### Azione 5 🟠 — Verificare l'applicazione effettiva di `ALLOWED_UPLOAD_EXTENSIONS`

**Perché:** La setting è dichiarata ([`base.py:123`](backend/config/settings/base.py:123)) ma non ho trovato evidenza che sia controllata nel codice degli endpoint di upload. Un attaccante potrebbe caricare file arbitrari.

**Cosa:** (a) Cercare nel codice l'uso di `ALLOWED_UPLOAD_EXTENSIONS`. (b) Se assente, aggiungere validazione nell'endpoint di upload PPM/seed. (c) Aggiungere test che verifica il rifiuto di `.exe`, `.py`, etc.

**Criterio:** Test che un upload di file `.exe` restituisce 400/413.

### Azione 6 🟡 — Aggiungere CI pipeline minima

**Perché:** Senza CI, la regressione è rilevata solo dall'attenzione del singolo sviluppatore. I 293 test backend perdono valore se non girano ad ogni push.

**Cosa:** Creare un workflow GitHub Actions (o equivalente) che esegue: `make test-backend`, `make test-frontend`, `make lint`, `make e2e` (con stack Docker).

**Criterio:** Badge verde su ogni PR.

### Azione 7 🟡 — Documentare la procedura di deploy e primo avvio

**Perché:** Il [`README.md`](README.md), il [`Makefile`](Makefile) e i vari `docker-compose*.yml` coprono lo sviluppo locale, ma non c'è una guida "da zero a produzione" che copra: configurazione `.env`, primo avvio, migrazione, creazione superuser, import seed, backup cron, monitoraggio.

**Cosa:** Scrivere `docs/DEPLOY_GUIDE.md` con checklist operativa.

**Criterio:** Un operatore può fare il primo deploy seguendo solo la guida.

---

## 8. Riepilogo rischi per livello

| Livello | ID | Sintesi |
|---------|-----|---------|
| 🔴 CRITICO | I1 | Validazione manuale mai eseguita (0/39 capability COMPLETE) |
| 🔴 CRITICO | E2E | Suite E2E non deterministica, copre solo 8 scenari di cui 3 non riproducibili |
| 🟠 ALTO | O7 | `collectstatic` assente nel Dockerfile prod |
| 🟠 ALTO | O8 | Nessuna migrazione automatica in prod entrypoint |
| 🟠 ALTO | S10 | Validazione estensioni upload potenzialmente non applicata |
| 🟠 ALTO | I2 | Test seedfile skippati silenziosamente senza seed reale |
| 🟠 ALTO | R1 | `domain_views.py` monolite 753 righe |
| 🟠 ALTO | GAP | 11 capability SOLO BACKEND, 6 NON IMPLEMENTATE |
| 🟡 MEDIO | O9 | Nessun monitoraggio/alerting |
| 🟡 MEDIO | O10 | Nessun CI/CD |
| 🟡 MEDIO | S8 | SECRET_KEY default insicuro in base.py |
| 🟡 MEDIO | S9 | Nessuna CSP header |
| 🟡 MEDIO | R3 | Thread-local non ASGI-safe (non bloccante oggi) |

---

## 9. Conclusione

Il progetto Supplier Ledger Blocco 0 ha un'architettura backend solida (separazione domain/API, append-only, RBAC, concurrency control, audit trail) e una buona copertura di test unitari e di dominio. Ma la **fiducia nella production readiness è bassa** per tre ragioni concrete:

1. **Nessuna validazione umana end-to-end è mai avvenuta** — i 293+30 test automatici provano che le funzioni individuali funzionano in isolamento, non che un utente possa completare un compito.

2. **L'unica suite E2E reale è instabile e non idempotente** — copre 8 scenari ma ne riproduce stabilmente solo 5, con fallimenti a cascata.

3. **17 delle 39 capability non hanno GUI** — un utente non tecnico può solo consultare, non operare.

Le 7 azioni elencate nella sezione 7 sono il percorso minimo per trasformare Blocco 0 da "backend funzionante con frontend incompleto" a "MVP realmente usabile".
