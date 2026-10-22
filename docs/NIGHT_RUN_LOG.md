# NIGHT RUN LOG — Fase 7

Inizio: 2026-10-23T01:35:53+02:00

## STATO BLOCCHI

### N0 — Forense Git — CHIUSO

- Stato iniziale osservato: branch `main`, HEAD `fb61b7c`, avanti di 29 commit rispetto a `origin/main`.
- Working tree non pulito: 28 file modificati e numerosi file non tracciati. Il contenuto corrisponde al checkpoint del Blocco 0 (loader demo, permessi GUI, documenti di analisi, test e flussi UI).
- Nessuno stash e nessun branch locale alternativo; log e reflog non mostrano commit successivi a `fb61b7c`.
- Tutti i sei artefatti richiesti dalla verifica N0 sono presenti nel working tree.
- Creato il tag locale `pre-night-run` su `fb61b7c` e creato/switchato il branch `fase7/night-run`, preservando integralmente il working tree.

### N1 — Baseline verde e pulizia — CHIUSO

- Obiettivo: integrare e verificare il lavoro recuperato del Blocco 0, applicare la pulizia richiesta e raggiungere tutti i gate verdi prima delle nuove feature.
- Pulizia applicata: rimosso loader duplicato `scripts/load_demo.py`; rimosso piano operativo temporaneo; rimosso da Git e ignorato `frontend/tsconfig.app.tsbuildinfo`; documentato che i test backend girano solo in Docker; target Makefile allineato al comando vincolante.
- Correzioni baseline: 10 errori ruff e 5 file black risolti; chiusura workbook PPM mantenuta; test E2E progetto reso indipendente dal numero/ordine delle righe tramite filtro utente reale.
- Il file `.xlsx` aziendale sotto `docs/` e il seed sotto `data/seed/` sono rimasti non tracciati e non modificati.
- Commit: `c5f3158 fix: stabilizza baseline fase 7 e recupera blocco 0`.

### N2 — Wallet: assegnazione e residuo per architetto — CHIUSO

- Implementata l'Opzione A per FG-013/FG-014: FK `assignee` nullable a `Person` per compatibilità storica; obbligatoria nell'API di creazione GUI.
- Dominio/API: flusso arricchito con architetto; aggregazione allocato/consumato/residuo per architetto; opzioni reali; creazione atomica con permessi e blocco oltre il residuo disponibile.
- GUI: form nuova allocazione per writer, selezione origine/attività/architetto, giornate e note; messaggio di errore; vista dei totali per architetto e architetto nel ledger.
- Migrazione `wallet.0002_add_allocation_assignee`: applicata con successo, reversibile (sola aggiunta campi nullable su tabella corrente e storica).
- Decisione D-17 annotata in `DECISIONI_APERTE.md` come provvisoria da confermare.
- Verifiche: test dominio wallet 15 passed; backend completo 294 passed; ruff 0; black 148 file puliti; mypy 97 file puliti; frontend 30 passed, typecheck/lint/build exit 0; E2E reali 3 run consecutivi da 8 passed, 0 failed, 0 skipped.

## DECISIONI PRESE IN AUTONOMIA

- Il lavoro del Blocco 0 non è perso né recuperabile da stash/commit: è ancora presente, non committato, nel working tree. Viene preservato integralmente e verificato sul branch dedicato.
- Il file aziendale `.xlsx` non tracciato sotto `docs/` è trattato come dato reale: non verrà letto, modificato, incluso nei log o committato.

## VERIFICHE

- `git status --short --branch`: comando riuscito; rilevati i file del checkpoint Blocco 0.
- `git branch -a`: comando riuscito; solo `main` locale e `origin/main` remoto.
- `git log --oneline -25 --all`: comando riuscito; HEAD più recente `fb61b7c`.
- `git stash list`: comando riuscito; nessuno stash.
- `git reflog -30`: comando riuscito; nessun commit irraggiungibile relativo al Blocco 0.
- Verifica presenza artefatti N0: 6/6 presenti.
- Creazione tag e branch: exit code 0; branch corrente `fase7/night-run`, tag `pre-night-run` presente.
- Docker stack: 4/4 servizi attivi; database e nginx healthy.
- ruff: 0 errori; black --check: 147 file invariati; mypy: 0 errori su 97 file.
- pytest Docker: 293 passed in 78.37s; gate coverage: 92.31%, soglia 85%, exit code 0.
- seedfile nel container con mount read-only: 4 passed, 289 deselected.
- frontend: vitest 30 passed; typecheck exit 0; eslint/prettier exit 0; build exit 0.
- migrazioni: `migrate --check` exit 0; nessuna migrazione pendente.
- loader demo con controlli: exit 0; esecuzione idempotente verificata prima dei run E2E.
- E2E iniziale senza variabili Makefile: browser assente (`ENOENT`), configurazione di invocazione errata e non regressione applicativa. Rieseguito con Chromium di sistema come previsto dal target `e2e`.
- E2E reale dopo fix indipendenza: 3 run consecutivi, ciascuno 8 passed, 0 failed, 0 skipped (24 pass totali osservati).
