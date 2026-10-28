# Supplier Ledger - design system consolidato

Ambito: primitivi e pattern frontend esistenti. Si mantengono componenti di dominio diversi quando la semantica differisce. Nessuna libreria grafica aggiunta al runtime.

| Famiglia | Implementazione / varianti | Stati e accessibilita | Responsive |
|---|---|---|---|
| Pulsanti | Controls.Button: plain, primary, secondary, danger; props native e forwardRef | submit/button conservati, disabled, focus visibile; min-height 36 px | azioni in flex-wrap |
| Input, date, ricerca | Controls.Input, type nativo; color-scheme del tema | label/aria-label; invalid per errori; placeholder e disabled semantici | min-width 0 e max-width 100% |
| Select e textarea | Controls.Select/Textarea; varianti tramite className | label e ref native; checkbox/radio restano controlli nativi | select min-height 36 px; textarea ridimensionabile |
| Intestazioni | PageHeader su Progetti, Wallet, Organico, Costi, Anomalie, Revisione e Admin | un h1, eyebrow, descrizione e azioni separate | wrapping delle azioni; parole lunghe spezzabili |
| Intestazioni speciali | hero Dashboard; Riconciliazione con stato snapshot; dettaglio progetto | gerarchia equivalente, conservata la semantica specifica | spazio massimo 1600 px nella shell |
| Filtri | FilterBar nei toolbar equivalenti; form Costi e filtri applicati Organico mantengono la propria semantica | role group e nomi dei campi; Applica/Azzera conservati dove previsti | flex-wrap e scroll locale delle tabelle |
| Tab | Radix Tabs per dettaglio Progetto/attivita; Admin tablist con roving tabIndex | frecce, Home/End, aria-selected/controls e tabpanel | scorrimento orizzontale locale |
| Badge | StatusBadge; OutcomeBadge per esiti riconciliazione | testo oltre al colore, dominio sr-only dove applicabile | testo leggibile, nessun affidamento al solo colore |
| KPI | KpiCard condiviso: neutral/ok/warn/danger, featured, hint/action | MetricLabel e tooltip; null, zero, loading, errori e non verificabile distinti | griglie per breakpoint; hint e azione su righe separate |
| Tabelle | DataTable per portafoglio; tabelle dedicate per FIFO, import, riconciliazione e aggregazioni | header, ordinamento numerico, righe da tastiera; resizer con frecce e Home | overflow confinato; 24 righe e titoli lunghi verificati |
| Dialog | Radix Dialog; ConfirmActionDialog per eliminazioni Organico | titolo/descrizione, Escape, focus trap, ritorno del focus; hook useDialogFocusReturn per dialog controllati senza Trigger | larghezza entro viewport, max-height e scroll quando necessari |
| Drawer | dettaglio Wallet in Radix Dialog laterale | nome/descrizione, focus di ritorno alla riga e Escape | max 42 rem, larghezza piena fino a 1024; scroll interno |
| Tooltip | Radix Tooltip per informazioni; ChartTooltip per grafici | apertura da focus/hover, Escape, portal e collision padding; dati grafici anche testuali | massimo min(18rem, viewport - 2rem) |
| Feedback | role status per successi, role alert per errori; messaggi ApiError in Anomalie/Revisione | non viene introdotto un secondo sistema di toast; feedback accanto al lavoro | testo a capo e blocchi fluidi |
| Stati | UiState.LoadingState/EmptyState/ErrorState | loading role status; error role alert; retry nei punti pertinenti | nessun valore fittizio per sostituire un errore |
| Grafici | AccessibleBarChart e DashboardCharts.DonutChart | legenda leggibile, segmenti nominati; readout testuale; nessuna animazione dei dati | colonne Dashboard singole sotto xl, grafici Costi orizzontali |
| Movimento | token/animazioni esistenti e prefers-reduced-motion | riduzione di durata globale; screenshot e axe acquisiti a transizioni finite | nessuna animazione necessaria per leggere i dati |

## Token

I colori sono definiti in frontend/src/styles/index.css e risolti da Tailwind: background/card/muted/foreground/border/input/ring, accent, ok, warn, danger e relative superfici. primary/secondary/destructive rimangono alias compatibili; i pulsanti di eliminazione pieni usano danger-action/danger-foreground, separati dal colore del testo di errore.

Correzioni osservate: accento dark piu chiaro; ok/warn/danger light piu scuri; danger dark piu chiaro; pulsanti verdi con fondo emerald-700; messaggi di successo con text-ok. Il badge Bloccato nel dialog progetto usa text-warn invece di un ambra fisso insufficiente in light. La legenda dei grafici usa foreground per le etichette e conserva il colore nei marcatori.

## Prove

Evidenze: outputs/visual-review/sol-final/*-axe.json e *-axe-summary.json; test sol-final.spec.ts, test Vitest e screenshot originali. Il superamento di axe copre le regole eseguite, non costituisce certificazione WCAG. Le verifiche umane riguardano gerarchia, leggibilita, spazi, dialog, grafici e scorrimento osservati negli screenshot.
