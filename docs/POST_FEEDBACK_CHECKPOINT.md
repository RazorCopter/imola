# Checkpoint post-feedback — fatturazioni, costi e reset DB

Data verifica: 2026-10-23. Branch rilevato: `fase7/night-run`. Nessun commit, push o deployment eseguito.

## Incremento: eliminazione sicura Progetti e allocazioni Wallet

### Contratti e politica di sicurezza

- `DELETE /api/v1/projects/{id}` richiede server-side `projects.edit` e `If-Match`/`expected_version`: 428 senza versione, 409 stale. La cancellazione fisica è ammessa soltanto per progetti manuali (`import_batch` nullo) senza milestone, consuntivi, allocazioni origine, attività wallet di destinazione, canoni/sotto-attività, righe PPM o anomalie. Il problema di dominio riporta un riepilogo delle categorie e dei conteggi; nessun ledger viene cancellato. Prima della delete viene scritto `AdminAuditEvent` con snapshot non sensibile.
- `POST /api/v1/allocations` richiede `wallet.edit`, anno coerente con la chiusura dell'origine, origine chiusa/non scaduta e giornate positive entro il residuo spendibile. La transazione blocca il progetto origine con `SELECT FOR UPDATE` e ricalcola il residuo nel lock, impedendo sovra-allocazioni concorrenti. La risposta include id, versione, ETag e residuo origine successivo; viene scritto audit create.
- `GET /api/v1/wallet/allocation-options/` espone in una query annotata (subquery aggregate, senza N+1) anno, residuo disponibile, stato di validità, scadenza e usabilità delle origini.
- `DELETE /api/v1/wallet/allocations/{id}/` richiede `wallet.edit` e optimistic locking. Blocca record importati, qualsiasi `TimesheetEntry` (anche coppie movimento/storno a netto zero) e anomalie; non tocca il ledger append-only. Registra audit delete in transazione e libera immediatamente il residuo impegnato.

### UX

- Il dettaglio Progetto mostra “Elimina progetto” solo dopo il caricamento e solo con permission delete. Un secondo dialog Radix richiede il codice progetto; errori di dipendenza restano leggibili. Al successo rimuove subito la riga e invalida progetti, dashboard, opzioni, analisi costi e wallet.
- Wallet mostra “Nuova allocazione” solo con `wallet.edit`; il dialog chiarisce che le giornate provengono dal residuo spendibile dell'origine e visualizza residuo, validità e scadenza. Al successo seleziona la nuova allocazione e aggiorna flow, balance, assegnatari, opzioni e dashboard.
- Il pannello allocazione mostra “Elimina allocazione” solo agli autorizzati, usa conferma Radix con codice attività e, al successo, seleziona la riga successiva. Utenti read-only non vedono CTA o mutation.
- Gli E2E di Progetti e Wallet verificano presenza e dialog di conferma senza premere il comando distruttivo su dati persistenti.

### File principali di questo incremento

- `backend/api/domain_views.py`, `backend/core/permissions.py`
- `backend/tests/test_project_editing_api.py`, `backend/tests/test_wallet_editing_api.py`
- `frontend/src/features/projects/EditProjectDialog.tsx`, `frontend/src/features/projects/ProjectsPage.tsx`
- `frontend/src/features/wallet/NewAllocationDialog.tsx`, `frontend/src/features/wallet/EditAllocationDialog.tsx`, `frontend/src/features/wallet/WalletPage.tsx`
- test Vitest ed E2E associati.

### Verifiche eseguite

- Docker backend mirato: `pytest tests/test_project_editing_api.py tests/test_wallet_editing_api.py tests/test_append_only.py -q` → exit 0, **48 passed**.
- Ruff sui file backend coinvolti → exit 0, **All checks passed**.
- Vitest Progetti/Wallet → exit 0, **2 file / 10 test passed**.
- TypeScript `tsc -b --noEmit` → exit 0.
- ESLint + Prettier check → exit 0.
- Build Vite production → exit 0, **2539 moduli trasformati**.

### Limiti e stato operativo

- E2E aggiornati ma non eseguiti contro lo stack in questa sessione; non è stata confermata alcuna delete su dati reali. Le mutation sono state validate esclusivamente sul database test isolato e con mock frontend.
- La concorrenza è coperta dal lock pessimista e dal test di ricalcolo sequenziale nella transazione; non è stato eseguito un test multi-connessione temporizzato.
- Nessun dato reale modificato. Nessun commit, push, pubblicazione o deployment eseguito.

## Comportamento realizzato

### Dashboard — fatturazioni del mese corrente

- La sezione `prossime_fatturazioni` include esclusivamente milestone aperte (`PIANIFICATA`, `SPOSTATA`, `DA_VERIFICARE`) con `planned_date` compresa tra il primo e l'ultimo giorno del mese di `today`.
- Le milestone di mesi precedenti/successivi e gli stati terminali fatturati/annullati sono esclususe.
- `data_pianificata` conserva la data reale della tranche; `data_fatturazione` è l'ultimo giorno del mese corrente per tutte le righe.
- La deduplicazione resta limitata alla chiave naturale `(project_id, planned_date)`, scegliendo deterministicamente la riga più antica per `created_at`, poi `id`.
- `count` è calcolato dopo filtro e deduplicazione ma prima del `limit`; le chiavi React restano univoche per progetto/data prevista.
- UI e empty state non classificano più righe come future/scadute, perché il dataset è esclusivamente del mese corrente.

### Analisi Costi — Costi per progetto

- Il grafico ordina esplicitamente i progetti per costo decrescente, con tie-break alfabetico.
- Il selettore Top 5/10/20 e la ricerca progetto filtrano solo il grafico/riepilogo, senza modificare i KPI globali o il contratto backend.
- È presente un empty state specifico per ricerche senza risultati.
- Tooltip React personalizzato con sfondo opaco `#0f172a`, testo ad alto contrasto, bordo, ombra, marker colore, nome progetto completo e valore euro formattato.
- Eliminato il cursor overlay Recharts predefinito; barre con colore premium esplicito, angoli arrotondati e `activeBar` discreto.
- Titolo e descrizione sono associati alla sezione. Una tabella accessibile riporta progetto e costo, quindi il tooltip non è l'unica fonte informativa.

### Admin — reset solo in Configurazione

- Titolo rinominato esattamente in `Attenzione - Reset Completo DB`.
- Sezione e trigger sono nel DOM soltanto con tab attivo `Configurazione` e `canResetData(session)` vero.
- Negli altri tab il trigger è assente; il dialog continua ad aprirsi e il comportamento/sicurezza server-side non sono stati modificati.

## File modificati in questo incremento

- `backend/domain/dashboard.py`
- `backend/tests/domain/test_dashboard.py`
- `backend/tests/test_dashboard_api.py`
- `frontend/src/components/AccessibleBarChart.tsx`
- `frontend/src/features/dashboard/DashboardPage.tsx`
- `frontend/src/features/dashboard/__tests__/DashboardPage.test.tsx`
- `frontend/src/features/cost-analysis/CostAnalysisPage.tsx`
- `frontend/src/features/cost-analysis/__tests__/CostAnalysisPage.test.tsx`
- `frontend/src/features/admin/AdminPage.tsx`
- `frontend/src/features/admin/__tests__/AdminPage.test.tsx`
- `frontend/src/i18n/it.json`
- `frontend/src/i18n/en.json`
- `frontend/e2e/phase7_admin_delete_db.spec.ts`
- `frontend/e2e/post_feedback_corrections.spec.ts`
- `docs/POST_FEEDBACK_CHECKPOINT.md`

Il workspace conteneva già numerose modifiche e file non tracciati, preservati. `frontend/tsconfig.node.tsbuildinfo` era già modificato e non è stato editato intenzionalmente.

## Verifiche ed esiti

| Verifica | Comando | Esito |
|---|---|---|
| Backend dashboard mirato in Docker | `docker compose exec backend pytest tests/domain/test_dashboard.py tests/test_dashboard_api.py -q` | exit 0; 4 test superati |
| Vitest mirati | `npm test -- --run src/features/dashboard/__tests__/DashboardPage.test.tsx src/features/cost-analysis/__tests__/CostAnalysisPage.test.tsx src/features/admin/__tests__/AdminPage.test.tsx` | exit 0; 3 file, 12 test superati |
| TypeScript | `npm run typecheck` | exit 0 |
| ESLint + Prettier file toccati | `npx eslint ... && npx prettier --check ...` | exit 0; nessun errore/warning, tutti i file conformi |
| Build Vite | `npm run build` | exit 0; 2538 moduli trasformati |
| Browser Chromium sullo stack | `npx playwright test e2e/post_feedback_corrections.spec.ts --project=chromium` | exit 0; 3 test superati in 6,8 s |

La validazione browser ha verificato: contratto dashboard con tutte le righe nel mese generato e fatturazione a fine mese; Top-N, ricerca, riepilogo e tooltip custom del grafico; assenza reset negli altri tab, presenza/titolo/dialog in Configurazione. Non è stata eseguita alcuna conferma distruttiva del reset.

## Conteggi e limiti

- Fatturazioni dashboard: limite backend invariato a 50; `count` rappresenta tutte le chiavi naturali aperte del mese prima del limite.
- Grafico progetti: default Top 10; opzioni 5, 10, 20; ricerca case-insensitive client-side sull'intero aggregato `by_project`.
- Nessuna modifica al contratto cost-analysis backend e nessuna alterazione dei KPI globali.

## Stato consegna

- Commit: non eseguito.
- Push/pubblicazione: non eseguiti.
- Deployment: non eseguito; verifica effettuata sullo stack Docker locale già attivo.
- Dati reali: non modificati; test backend su database di test e browser in sola lettura, salvo login/sessione. Il dialog reset è stato aperto ma non confermato.
- Verifiche pendenti: nessuna rispetto all'ambito richiesto.
