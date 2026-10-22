# Matrice permessi per ruolo — Fase 7, Blocco 0.3

## Criterio

La matrice descrive il comportamento effettivo introdotto/verificato per la sezione 0.3. La sicurezza è applicata dalle permission API; la GUI usa esclusivamente il payload di sessione (`roles`, `is_admin`, `can_write`) e, per l'annotazione del singolo progetto, la permission object-level restituita dall'API. Nascondere un'azione non autorizza la corrispondente mutation.

La navigazione resta distinta dalle mutation: tutte le pagine consultive elencate sono raggiungibili da ogni ruolo autenticato perché le API di lettura corrispondenti sono accessibili. La route placeholder `/amministrazione` è stata rimossa: non rappresentava una capability disponibile. Un URL frontend sconosciuto viene ricondotto alla dashboard; una chiamata API vietata risponde `403`.

Legenda: **R** lettura, **W** mutation, **DR** upload forzato in dry-run, **—** non consentito/non esposto.

## Matrice GUI, API e risultato atteso

| GUI / capability | API | Admin | Responsabile BMED | Referente BMED | Fornitore | Permesso backend | Esito atteso |
|---|---|---:|---:|---:|---:|---|---|
| Dashboard | `GET wallet/.../balance`, `GET reconciliation/latest` | R | R | R | R | autenticato | Pagina e menu visibili; dati consultabili. |
| Progetti / dettaglio / storico | `GET projects/balances`, `GET audit/project/{id}` | R | R | R | R | autenticato / safe method | Pagina e menu visibili anche ai ruoli senza scrittura. |
| Nuovo progetto | `POST projects` | W | W | — | — | `ReadOnlyOrLedgerWriter` | Azione visibile solo con `can_write`; API `403` per Referente e Fornitore. |
| Annotazione progetto (data prevista, note, punti verifica) | `PATCH projects/{id}` | W | W | W sul proprio progetto | — | `ReferentCanAnnotate` object-level | La GUI usa `permissions.annotate`; il Referente riceve `403` su progetto altrui, il Fornitore sempre `403`. |
| Wallet | `GET wallet/{year}/balance`, `GET wallet/{year}/flow` | R | R | R | R | autenticato | Pagina e menu visibili per tutti. |
| Rettifica/chiusura allocazione wallet | `POST allocations/{id}/adjust` | W | W | — | — | `ReadOnlyOrLedgerWriter` | Azioni visibili solo con `can_write`; chiamata diretta vietata con `403`. |
| Canone | `GET canoni`, `GET canoni/{id}/status` | R | R | R | R | autenticato | Pagina e menu visibili per tutti. |
| Riconciliazione | `GET reconciliation/latest` | R | R | R | R | autenticato | Pagina e menu visibili per tutti. |
| Anomalie | `GET anomalies` | R | R | R | R | autenticato | Inbox consultabile per tutti. |
| Esecuzione controlli / gestione anomalie | `POST checks/run`, `POST anomalies/{id}/{action}` | W | W | — | — | `ReadOnlyOrLedgerWriter` | Pulsanti visibili solo con `can_write`; API `403` agli altri ruoli. |
| Coda revisione | `GET review-queue` | R | R | R | R | autenticato | Pagina e menu visibili per tutti. |
| Conferma revisione | `POST projects/{id}/confirm-review` | W | W | — | — | `ReadOnlyOrLedgerWriter` | Writer vedono il form; agli altri è mostrato “Sola lettura” e l'API risponde `403`. |
| Impostazioni globali | `GET/PATCH settings` | R/W | R/— | R/— | R/— | lettura autenticata, scrittura `IsAdmin` | Nessuna GUI amministrativa completa è dichiarata; `PATCH` non Admin risponde `403`. |
| Upload PPM | `POST imports/ppm` | W | W | — | DR | `CanUploadImports` + forzatura server-side | Admin/Responsabile possono applicare; Fornitore può caricare ma `apply=true` resta dry-run; Referente riceve `403`. Non è introdotta una nuova GUI upload. |
| Amministrazione | nessuna API aggregata/capability completa | — | — | — | — | n/d | Nessuna voce menu o route ingannevole; non viene dichiarata amministrazione completa. |

## Accesso diretto e fonte di sicurezza

- Le route consultive restano raggiungibili direttamente per tutti i quattro ruoli autenticati.
- Le singole azioni di scrittura sono allineate a `can_write` o alla permission object-level del progetto, senza identificativi utente hardcoded.
- L'accesso diretto a una mutation tramite API non dipende dalla GUI: le permission DRF restituiscono `403` quando il ruolo non è autorizzato.
- Il Fornitore mantiene il comportamento esistente dell'upload PPM: può inviare il file, ma il backend ignora la richiesta di applicazione e restituisce un risultato dry-run.
- Questa evidenza non modifica classificazioni o stati della baseline `docs/FUNCTIONAL_GAP_ANALYSIS.md` e non dichiara alcuna capability COMPLETA.
