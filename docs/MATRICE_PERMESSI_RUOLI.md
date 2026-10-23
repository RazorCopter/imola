# Matrice permessi per ruolo — Fase 7, Tranche 1

## Contratto

La sicurezza delle mutation è applicata dal backend tramite capability granulari. La sessione autenticata espone `capabilities` oltre ai campi legacy `roles`, `is_admin` e `can_write`; il frontend usa le capability e mantiene il fallback legacy solo durante il rollout. Le capability derivano in questa tranche da un catalogo statico associato ai gruppi Django esistenti, senza migrazioni.

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
| Gestione utenti/ruoli e import amministrativi | capability amministrative tramite `IsAdmin` | Solo Admin, preservando gli endpoint correnti. |

Le letture di dashboard, progetti, Wallet, anomalie e riconciliazione restano disponibili a tutti i ruoli autenticati. La UI non costituisce un confine di sicurezza: una mutation non autorizzata riceve `403` anche se invocata direttamente.
