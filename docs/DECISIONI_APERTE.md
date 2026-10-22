# Decisioni aperte e interpretazioni conservative

## D-16 — Quota residuo di IM26254 rilasciata al wallet

**Problema**: il seed reale non distingue il residuo informativo dei progetti ancora in corso
dalla quota già resa spendibile nel wallet.
**Scelta**: per `IM26254` l'import imposta `released_to_wallet_days = 10.0000`, come
rettifica esplicita e storicizzata. I residui dei progetti ATTIVI restano informativi salvo
questa quota; ulteriori rilasci richiedono motivazione tramite l'endpoint dedicato e non
possono superare il residuo disponibile.
**Dove**: `backend/projects/models.py`, `backend/importers/seed_json.py`,
`backend/api/domain_views.py`, `backend/domain/wallet_balance.py`.


Ogni voce elenca: la domanda non risolta dalle specifiche, la scelta applicata nel codice
(sempre la più conservativa) e dove vive nel codice. Da rivedere con il responsabile BMED.

## D-01 — Giornate di canone non utilizzate

**Non definito**: cosa accade alle giornate del monte semestrale non consuntivate a fine semestre.
**Scelta**: nessun travaso automatico verso il wallet. Le giornate non usate sono solo un KPI
("sotto-utilizzo canone") in dashboard e nella schermata Canone, più l'anomalia
`CHK_CANONE_UNDERUSE` quando il forecast scende sotto il 95% del monte.
**Dove**: `backend/domain/canone_status.py`, `backend/domain/checks/canone_underuse.py`.

## D-02 — `CHK_OVERRUN_PROJECT` e la fonte dello sforamento

**Problema**: il §11.1 richiede che la regola scatti su IM24133, dove il consumato interno è
esattamente pari al budget (85 su 85); lo sforamento (86,5) esiste solo nell'estratto PPM.
**Scelta**: la regola valuta `max(consumato interno, gg_totali dell'ultimo snapshot PPM del
progetto)`, coerente con R6 che eleva il PPM a fonte di verità dei consuntivi. La severità
deriva dallo scostamento percentuale (> 10% → ALTA, altrimenti MEDIA) e la descrizione
dichiara sempre da quale delle due fonti arriva lo sforamento.
**Conseguenza**: IM24133 → MEDIA (+1,8%), IM26292 → ALTA (+45,9%).
**Dove**: `backend/domain/checks/overrun_project.py`.

## D-03 — Progetti CHIUSO senza data di chiusura e Coda di revisione

**Problema**: nel seed 4 progetti sono `CHIUSO` ma solo 1 ha `data_chiusura_consuntivazione`;
gli altri 3 portano solo `anno_riferimento_residuo = 2026`. Inoltre, 9 progetti presentano
stato di consuntivazione `DA_VERIFICARE`. R2 fa dipendere la scadenza dall'anno della data
di chiusura, che in questi casi non esiste o non è consolidata.
**Scelta**:

1. `residual_reference_year` resta `null` (campo derivato di sola lettura); l'anno dichiarato
   nel seed è conservato in `declared_residual_year` solo per confronto visivo.
2. Senza data di chiusura consolidata il residuo è classificato `DA_VERIFICARE`: escluso dal
   disponibile wallet ufficiale e conteggiato nel KPI separato "residui potenziali da verificare".
3. **Coda di revisione progetti** (`GET /api/v1/projects/review-queue` / `domain.residuals.review_queue_projects`):
   raccoglie esattamente i 12 progetti da revisionare (3 `CHIUSO` senza data effettiva + 9 con stato
   `DA_VERIFICARE`).
4. **Ordinamento e scadenze**: gli elementi della coda sono ordinati per **scadenza potenziale crescente**
   (in base a `data_fine_effettiva`, `data_fine_prevista` o data convenzionale).
5. **Avviso entro 90 giorni**: se il residuo scade entro 90 giorni rispetto alla data di riferimento
   (es. 2026-10-16 del seed), viene generato un avviso esplicito (es. *"9,87 gg utilizzabili fino al 31/12/2026"*).
6. **Precompilazione data di chiusura**: l'interfaccia/endpoint predispone la proposta di data chiusura
   attinta da `data_fine_prevista` (o data di riferimento dell'import se assente), pronta per la conferma dell'utente.
**Dove**: `backend/domain/residuals.py` (`project_review_queue_qs()`, `review_queue_projects()`),
`backend/api/domain_views.py` (`ProjectReviewQueueView`), `backend/api/urls.py`, `backend/tests/test_review_queue.py`.

## D-04 — `gg_wallet_storico_gia_usati` e le allocazioni tecniche STORICO

**Problema**: il campo è presente su 9 progetti; il seed non contiene il wallet dell'anno
precedente in cui le allocazioni tecniche dovrebbero vivere.
**Scelta**: viene creato `WalletYear 2025` con 6 attività/allocazioni tecniche
`STORICO-<codice>` (stato CHIUSA, affidabilità DA_VERIFICARE). Sono escluse:

- **IM25270** perché il valore è 0 (nessuna giornata da tracciare);
- **IM25151 (5 gg)** e **IM25236 (2,06 gg)** perché, come confermato dal responsabile BMED,
  duplicano le allocazioni wallet 2026 `W26-012` e `W26-005` già presenti nel seed.
I tre scarti compaiono nel report del batch con la motivazione. Le allocazioni STORICO sono
contate separatamente, così i conteggi di accettazione del wallet 2026 (21 attività,
24 allocazioni) restano verificabili.
**Dove**: `backend/importers/seed_json.py` (`WALLET_HISTORY_SKIP`).

## D-05 — Anomalie seed sostituite dalle regole automatiche [RISOLTA]

**Stato**: RISOLTA (21/10/2026, implementata nella Fase 2).
**Problema**: le 11 anomalie del seed sono state scritte a mano e descrivono in prosa
situazioni che il motore controlli rileva da sé: lasciarle aperte produrrebbe doppioni.
**Soluzione adottata**:

1. Modello `Anomaly` esteso con campo `superseded_by` (`ForeignKey("self", null=True, blank=True, on_delete=SET_NULL)`) e metodo transazionale `mark_superseded(replacement)` che valida l'istanza sostitutiva (salvata, valida e non coincidente con se stessa), imposta `status = RISOLTA` e annota la motivazione con il codice regola automatico.
2. Mappa dichiarativa `SEED_SUPERSESSION_MAP` definita in `backend/importers/seed_json.py` che associa esplicitamente le anomalie seed alle corrispondenti regole automatiche di Fase 4 (`AN-003` → `CHK_UNVERIFIED_DATA` sui 9 progetti in stato DA_VERIFICARE, `AN-004` → `CHK_OVERRUN_PROJECT` su `IM26292`, `AN-005` → `CHK_DOUBLE_COUNT`, `AN-006` → `CHK_MISSING_IN_PPM` su `IM25379`, `AN-007` → `CHK_RECON_DELTA`, `AN-008` → `CHK_CANONE_UNDERUSE` su `IM26179`). Le anomalie seed risolte all'import per difetto Excel (`AN-001`, `AN-002`, `AN-009`, `AN-010`, `AN-011`) non creano rumore.
3. Idempotenza garantita: in caso di reimport del seed, le anomalie già marcate come `RISOLTA` per supersessione preservano puntatore e stato senza sovrascritture o riaperture indebite.
**Dove**: `backend/anomalies/models.py` (`Anomaly.superseded_by`, `Anomaly.mark_superseded()`), `backend/importers/seed_json.py` (`SEED_SUPERSESSION_MAP`), suite test in `backend/tests/importers/test_supersession.py`. Il runner automatico di Fase 4 (`backend/domain/checks/runner.py`) collegherà le istanze al primo calcolo.

## D-06 — Nessun job asincrono in v1

**Problema**: le specifiche ammettono Celery + Redis "solo se servono".
**Scelta**: non introdotti. Gli import sono piccoli (seed 84 KB, estratti PPM poche centinaia
di righe) e girano in una singola transazione sincrona con un limite di dimensione del file.
Se gli estratti crescessero oltre ~20.000 righe va rivalutato.
**Dove**: `backend/importers/batch.py`, `MAX_UPLOAD_BYTES` in `config/settings/base.py`.

## D-07 — Identificazione delle persone

**Problema**: nel seed `persone[].email` è `null` per tutti i 16 record.
**Scelta**: il match avviene solo sul nome normalizzato ("Cognome Nome" → "Nome Cognome",
spazi compattati, confronto case-insensitive e accent-insensitive) dentro la stessa
organizzazione. I nomi parziali (es. il solo nome proprio) **non** vengono risolti
automaticamente: finiscono nella coda di revisione con i candidati proposti.
**Dove**: `backend/directory/normalization.py`.

## D-08 — Milestone di fatturazione tutte `DA_VERIFICARE`

**Osservazione**: nel seed tutte le 54 milestone hanno stato `DA_VERIFICARE`.
**Scelta**: nessuna inferenza automatica dello stato di fatturazione del progetto a partire
dalle milestone. I due dati restano indipendenti e si aggiornano a mano (R1).

## D-09 — Allocazioni con 0 giornate

**Osservazione**: 4 allocazioni del seed hanno `gg_allocati = 0` (fra cui quella di IM26254).
**Scelta**: vengono importate così come sono, non cancellate: sono tracce di una decisione
presa nell'Excel originale. Il residuo del progetto di origine resta quindi interamente
disponibile e visibile nel pannello "Residui disponibili".

## D-10 — Segno del delta canone

**Scelta**: `delta = target_alla_data − consuntivato`. Positivo = consuntivato sotto il target
(a favore di BMED), mostrato in verde; negativo = oltre il target, mostrato in ambra/rosso.
Il tooltip esplicita sempre la formula e i suoi addendi.
**Dove**: `backend/domain/canone_status.py`.

## D-11 — Sforamento del residuo in allocazione

**Scelta**: blocco applicativo (errore `residuo-insufficiente`). Solo il ruolo Admin può
forzare, con motivazione obbligatoria registrata in `override_reason` + `override_by` e
apertura di `CHK_ALLOC_EXCEEDS_RESIDUAL`.

## D-12 — Formato della data di estrazione degli snapshot

**Osservazione**: `snapshot_ppm[].data_estrazione` è un datetime ISO (`2026-10-16T11:05:18`),
mentre tutte le altre date del seed sono `YYYY-MM-DD`.
**Scelta**: il parser accetta entrambi i formati; se manca l'ora si assume 00:00 nel fuso
`Europe/Rome`.

## D-13 — Collazione del database di sviluppo diversa da quella di produzione

**Osservazione**: l'istanza PostgreSQL portatile usata su questa macchina (niente WSL2,
quindi niente Docker) è stata inizializzata con `--locale=C`, mentre il servizio `db` di
`docker-compose.yml` usa `--encoding=UTF8 --locale=it_IT.UTF-8 --lc-collate=C`.
**Conseguenza**: la collazione (`lc_collate`) coincide in entrambi gli ambienti (C), quindi
gli ordinamenti di testo sono identici; cambiano solo `lc_ctype` e `lc_messages`, cioè la
classificazione dei caratteri e la lingua dei messaggi del server.
**Scelta**: nessun ordinamento applicativo si appoggia alla collazione del database per i
nomi di persona. Dove conta l'ordine alfabetico italiano (elenchi di persone) si ordina
usando la chiave normalizzata senza accenti (`Person.name_key`, vedi D-07), che è stabile
fra i due ambienti. Da rivalutare se un giorno servisse un `ORDER BY` sensibile agli accenti:
in quel caso va dichiarata una collazione esplicita sulla colonna, non ereditata dal cluster.
**Dove**: `scripts/pg-local.sh`, `docker-compose.yml`, `directory/normalization.py`.

## D-14 — Limitazione rigorosa delle eccezioni al solo SEED_JSON (mutazione ledger e vincoli)

**Problema**: il trigger `timesheets_append_only` nega UPDATE e DELETE sui consuntivi a qualsiasi livello.
Inoltre, il modello dati ammette progetti `CHIUSO` senza `actual_closure_date` unicamente per tollerare
i dati storici del file Excel di origine. Lasciare tali eccezioni aperte a futuri import (es. PPM mensili
di Fase 5) violerebbe l'integrità del ledger contabile.
**Scelta**:

1. **Mutazione e cancellazione consuntivi**: `timesheets.mutations.allow_ledger_mutation(reason, batch)`
   e il rollback diretto in `importers.rollback.rollback_seed_batch` sono consentiti **esclusivamente**
   se il batch associato è di tipo `ImportKind.SEED_JSON`. Per qualsiasi batch PPM (o altro tipo futuro),
   qualsiasi tentativo di mutazione diretta solleva `PermissionError`: i batch PPM si annulleranno unicamente
   mediante storni contabili append-only.
2. **Progetti CHIUSO senza data**: il check a livello di modello (`Project.clean()`) e il trigger dedicato a livello
   di database (`trg_project_closed_requires_seed_batch`) impongono che lo stato `CHIUSO` privo di data
   di chiusura sia ammesso **solo** se il progetto appartiene a un `import_batch` con `kind == 'SEED_JSON'`.
   Qualsiasi progetto creato senza batch o proveniente da flussi operativi/PPM deve obbligatoriamente fornire
   la data di chiusura effettiva.
**Dove**: `backend/timesheets/mutations.py`, `backend/importers/rollback.py`, `backend/projects/models.py`,
`backend/projects/migrations/0002_project_closed_seed_only_trigger.py`, `backend/tests/test_d14_seed_exceptions.py`.

## D-15 — Le giornate restano stringhe fino alla formattazione

**Problema**: in JavaScript ogni numero è un float a doppia precisione: sommare giornate nel
client reintrodurrebbe gli errori di arrotondamento che il backend evita con i Decimal.
**Scelta**: le giornate attraversano l'API come stringhe (`api/renderers.py` serializza ogni
Decimal come stringa) e nel frontend non vengono mai usate per calcoli. Tutti i totali,
i delta e le percentuali arrivano già calcolati dalle viste di dominio; il client converte a
numero solo dentro i formattatori, per la sola resa a schermo.
**Dove**: `backend/api/renderers.py`, `frontend/src/lib/format.ts`, test in
`frontend/src/lib/__tests__/format.test.ts`.

## D-17 — Regole di controllo addizionali candidate non attivate in v1

**Osservazione**: durante l'analisi sono emerse verifiche di coerenza potenzialmente utili (`CHK_MISSING_OWNER`, `CHK_ZERO_BUDGET`, `CHK_ZERO_ALLOCATION`, `CHK_MILESTONE_NO_DATE`, `CHK_BILLING_INCONSISTENT`, `CHK_PPM_UNMATCHED`, `CHK_PPM_UNBALANCED`).
**Scelta**: non attivate in v1 per aderenza rigorosa al catalogo canonico delle 18 regole di specifica (`CHK_DATE_ORDER`, `CHK_END_PASSED_ACTIVE`, `CHK_CLOSED_NO_DATE`, `CHK_OVERRUN_PROJECT`, `CHK_OVERRUN_ALLOCATION`, `CHK_ALLOC_EXCEEDS_RESIDUAL`, `CHK_RESIDUAL_EXPIRING`, `CHK_RESIDUAL_UNALLOCATED_CLOSED`, `CHK_ALLOC_FROM_EXPIRED`, `CHK_RECON_DELTA`, `CHK_MISSING_IN_PPM`, `CHK_DOUBLE_COUNT`, `CHK_CANONE_UNDERUSE`, `CHK_CANONE_OVERUSE`, `CHK_ACTIVE_WITHOUT_OFFER`, `CHK_ALLOC_NO_SOURCE`, `CHK_UNVERIFIED_DATA`, `CHK_MILESTONE_SLIPPED`). Da valutare con il responsabile BMED per estensioni future.

## D-16 — Disallineamento versione Python (venv locale 3.13 vs Dockerfile 3.12)

**Problema**: sull'ambiente di sviluppo Windows locale (privo di WSL2/Docker) l'interprete
disponibile nel `.venv` è Python 3.13 (`.venv/Scripts/python.exe`), mentre il file di deployment
`backend/Dockerfile` e `docker-compose.yml` fanno riferimento all'immagine ufficiale `python:3.12-slim`.
**Scelta**:

1. Il codice backend rispetta rigorosamente la compatibilità sia con Python 3.12 sia con Python 3.13
   (nessun uso di feature esclusive di 3.13; typing compatibile con 3.12 via `__future__.annotations` o unioni `|`).
2. Nei file di configurazione (`pyproject.toml`, linter) il target minimo rimane `py312`.
3. In sede di CI/CD e containerizzazione ufficiale viene impiegato l'ambiente standard Python 3.12;
   l'esecuzione locale su 3.13 è supportata e verificata con la suite di test completa e il tooling di qualità.
**Dove**: `backend/Dockerfile`, `pyproject.toml`, `docs/STATO_FASE_2.md`.
