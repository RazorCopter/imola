# Matrice permessi per ruolo — Fase 7

## Contratto

La sicurezza delle mutation è applicata dal backend tramite capability granulari. La sessione autenticata espone `capabilities` oltre ai campi legacy `roles`, `is_admin` e `can_write`. I gruppi Django restano la fonte dei ruoli assegnati agli account; la fonte di verità delle variazioni rispetto ai default è `core.RoleCapabilityOverride`, una riga per coppia ruolo/capability modificata. In assenza di riga vale il default canonico in `core.capabilities.ROLE_DEFAULTS`.

Gli override sono letti dal database a ogni verifica server-side e a ogni richiesta della sessione: una modifica è quindi effettiva dalla richiesta successiva senza cache né riavvio. Admin riceve sempre l'intero catalogo; `data.reset`, `users.manage` e `privileges.manage` sono riservate e gli override per ruoli non-Admin vengono ignorati/rifiutati.

Le PATCH dei progetti espongono `version` ed `ETag` e richiedono la versione attesa tramite `If-Match` oppure `expected_version`. Una versione superata produce `409 risorsa-obsoleta`; una versione attesa assente produce `428 precondizione-richiesta`. Lo stesso contratto è definito dal meccanismo comune per i futuri editor Wallet. Ledger e consuntivi restano append-only.

## Catalogo canonico e default

| Capability | Admin | Responsabile BMED | Referente BMED | Fornitore |
|---|:---:|:---:|:---:|:---:|
| `data.reset` | Sì | — | — | — |
| `users.manage` | Sì | — | — | — |
| `privileges.manage` | Sì | — | — | — |
| `projects.create` | Sì | Sì | — | Sì |
| `projects.edit` | Sì | Sì | — | — |
| `projects.annotate_own` | Sì | Sì | Sì | — |
| `timesheets.create` | Sì | Sì | — | Sì |
| `wallet.edit` | Sì | Sì | — | — |
| `accounting.adjust` | Sì | Sì | — | — |
| `imports.upload` | Sì | Sì | — | Sì |
| `imports.apply` | Sì | Sì | — | — |
| `exports.run` | Sì | Sì | Sì | Sì |
| `anomalies.resolve` | Sì | Sì | — | — |

## Comportamento API implementato

| Operazione | Capability/verifica | Note |
|---|---|---|
| Creazione progetto | `projects.create` | Consentita anche al Fornitore. |
| Modifica progetto | `projects.edit` | Admin e Responsabile; lock ottimistico obbligatorio. |
| Annotazione proprio progetto | `projects.annotate_own` + object permission | Il Referente può modificare solo i campi di annotazione dei progetti associati. |
| Creazione/modifica allocazioni Wallet | `wallet.edit` | Non consentita al Fornitore. |
| Mutation contabili e conferma revisione | `accounting.adjust` | Non consentite a Referente e Fornitore. |
| Upload PPM in dry-run | `imports.upload` | Il Fornitore può caricare, ma la richiesta `apply` è forzata a dry-run. |
| Applicazione import | `imports.apply` | Admin e Responsabile; mai Fornitore. |
| Export | `exports.run` | Tutti i ruoli correnti. |
| Risoluzione anomalie | `anomalies.resolve` | Admin e Responsabile. |
| Gestione utenti | `users.manage` | CRUD, password, disattivazione ed eliminazione sicura; self-disable/self-delete e ultimo Admin protetti. |
| Gestione matrice ruoli | `privileges.manage` | Override persistenti solo per ruoli non-Admin e capability non riservate. |
| Import amministrativi | `privileges.manage` tramite `IsAdmin` | Solo Admin, preservando gli endpoint correnti. |
| Reset sicuro DB applicativo | `data.reset` | Solo Admin con controverifica digitata 'ELIMINA' e token di sicurezza effimero. |

Le letture di dashboard, progetti, Wallet, anomalie e riconciliazione restano disponibili a tutti i ruoli autenticati. La UI non costituisce un confine di sicurezza: una mutation non autorizzata riceve `403` anche se invocata direttamente.

## Gestione amministrativa e audit

Le API `/api/v1/admin/users`, `/api/v1/admin/users/{id}`, `/api/v1/admin/users/{id}/password` e `/api/v1/admin/roles/capabilities` sono protette server-side. Le risposte utente non serializzano mai password. La cancellazione fisica è ammessa soltanto per account diversi dall'attore, non ultimo Admin e senza riferimenti di dominio; in caso contrario risponde `409` indicando la disattivazione.

Creazione, modifica, password, eliminazione e variazione privilegi producono un `core.AdminAuditEvent` con attore, azione, destinatario, timestamp e metadati non segreti. Le password non vengono incluse nei dettagli di audit.
