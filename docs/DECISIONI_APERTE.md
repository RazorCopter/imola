# Decisioni aperte e interpretazioni conservative

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

## D-03 — Progetti CHIUSO senza data di chiusura
**Problema**: nel seed 4 progetti sono `CHIUSO` ma solo 1 ha `data_chiusura_consuntivazione`;
gli altri 3 portano solo `anno_riferimento_residuo = 2026`. R2 fa dipendere la scadenza
dall'anno della data di chiusura, che qui non esiste.
**Scelta**: `residual_reference_year` resta `null` (è un campo derivato e di sola lettura);
l'anno dichiarato nel seed è conservato in `declared_residual_year` solo per visualizzazione
e confronto. Senza data la scadenza non è calcolabile, quindi il residuo è classificato
`DA_VERIFICARE`: **escluso** dal disponibile wallet ufficiale e conteggiato nel KPI separato
"residui potenziali da verificare". Viene aperta `CHK_CLOSED_NO_DATE` (ALTA).
**Sbloccare**: coda di revisione → il campo data è precompilato con `data_fine_prevista`
(marcato come proposta, con l'origine del dato visibile) e si conferma con un clic.
**Dove**: `backend/domain/residuals.py`, `backend/domain/checks/closed_no_date.py`.

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

## D-05 — Anomalie seed sostituite dalle regole automatiche
**Problema**: le 11 anomalie del seed sono state scritte a mano e descrivono in prosa
situazioni che il motore controlli rileva da sé: lasciarle aperte produrrebbe doppioni.
**Scelta**: quando una regola rileva la stessa situazione, le due anomalie vengono collegate
(`superseded_by`) e quella seed passa a RISOLTA con nota "sostituita da `<rule_code>`".
Il riconoscimento usa una mappa dichiarativa `id_import → (rule_code, entità attesa)` e non
un confronto testuale, inaffidabile sulla prosa. Le anomalie seed non mappabili restano
aperte, con un'azione manuale "collega e chiudi come sostituita" nella coda di revisione.
**Dove**: `backend/importers/seed_json.py` (`SEED_SUPERSESSION_MAP`), `backend/domain/checks/runner.py`.

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

## D-14 — Finestra di modifica dei consuntivi per il rollback degli import
**Problema**: il trigger `timesheets_append_only` nega UPDATE e DELETE sui consuntivi anche
a `queryset.update()`, `queryset.delete()` e all'SQL diretta. Annullare un batch di import,
tuttavia, deve poter rimuovere le righe che quel batch ha creato.
**Scelta**: una sola via d'uscita, il parametro di sessione
`supplier_ledger.allow_ledger_mutation`, impostato con `SET LOCAL` dal gestore di contesto
`timesheets.mutations.allow_ledger_mutation(motivazione)`. Vale solo per la transazione in
corso, si chiude da sé al commit o al rollback, pretende una motivazione e scrive due righe
di log (apertura e chiusura). Nessun altro percorso applicativo deve usarla: ogni correzione
di merito resta uno storno.
**Dove**: `timesheets/migrations/0002_append_only_trigger.py`, `timesheets/mutations.py`,
`tests/test_append_only.py`.

## D-15 — Le giornate restano stringhe fino alla formattazione
**Problema**: in JavaScript ogni numero è un float a doppia precisione: sommare giornate nel
client reintrodurrebbe gli errori di arrotondamento che il backend evita con i Decimal.
**Scelta**: le giornate attraversano l'API come stringhe (`api/renderers.py` serializza ogni
Decimal come stringa) e nel frontend non vengono mai usate per calcoli. Tutti i totali,
i delta e le percentuali arrivano già calcolati dalle viste di dominio; il client converte a
numero solo dentro i formattatori, per la sola resa a schermo.
**Dove**: `backend/api/renderers.py`, `frontend/src/lib/format.ts`, test in
`frontend/src/lib/__tests__/format.test.ts`.
