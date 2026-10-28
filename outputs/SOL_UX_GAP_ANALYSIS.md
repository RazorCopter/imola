# SOL - gap analysis chiusa

28 ottobre 2026. Backlog frontend definito dopo audit del repository e chiuso contro le prove riportate. Le correzioni osservate durante il ciclo render/inspect sono incluse. DONE riguarda i criteri frontend indicati; la persistenza e le operazioni reali backend sono tracciate separatamente.

| ID | Priorita | Pagina / componente | Stato |
|---|---|---|---|
| SOL-01 | P2 | Tutte / controlli | DONE |
| SOL-02 | P2 | Tutte / gerarchia | DONE |
| SOL-03 | P1 | Admin / ImportPanel | DONE |
| SOL-04 | P1 | Organico / dettaglio e attivita | DONE |
| SOL-05 | P1 | Wallet / dettaglio | DONE |
| SOL-06 | P1 | Anomalie e Revisione / feedback | DONE |
| SOL-07 | P1 | Admin / navigazione e utenti | DONE |
| SOL-08 | P0 | Dashboard / fonti KPI | DONE |
| SOL-09 | P3 | Dialog, tooltip e resizer | DONE |
| SOL-10 | P3 | Tutte / contrasto | DONE |
| SOL-11 | P3 | Nove pagine / responsive | DONE |
| SOL-12 | P1 | QA / browser isolato | DONE |
| SOL-13 | P3 | QA / evidenze visive | DONE |
| SOL-14 | P2 | Documentazione / chiusura | DONE |
| SOL-15 | P1 | Organico / eliminazioni | DONE |
| SOL-16 | P4 | Costi / aggregazioni | DONE |
| SOL-BE | P0 | Backend reale / integrazione | BLOCKED |

## SOL-01 - Tutte / controlli

- Priorita: P2. Stato: DONE.
- Problema / impatto UX: Controlli nativi con stili ripetuti e stati non uniformi.
- File coinvolti: Controls.tsx; features/* (sotto frontend/src salvo percorsi espliciti).
- Intervento: Button/Input/Select/Textarea condivisi, ref e props native conservati.
- Criterio di accettazione verificato: Form e azioni funzionanti, focus e disabled uniformi.
- Test: 73 Vitest; 25 Playwright; 40 axe.
- Evidenza: review-sheets/*.png, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-02 - Tutte / gerarchia

- Priorita: P2. Stato: DONE.
- Problema / impatto UX: KPI duplicato Dashboard e template pagina equivalenti.
- File coinvolti: KpiCard.tsx; PageHeader.tsx; DashboardPage.tsx; pagine operative (sotto frontend/src salvo percorsi espliciti).
- Intervento: KPI riutilizzato, PageHeader e FilterBar per semantiche equivalenti.
- Criterio di accettazione verificato: Titoli, azioni, hint e tooltip conservati; link non compressi.
- Test: Matrice nove route e controlli di navigazione.
- Evidenza: dashboard-dark-1440x900.png; progetti-dark-1440x900.png, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-03 - Admin / ImportPanel

- Priorita: P1. Stato: DONE.
- Problema / impatto UX: Conferma applicazione valida anche sostituendo il file simulato.
- File coinvolti: features/admin/AdminPage.tsx (sotto frontend/src salvo percorsi espliciti).
- Intervento: Reset preview e risultato al cambio file; pending sugli input.
- Criterio di accettazione verificato: Cambiare file disabilita Conferma; simulazione e conferma disponibili solo in sequenza.
- Test: Playwright: amministrazione import e cambio file; PPM/download.
- Evidenza: admin-preview-enabled.png; admin-import-result.png, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-04 - Organico / dettaglio e attivita

- Priorita: P1. Stato: DONE.
- Problema / impatto UX: Creazione sempre aperta e dati precedenti durante cambio canone.
- File coinvolti: features/canone/CanonePage.tsx (sotto frontend/src salvo percorsi espliciti).
- Intervento: Creazione esplicita; loading/error del dettaglio; selezione corrente verificata; attivita su due righe a sinistra.
- Criterio di accettazione verificato: Passaggio fra due canoni non mostra attivita precedenti; retry recupera dettaglio; modifica contestuale.
- Test: Playwright: creazione/modifica/consuntivo; cambio canone con risposta ritardata ed errore.
- Evidenza: organico-dark-bottom.png; organico-detail-error.png; organico-cambio-selezione.png, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-05 - Wallet / dettaglio

- Priorita: P1. Stato: DONE.
- Problema / impatto UX: Dettaglio affiancato restringe la tabella; ritorno focus non verificato.
- File coinvolti: features/wallet/WalletPage.tsx; EditAllocationDialog.tsx; NewAllocationDialog.tsx (sotto frontend/src salvo percorsi espliciti).
- Intervento: Drawer Radix con scroll; nomi dei campi stabili; ripristino focus.
- Criterio di accettazione verificato: Enter apre, Escape e Chiudi restituiscono focus; update e nuovo utilizzo inviano richieste corrette.
- Test: Playwright Wallet; unit test FIFO e consumo cumulativo.
- Evidenza: wallet-drawer.png; wallet-drawer-dark-1024-bottom.png; wallet-nuovo-dialog.png, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-06 - Anomalie e Revisione / feedback

- Priorita: P1. Stato: DONE.
- Problema / impatto UX: Errori generici, pending incompleto e conferme poco esplicite.
- File coinvolti: AnomaliesPage.tsx; ReviewQueuePage.tsx (sotto frontend/src salvo percorsi espliciti).
- Intervento: Messaggi ApiError, successi role status, pending; data obbligatoria solo quando CHIUSO; motivazioni leggibili.
- Criterio di accettazione verificato: Errore mostrato senza perdere input; retry riuscito; CHIUSO senza data non salvabile.
- Test: Playwright: errori di mutazione, retry e validazione revisione.
- Evidenza: anomalie-mutation-error.png; revisione-form.png, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-07 - Admin / navigazione e utenti

- Priorita: P1. Stato: DONE.
- Problema / impatto UX: Dialog custom, navigazione secondaria e storico disomogenei.
- File coinvolti: features/admin/AdminPage.tsx; DeleteDatabaseDialog.tsx (sotto frontend/src salvo percorsi espliciti).
- Intervento: Dialog utenti Radix; tablist da tastiera; storico tabellare; backup/restore visibili.
- Criterio di accettazione verificato: Tab attivi e pannelli coerenti; modale etichettato; import/export, utenti, referenti, ruoli e costo esercitati con fixture.
- Test: Vitest Admin; Playwright Admin e subview 1024 dark/light.
- Evidenza: admin-utente-dialog.png; admin-Utenti-dark-1024.png; amministrazione-dark-bottom.png, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-08 - Dashboard / fonti KPI

- Priorita: P0. Stato: DONE.
- Problema / impatto UX: Errore di una fonte poteva apparire come assenza o numero.
- File coinvolti: features/dashboard/DashboardPage.tsx (sotto frontend/src salvo percorsi espliciti).
- Intervento: Errore per fonte distinto da zero/null/non verificabile; nessuna modifica economica.
- Criterio di accettazione verificato: Con fonte Wallet in errore, Delta PPM resta valido e le KPI Wallet mostrano Errore caricamento.
- Test: Playwright errori parziali; test Dashboard su valori non rappresentabili.
- Evidenza: dashboard-source-error.png; dashboard-error.png; dashboard-empty.png, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-09 - Dialog, tooltip e resizer

- Priorita: P3. Stato: DONE.
- Problema / impatto UX: Etichette non associate, focus perso, tooltip non dismissibile.
- File coinvolti: InfoTooltip.tsx; useDialogFocusReturn.ts; EditProjectDialog.tsx; NewProjectDialog.tsx; ResizableTableHeader.tsx (sotto frontend/src salvo percorsi espliciti).
- Intervento: Label/id, aria-invalid/errori collegati; descrizioni; focus di ritorno; Radix Tooltip; tastiera resizer.
- Criterio di accettazione verificato: Escape, focus trap/ritorno, frecce/Home e trascinamento verificati; audit senza violazioni.
- Test: 40 axe; 4 controlli manual-checks; Vitest tooltip.
- Evidenza: progetti-edit-light-1024.png; admin-reset-light.png; manual-interaction-checks.json, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-10 - Tutte / contrasto

- Priorita: P3. Stato: DONE.
- Problema / impatto UX: Accento dark, badge light, pulsanti verdi e legenda insufficienti.
- File coinvolti: styles/index.css; tailwind.config.ts; AccessibleBarChart.tsx; azioni interessate (sotto frontend/src salvo percorsi espliciti).
- Intervento: Token semantici corretti; danger-action distinto dal testo; legenda foreground.
- Criterio di accettazione verificato: Nessuna violazione nelle regole axe eseguite nelle 40 viste.
- Test: 40 audit dark/light; osservazione screenshot.
- Evidenza: *-axe.json; *-axe-summary.json, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-11 - Nove pagine / responsive

- Priorita: P3. Stato: DONE.
- Problema / impatto UX: Matrice parziale; scorciatoia topbar a capo e rischio overflow.
- File coinvolti: AppShell.tsx; pagine operative; e2e/sol/sol-final.spec.ts (sotto frontend/src salvo percorsi espliciti).
- Intervento: Matrice completa; Ctrl K non va a capo; scroll locale e griglie adattive.
- Criterio di accettazione verificato: Nessun overflow orizzontale documento a cinque viewport; ultimo comando della tabella raggiungibile.
- Test: Playwright nove route x sei combinazioni e tabella 24 righe.
- Evidenza: *-1024x768.png; progetti-stress-scroll.png; scroll-diagnostics.json, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-12 - QA / browser isolato

- Priorita: P1. Stato: DONE.
- Problema / impatto UX: Script temporanei frammentati, flussi non riproducibili.
- File coinvolti: e2e/sol.config.ts; e2e/sol/*; package.json (sotto frontend/src salvo percorsi espliciti).
- Intervento: Harness deterministico e Vite senza proxy; fixture fuori dal bundle.
- Criterio di accettazione verificato: 25 scenari passati, nessun errore JS/console inatteso; richieste non fixture bloccate.
- Test: npm run e2e:ux; manual-checks.mjs.
- Evidenza: results.json; manual-interaction-checks.json, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-13 - QA / evidenze visive

- Priorita: P3. Stato: DONE.
- Problema / impatto UX: Catture non tutte della versione finale e review incompleta.
- File coinvolti: e2e/sol/catalog.py; outputs/visual-review/sol-final/ (sotto frontend/src salvo percorsi espliciti).
- Intervento: Catture reali, catalogo, manifest SHA256, contact sheet e riesame delle correzioni.
- Criterio di accettazione verificato: 121 originali esaminati tramite tavole e ingrandimenti; originali Terra preservati.
- Test: Ispezione delle nove tavole, dettagli 01-16 e cambiamenti; catalogo finale.
- Evidenza: index.html; SCREENSHOTS.md; screenshot-manifest.json; VISUAL_REVIEW.md, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-14 - Documentazione / chiusura

- Priorita: P2. Stato: DONE.
- Problema / impatto UX: Report storico con PARTIAL generico.
- File coinvolti: outputs/SOL_UX_*.md (sotto frontend/src salvo percorsi espliciti).
- Intervento: Criteri, prove, stato per gap e limite backend separato.
- Criterio di accettazione verificato: Ogni DONE collegato a test e screenshot; comandi riproducibili.
- Test: Controllo documenti, risultati e Git.
- Evidenza: SOL_UX_FINAL_REPORT.md; SOL_UX_PROGRESS.md, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-15 - Organico / eliminazioni

- Priorita: P1. Stato: DONE.
- Problema / impatto UX: Eliminazione da un singolo click, senza conferma contestuale.
- File coinvolti: ConfirmActionDialog.tsx; CanonePage.tsx (sotto frontend/src salvo percorsi espliciti).
- Intervento: Conferma Radix per canone, attivita e consuntivo, focus iniziale su Annulla e pending.
- Criterio di accettazione verificato: Annulla/Escape non inviano DELETE e restituiscono focus; ELIMINA resta rosso.
- Test: Playwright conferme sicure; audit dialog.
- Evidenza: organico-conferma-eliminazione.png, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-16 - Costi / aggregazioni

- Priorita: P4. Stato: DONE.
- Problema / impatto UX: Tabella senza righe mostrava soltanto intestazioni.
- File coinvolti: features/cost-analysis/CostAnalysisPage.tsx (sotto frontend/src salvo percorsi espliciti).
- Intervento: Messaggio esplicito nella singola aggregazione vuota.
- Criterio di accettazione verificato: Gruppo vuoto spiegato senza eliminare le altre aggregazioni popolate.
- Test: Playwright aggregazioni parziali; Vitest Costi.
- Evidenza: costi-aggregazione-vuota.png, in outputs/visual-review/sol-final salvo documenti SOL.

## SOL-BE - integrazione reale

Priorita P0; stato BLOCKED per dipendenza backend, esterna al backlog frontend implementabile. Docker backend risulta restarting. api/urls.py:51 richiama admin_views.ReferentListCreateView, assente nel file locale preesistente. Il file backend/api/admin_views.py e rimasto escluso e non e stato modificato. Log: outputs/sol-backend-blocker.log. API e business logic non alterate. E2E su dati reali, import effettivo e restore del DB NON verificati.

## Esito

16 gap frontend DONE; nessun gap frontend NOT_STARTED/PARTIAL nel backlog definito. Un blocco di integrazione reale separato. Nessun commit, push, reset, clean o intervento sul database.
