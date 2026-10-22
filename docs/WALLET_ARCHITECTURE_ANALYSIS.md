# Analisi architetturale wallet

## Scopo e perimetro

Questo documento fotografa il modello corrente e valuta come rappresentare l'assegnazione delle giornate wallet a un architetto. È un'analisi: **non introduce campi, modelli o migrazioni** e non implementa FG-013/FG-014.

Domanda guida:

> Come rappresentiamo in modo contabile e auditabile che N giornate del wallet vengono riservate a una determinata attività/progetto e affidate a uno specifico architetto, mantenendo consumo, residuo e storico?

## Stato attuale dei modelli

Tutti i modelli descritti che ereditano da `TrackedModel` hanno UUID, `created_at`, `updated_at`, `created_by`, `updated_by` e `version`. Le FK autore puntano al modello utente Django configurato. I modelli in esame dichiarano inoltre `HistoricalRecords`, quindi dispongono dello storico di django-simple-history. `ImportedRecordMixin` collega i record creati dall'import al relativo batch.

### `WalletYear`

Contenitore annuale del wallet:

- `year`: intero positivo piccolo, univoco;
- `notes`: testo facoltativo;
- relazione inversa `allocations` da `WalletAllocation.wallet_year`;
- storico abilitato.

Non memorizza totali contabili materializzati: allocato, consumato e disponibile sono calcolati dai dati sottostanti.

### `WalletActivity`

Rappresenta la destinazione funzionale di un'allocazione:

- `code`: codice univoco;
- `title`;
- `kind`: `PROGETTO`, `ATTIVITA` o `REDMINE`;
- `project`: FK facoltativa e protetta a `Project`; è obbligatoria a livello di validazione applicativa quando `kind=PROGETTO`;
- `redmine_ref`;
- `client_owner`: FK facoltativa a `Person`, con `SET_NULL`, descritta come referente BMED;
- `supplier_owner`: FK facoltativa a `Person`, con `SET_NULL`, descritta come referente Imola;
- `notes`, `is_technical` e storico.

I due owner sono referenti dell'attività, non sono dichiarati come esecutori/architetti incaricati e non esprimono una quantità assegnata alla persona.

### `WalletAllocation`

È la scrittura che riserva una quantità alla destinazione:

- `wallet_year`: FK obbligatoria e protetta a `WalletYear`;
- `source_project`: FK facoltativa e protetta a `Project`, progetto da cui provengono le giornate;
- `activity`: FK obbligatoria e protetta a `WalletActivity`;
- `allocated_days`: giornate allocate, vincolate a essere non negative;
- `status`: `APERTA` o `CHIUSA`;
- `notes`;
- `external_ref`: riferimento di import, univoco quando non vuoto;
- `requires_source_attribution`: derivato in `save()` dall'assenza del progetto origine;
- `override_reason` e `override_by`: motivazione e FK facoltativa a `auth.User` per autorizzare uno sforamento;
- `is_technical` e storico.

`override_by` identifica chi autorizza un'eccezione, non l'architetto a cui sono affidate le giornate. Non esiste alcuna FK da `WalletAllocation` a `Person`.

### `TimesheetEntry`

Registro append-only del consumo:

- esattamente una fra le FK facoltative `project`, `canone_subactivity` e `wallet_allocation` deve essere valorizzata; il vincolo esiste sia in `clean()` sia nel database;
- `period`: primo giorno del mese di competenza;
- `days`: valore diverso da zero;
- `source`: `PPM_IMPORT`, `MANUALE`, `SEED_INIZIALE` o `STORNO`;
- `ppm_snapshot`: FK facoltativa allo snapshot PPM;
- `reverses`: FK facoltativa e protetta a un'altra `TimesheetEntry`, usata per lo storno;
- `note` e storico.

Il record non può essere aggiornato o cancellato: una correzione richiede un nuovo movimento di storno. Questa struttura rende auditabile il consumo complessivo dell'allocazione. Tuttavia, `TimesheetEntry` **non punta a `Person`**: non consente di sapere chi abbia prodotto le giornate.

### `Project`

Entità contabile e operativa del progetto:

- identificazione: `code` univoco, `title`, `contract_type`, `aro_code`, `rda_code`, `deliverable`;
- referenti: `client_owner` e `supplier_owner`, entrambe FK facoltative a `Person` con `SET_NULL`;
- quantità: `budget_days` e `released_to_wallet_days`;
- date: inizio, fine prevista e chiusura consuntivazione;
- stati distinti di offerta, consuntivazione e fatturazione;
- anno residuo derivato dalla chiusura, eventuale anno dichiarato, note, affidabilità/verifica e storico.

Relazioni con il wallet: un progetto può essere destinazione tramite `WalletActivity.project`, origine tramite `WalletAllocation.source_project` e bersaglio diretto di consuntivi tramite `TimesheetEntry.project`. Anche qui i referenti non equivalgono necessariamente all'architetto esecutore.

### `Person` e `User`

`Person` è l'anagrafica organizzativa:

- `full_name` e `name_key` normalizzata;
- FK obbligatoria e protetta a `Organization`;
- `email`, `is_active`, `needs_review`, `review_note` e storico;
- unicità del nome e della chiave normalizzata all'interno dell'organizzazione.

`User` è il modello Django auth usato per autenticazione, ruoli e attribuzione tecnica delle modifiche. Nel codice esaminato non esiste una relazione diretta `Person` ↔ `User`. Di conseguenza una persona di directory e un account autenticato sono concetti distinti; non si può inferirne l'identità dall'email o dal nome.

I referenti/responsabili di dominio osservati sono:

- `Project.client_owner` e `WalletActivity.client_owner`: referente BMED (`Person`);
- `Project.supplier_owner` e `WalletActivity.supplier_owner`: referente Imola (`Person`);
- `WalletAllocation.override_by`: utente autenticato che autorizza un override;
- campi ereditati `created_by`/`updated_by`: utenti autenticati che hanno creato/modificato il record.

Non è presente un ruolo persistito di “architetto assegnatario” sulle allocazioni o sui movimenti.

## Grafo delle FK effettive rilevanti

```text
WalletYear 1 ──< WalletAllocation >── 1 WalletActivity
                         │                    │
                         │ source_project?    │ project?
                         v                    v
                      Project <──────────── Project
                         ^
                         │ project?
TimesheetEntry ──────────┤
       │                 │
       └── wallet_allocation? ──> WalletAllocation

Project.client_owner? ───────────> Person <── WalletActivity.client_owner?
Project.supplier_owner? ─────────> Person <── WalletActivity.supplier_owner?
Person.organization ─────────────> Organization

WalletAllocation.override_by? ───> auth.User
TrackedModel.created_by/updated_by? ──> AUTH_USER_MODEL
TimesheetEntry.reverses? ─────────> TimesheetEntry
```

Le tre destinazioni di `TimesheetEntry` sono mutuamente esclusive. Non vi sono FK `WalletAllocation → Person`, `TimesheetEntry → Person` o `Person → User`.

## Contabilità disponibile oggi

La quantità riservata è `WalletAllocation.allocated_days`. Il consumo associato è la somma algebrica dei `TimesheetEntry.days` che puntano a quell'allocazione; gli storni restano nuove righe e preservano la traccia. Il residuo dell'allocazione è quindi concettualmente:

```text
residuo = allocated_days - somma(movimenti timesheet dell'allocazione)
```

La provenienza è `source_project` oppure wallet generale; la destinazione è `activity`, eventualmente collegata a `Project`. Stato e storico dell'allocazione, movimenti append-only e audit utente garantiscono una buona base contabile.

Ciò che manca è la dimensione “a chi sono affidate le giornate”. Oggi è possibile attestare che N giornate sono state riservate a una destinazione e quante ne sono state consumate, ma non che siano state affidate a una determinata `Person`, né chi abbia effettivamente consuntivato ogni movimento.

## Lacune da colmare

1. **Nessuna FK da allocazione a `Person`.** Non esiste un assegnatario della singola quantità riservata.
2. **Nessuna FK esecutore su `TimesheetEntry`.** Il consumo non è attribuibile a una persona.
3. **Gli owner non sono assegnazioni.** I referenti di progetto/attività esprimono responsabilità di coordinamento, non quantità affidate.
4. **Cardinalità non definita.** Non è deciso se un'allocazione possa essere ripartita tra più architetti o se un'attività abbia un solo architetto stabile.
5. **Temporalità dell'incarico assente.** Non esistono validità, riassegnazioni, chiusure o motivazioni specifiche dell'affidamento.
6. **Identità applicativa separata.** Senza legame `Person` ↔ `User`, autore della modifica e persona assegnataria non sono correlabili automaticamente.
7. **Consumo per persona non dimostrabile.** Anche aggiungendo l'assegnatario alla riserva, senza una regola per i movimenti non è possibile distinguere chi ha consumato cosa in assegnazioni multiple.

## Opzioni di modellazione

### Opzione A — FK `Person` su `WalletAllocation`

Aggiungere in futuro un'assegnazione facoltativa dell'allocazione a una persona.

**Pro**

- modello semplice e facilmente interrogabile;
- quantità, destinazione e assegnatario sono nello stesso record;
- il residuo continua a derivare dai movimenti dell'allocazione senza cambiare formula;
- adatto se ogni allocazione appartiene a un solo architetto; per ripartire si creano allocazioni distinte.

**Contro**

- la riassegnazione aggiornando la FK altera lo stato corrente; lo storico tecnico registra il cambio, ma non costituisce da solo un registro di incarichi con intervalli espliciti;
- più architetti richiedono duplicazione/ripartizione delle allocazioni e regole contro sovra-allocazione;
- `TimesheetEntry` continuerebbe a non registrare l'esecutore: lo si inferirebbe dall'allocazione corrente o storica;
- richiede decisioni su cancellazione persona, obbligatorietà e gestione di assegnazioni pregresse.

### Opzione B — FK `Person` su `WalletActivity`

Associare un architetto principale alla destinazione.

**Pro**

- molto semplice quando un'attività ha un unico responsabile stabile;
- evita ripetere l'assegnatario su ogni allocazione della stessa attività;
- utile come ownership operativa dell'attività.

**Contro**

- cardinalità troppo grossolana: tutte le allocazioni, gli anni e le fonti dell'attività erediterebbero la stessa persona;
- non rappresenta ripartizioni, sostituzioni temporali o assegnazioni differenti per tranche;
- confonde facilmente owner/referente con esecutore;
- una modifica dell'assegnatario dell'attività rende ambigua l'attribuzione dei consumi storici, se non si ricostruisce lo storico alla data del movimento.

### Opzione C — tabella bridge di assegnazione

Introdurre in futuro un'entità esplicita, per esempio concettualmente `WalletAssignment`, collegata a `WalletAllocation` e `Person`, con giornate assegnate, stato e validità. I movimenti potrebbero puntare alla specifica assegnazione oppure mantenere l'allocazione e aggiungere un riferimento coerente all'assegnazione.

**Pro**

- supporta più architetti sulla stessa allocazione e ripartizioni quantitative;
- consente vincoli contabili: somma delle giornate assegnate ≤ giornate allocate;
- rende riassegnazioni, periodi di validità, motivazioni e chiusure eventi di dominio espliciti;
- permette residuo totale per allocazione e residuo per persona;
- è l'opzione più adatta a uno storico auditabile senza sovrascrivere l'incarico precedente.

**Contro**

- maggiore complessità di modello, API, UI, validazioni e migrazione dati;
- deve essere definito come attribuire ogni `TimesheetEntry` a un'assegnazione; senza tale legame il consumo per persona resta ambiguo;
- richiede gestione di concorrenza, sovra-assegnazione, periodi sovrapposti e storni;
- occorre decidere se l'assegnazione sia immutabile/event-based o modificabile con history.

## Raccomandazione per il blocco successivo

Se il requisito ammette più architetti, riassegnazioni o rendicontazione individuale, la tabella bridge è la base più solida. Dovrebbe trattare separatamente:

1. **riserva contabile totale:** `WalletAllocation.allocated_days`;
2. **affidamento:** righe persona/quantità con validità e stato;
3. **consumo:** movimento append-only attribuito in modo non ambiguo all'affidamento;
4. **residui:** totale allocazione e quota per affidamento, sempre derivati;
5. **audit:** creazione/chiusura/rettifica tramite nuove scritture o storico esplicito, senza cancellare movimenti.

Se invece il vincolo di dominio certificato è “una allocazione, un solo architetto, nessuna attribuzione individuale del consuntivo”, la FK su allocation è l'alternativa minima. La FK su activity è consigliabile soltanto come ownership operativa, non come prova contabile dell'affidamento delle giornate.

Prima di implementare servono decisioni esplicite su cardinalità, riassegnazione, consumo per persona, relazione `Person`/`User`, gestione delle persone inattive e regole sugli storni. Nessuna delle opzioni è implementata in questo documento.