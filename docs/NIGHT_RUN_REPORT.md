# NIGHT RUN REPORT — Fase 7

Fine esecuzione: 2026-10-23T02:07:01+02:00
Branch: `fase7/night-run`
Tag iniziale: `pre-night-run` → `fb61b7c`

## 1. Esito N0 — Forense Git

Il lavoro del Blocco 0 non era perso: era presente integralmente nel working tree non committato. Non esistevano stash, branch alternativi o commit irraggiungibili successivi a `fb61b7c`. Tutti i sei artefatti richiesti erano presenti. Il lavoro è stato preservato, verificato e integrato sul branch dedicato.

## 2. Stato blocchi

| Blocco | Stato | Commit | Capability principali |
|---|---|---|---|
| N0 | CHIUSO | incluso in `c5f3158` | forense e recupero Blocco 0 |
| N1 | CHIUSO | `c5f3158` | baseline, pulizia, permessi, flussi recuperati |
| N2 | CHIUSO | `2bab0a8` | FG-013, FG-014 |
| N3 | CHIUSO | `a011a06` | FG-023, FG-025, FG-027, FG-029/030/031, FG-038 |
| N4 | CHIUSO | `4bcb5b5` (evidenze) | revisione, progetto, riconciliazione, canone, FG-034, dashboard |
| N5 | CHIUSO/SALTATO secondo piano | `4bcb5b5` | capability backend valutate singolarmente |
| N6 | BLOCCATO — input mancante | `4bcb5b5` | FG-026 |
| N7 | SALTATO — non previsto dal piano | `4bcb5b5` | FG-037 |

## 3. Risultati verifiche

- `ruff check .`: 0 errori.
- `black --check .`: 149 file invariati nell'ultimo gate.
- `mypy .`: 0 errori su 98 file.
- Backend Docker: 294 passed, 0 failed, 0 error nell'ultimo gate; precedente gate coverage 92,31% contro soglia 85%.
- Seedfile nel container con mount read-only: 4 passed, 289 deselected.
- Vitest: 30 passed, 0 failed.
- TypeScript `tsc`: exit 0.
- ESLint + Prettier: exit 0.
- Build Vite: exit 0, 1737 moduli trasformati nell'ultimo gate.
- E2E reali: tre run consecutivi dopo N3, ciascuno 8 passed, 0 failed, 0 skipped (24 pass osservati). Test UI mock di Fase 3 non conteggiati.
- Stack finale: backend/frontend/db/nginx attivi; db e nginx healthy; dati demo caricati con `load_demo_data --run-checks` exit 0.

## 4. Matrice FG prima/dopo

Baseline canonica letta: 0 COMPLETE, 22 PARZIALI, 11 SOLO BACKEND, 6 NON IMPLEMENTATE (39 capability).

Stato finale conservativo: nessuna riga promossa a COMPLETE, come imposto dalla specifica. Le righe FG-013/014, FG-023/025/027, FG-029/030/031 e FG-038 hanno nuove evidenze applicative, ma restano da riclassificare al massimo PARZIALI finché l'utente non esegue FG-039. La matrice non è stata alterata retroattivamente per evitare una certificazione non consentita.

## 5. Decisioni autonome

- Applicata Opzione A wallet; decisione D-17 marcata da confermare.
- Dati `.xlsx` non tracciati fuori da `data/seed/` trattati come aziendali e mai letti o committati.
- N6 bloccato perché in `data/seed/` non esiste alcun `.xlsx` storico.
- N7 saltato perché `PLAN.md` dichiara nessun Celery in v1.
- Rollback import e ledger timesheet non esposti come CRUD GUI perché non richiesti dal piano e potenzialmente contrari all'append-only.

## 6. Blocchi BLOCCATI

N6 soltanto: manca un input `.xlsx` storico nella directory autorizzata `data/seed/`. Nessun branch `wip/` creato perché non esiste lavoro parziale o non funzionante da preservare.

## 7. Migrazioni

- `wallet.0002_add_allocation_assignee`: aggiunge FK nullable `assignee` a tabella corrente e storica. Reversibile tramite migrazione Django inversa; applicata con successo.

## 8. Avvio stack e URL

```bash
make up
make migrate
make demo
```

- Applicazione nginx: http://localhost:8080
- Frontend sviluppo: http://localhost:5173
- API: http://localhost:8000/api/v1
- Swagger: http://localhost:8000/api/v1/docs

Lo stack è stato lasciato acceso con dati demo caricati.

## 9. Percorso di collaudo utente

Seguire `docs/MANUAL_VALIDATION_FASE7.md` in questo ordine:

1. login e permessi dei quattro utenti demo;
2. nuova allocazione wallet e vista residuo per architetto;
3. amministrazione: visibilità admin, dry-run seed/PPM con file sintetico, export e ruoli;
4. coda revisione e persistenza dopo reload;
5. progetto, riconciliazione e canone;
6. dashboard e navigazione filtrata per ruolo.

FG-039 resta intenzionalmente non eseguita: è riservata all'utente.

## 10. Git

```text
4bcb5b5 docs: registra chiusura blocchi funzionali fase 7
a011a06 feat: aggiunge amministrazione e import controllati
2bab0a8 feat: assegna allocazioni wallet agli architetti
c5f3158 fix: stabilizza baseline fase 7 e recupera blocco 0
```

Working tree applicativo pulito. Restano non tracciati, intenzionalmente non committati: il file `.xlsx` aziendale e due report audit preesistenti sotto `docs/`.

## Stato pubblicazione

Commit locali eseguiti sul branch `fase7/night-run`. Nessun push e nessun deploy, come richiesto.
