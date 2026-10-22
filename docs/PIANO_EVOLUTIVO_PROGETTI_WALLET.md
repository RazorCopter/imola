# Piano evolutivo — progetti, residui, wallet e amministrazione

**Stato:** proposta architetturale pronta per l’esecuzione incrementale; nessuna implementazione è inclusa in questo documento.  
**Data di riferimento:** 22 ottobre 2026.  
**Workbook autorevole:** [2026S1-OrgAllargatoProgetti-Situazione.xlsx](2026S1-OrgAllargatoProgetti-Situazione.xlsx).  
**Seed da rendere completo:** [seed_imola_2026-10-16.json](../data/seed/seed_imola_2026-10-16.json).  
**Evidenze di partenza:** [audit complessivo](audit202610222126.md), [gap analysis](FUNCTIONAL_GAP_ANALYSIS.md), [analisi wallet](WALLET_ARCHITECTURE_ANALYSIS.md), [analisi import storico](HISTORICAL_IMPORT_ANALYSIS.md), [matrice permessi](MATRICE_PERMESSI_RUOLI.md).

---

## 1. Decisione architetturale

Evolvere il sistema esistente senza riscriverlo, separando in modo esplicito quattro concetti oggi sovrapposti:

1. **saldo operativo di un progetto**: budget meno consuntivi diretti, anche mentre il progetto è attivo;
2. **lotto wallet**: fotografia immutabile del residuo positivo prodotta soltanto dalla chiusura valida di un progetto;
3. **iniziativa wallet**: destinazione con un proprio ciclo di vita, alla quale si richiedono e consumano giornate;
4. **quota assegnata**: porzione di un singolo lotto riservata a un’iniziativa, con provenienza e data di assegnazione preservate.

Le transizioni di progetto e le operazioni wallet devono passare da servizi applicativi transazionali. Le viste API non devono più modificare direttamente gli stati né replicare formule di dominio. I movimenti di consumo restano append-only, secondo il modello già presente in [`TimesheetEntry`](../backend/timesheets/models.py:34).

### Perché questa soluzione

- Riusa Django, Django REST Framework, lo storico, il locking ottimistico, i batch di import e il ledger già presenti.
- Elimina l’ambiguità tra “residuo di progetto attivo” e “credito wallet spendibile”.
- Rende verificabili FIFO, origine delle giornate, permanenza della quota assegnata e perdita alla chiusura.
- Evita microservizi, code, event sourcing generale o nuove dipendenze: non servono al volume e al contesto attuali.
- Consente una migrazione espandibile e reversibile prima di rimuovere i campi legacy.

---

## 2. Regole normative da congelare prima del codice

Queste regole costituiscono il contratto di dominio e devono diventare casi di test leggibili prima delle migrazioni.

1. Un progetto non scade per il solo trascorrere del tempo e può rimanere attivo per più anni.
2. La fine prevista è informativa e può produrre un controllo, ma non chiude né fa scadere il progetto.
3. Un residuo entra nel wallet solo quando il progetto è chiuso e possiede una data effettiva di chiusura.
4. Un progetto storicamente chiuso senza data resta in revisione, non produce lotto e non finanzia iniziative.
5. L’anno di nascita del lotto coincide con l’anno della data effettiva di chiusura.
6. Il lotto è assegnabile dalla data effettiva di chiusura fino al 31 dicembre dell’anno successivo incluso.
7. Dal primo gennaio seguente il lotto non assegnato è scaduto.
8. La quota assegnata in tempo a un’iniziativa ancora aperta resta consumabile anche dopo la scadenza del lotto sorgente.
9. Le richieste usano FIFO per data di scadenza; a parità, per data di nascita, codice progetto e identificativo stabile.
10. Una richiesta può generare più quote, ciascuna legata a un solo lotto.
11. Alla chiusura di un’iniziativa, il non consumato proveniente da un lotto ormai scaduto è perso e non torna nel basket.
12. Nessun consumo, storno, assegnazione o chiusura può aggiornare o cancellare righe di consuntivo esistenti.
13. Nessun numero contabile viene calcolato nel browser: il frontend mostra importi e spiegazioni restituiti dall’API.
14. Tutti i comandi mutativi sono autorizzati dal backend, atomici, auditabili e protetti da concorrenza.

### Assunzioni da ratificare nel Blocco 0

Sono necessarie per chiudere il contratto, ma non vanno nascoste nell’implementazione:

- **Restituzione da lotto ancora valido:** alla chiusura dell’iniziativa, il non consumato torna disponibile nello stesso lotto se il lotto è ancora valido alla data effettiva di chiusura. È la scelta raccomandata perché conserva il significato del basket ed è complementare alla perdita già confermata per i lotti scaduti.
- **Attribuzione dei consumi multi-lotto:** i consumi di un’iniziativa vengono distribuiti sulle sue quote secondo la stessa priorità FIFO per scadenza, poi per data di assegnazione e identificativo. È necessaria per determinare in modo ripetibile quale origine resta inutilizzata.
- **Sospensione e riapertura:** non introdurre nuovi stati senza una regola approvata. Il primo rilascio usa gli stati già presenti; la chiusura ordinaria di progetto e iniziativa è irreversibile. Le rettifiche avvengono con comandi amministrativi compensativi, non riscrivendo lo storico.
- **Validità configurabile:** la regola confermata equivale a un solo anno successivo. Il campo storico [`AppSettings.residual_years_after_closure`](../backend/core/models.py:92) resta temporaneamente leggibile per compatibilità, ma viene bloccato al valore 1 e non governa nuovi lotti finché il processo normativo non autorizza una durata diversa.

**Stop decisionale:** nessuna migrazione distruttiva e nessuna nuova assegnazione wallet prima che queste quattro assunzioni siano registrate come approvate o sostituite.

---

## 3. Stato corrente e correzioni necessarie

| Area | Base riutilizzabile | Incoerenza o mancanza da correggere |
|---|---|---|
| Progetto | [`Project`](../backend/projects/models.py:59), date, tre stati separati, audit e revisione | [`Project.released_to_wallet_days`](../backend/projects/models.py:89) abilita il rilascio da progetto attivo; gli stati sono modificati direttamente dalle viste; manca una macchina di transizione unica. |
| Residui | [`last_usable_day()`](../backend/domain/residuals.py:52), query annotate e spiegazioni | [`residual_validity()`](../backend/domain/residuals.py:57) qualifica come valido anche il saldo di un progetto non chiuso; [`projects_with_usable_residual()`](../backend/domain/residuals.py:215) può esporlo come spendibile. |
| Wallet | [`WalletActivity`](../backend/wallet/models.py:45), [`WalletAllocation`](../backend/wallet/models.py:104), provenienza progetto e ledger dei consumi | Manca un lotto esplicito, un lifecycle dell’iniziativa, la data di assegnazione, una disposizione di restituzione/perdita e un servizio FIFO. |
| API | Autenticazione, problem details, permessi, audit e locking ottimistico | [`ReleaseProjectToWalletView.post()`](../backend/api/domain_views.py:334) accetta progetti attivi; [`ProjectConfirmReviewView.post()`](../backend/api/domain_views.py:618) modifica campi senza servizio di transizione; [`domain_views.py`](../backend/api/domain_views.py) concentra troppe responsabilità. |
| Timesheet | [`TimesheetEntry`](../backend/timesheets/models.py:34), storni e vincoli append-only | Mancano API e UI complete per elenco, inserimento e storno; il consumo di un’iniziativa multi-lotto deve essere suddiviso deterministicamente. |
| Frontend progetti | [NewProjectDialog.tsx](../frontend/src/features/projects/NewProjectDialog.tsx), [ProjectsPage.tsx](../frontend/src/features/projects/ProjectsPage.tsx), [ProjectDetailPage.tsx](../frontend/src/features/projects/ProjectDetailPage.tsx) | Creazione incompleta, tab placeholder, nessun workflow di offerta/avvio/chiusura, nessun ledger operativo. |
| Frontend wallet | [WalletPage.tsx](../frontend/src/features/wallet/WalletPage.tsx) | Nessuna creazione iniziativa, anteprima FIFO, consumo/storno o chiusura con restituzioni e perdite. |
| Impostazioni | [`AppSettings`](../backend/core/models.py:63), [`SettingsView`](../backend/api/domain_views.py:53) | Nessuna pagina; amministrazione e impostazioni sono oggi confuse; [CommandPalette.tsx](../frontend/src/components/CommandPalette.tsx:10) punta a una route rimossa. |
| Import | Batch, dry-run, apply, issue e rollback in [backend/importers](../backend/importers/) | Il converter Excel non esiste; il seed copre circa 40 progetti a fronte di circa 130 righe progetto; manca tracciabilità lossless foglio/riga. |
| Test | Suite backend ampia, test frontend ed E2E reali iniziali | I test correnti codificano anche la semantica superata e gli E2E seriali consumano lo stato condiviso. |

---

## 4. Modello target minimo

### 4.1 Progetto

Conservare [`Project`](../backend/projects/models.py:59) come aggregato anagrafico e operativo. Nel percorso ordinario gli stati ammessi sono:

- offerta: INVIATA → ACCETTATA, NON_ACCETTATA oppure SCADUTA;
- consuntivazione: NON_AVVIATO → ATTIVO → CHIUSO;
- revisione storica: DA_VERIFICARE → stato validato mediante comando dedicato;
- fatturazione: resta indipendente dal lifecycle operativo.

Vincoli applicativi:

- l’avvio richiede offerta accettata e data di inizio;
- la chiusura richiede stato ATTIVO, data effettiva, motivo e versione attesa;
- la chiusura non può precedere l’inizio;
- dopo la chiusura non sono consentiti nuovi consuntivi diretti;
- il residuo di chiusura è budget meno somma netta dei consuntivi diretti;
- un residuo positivo crea un lotto; zero o negativo non crea credito e lo sforamento resta visibile nei controlli;
- la coppia progetto–lotto è univoca, rendendo la chiusura idempotente.

[`Project.released_to_wallet_days`](../backend/projects/models.py:89) deve essere deprecato nella fase di espansione, escluso da tutte le formule nuove e rimosso solo dopo backfill e riconciliazione.

### 4.2 Lotto wallet

Introdurre [`WalletLot`](../backend/wallet/models.py:1) con soli dati derivati dal contratto:

- progetto sorgente univoco e protetto;
- giornate iniziali positive, congelate alla chiusura;
- data di nascita uguale alla chiusura effettiva;
- anno di riferimento derivato dalla nascita;
- ultimo giorno assegnabile memorizzato alla creazione;
- affidabilità e riferimento al batch di import, riusando i mixin esistenti;
- storico e metadati standard di [`TrackedModel`](../backend/core/models.py:22).

Lo stato VALIDO, IN_SCADENZA o SCADUTO è calcolato rispetto a una data, non salvato. La scadenza memorizzata non viene ricalcolata quando cambiano impostazioni future.

Disponibilità basket di un lotto a una data:

**giornate iniziali − quote assegnate + restituzioni valide**

Il risultato spendibile è zero se il lotto è scaduto o non affidabile. Le quote già assegnate non rientrano nel basket solo perché la sorgente scade.

### 4.3 Iniziativa wallet

Evolvere [`WalletActivity`](../backend/wallet/models.py:45), mantenendo codice, titolo, tipo, progetto/ticket e referenti, con:

- stato APERTA, CHIUSA o DA_VERIFICARE per il backfill storico;
- data apertura;
- data chiusura effettiva facoltativa;
- motivo di chiusura;
- versione per concorrenza già ereditata.

Regole:

- solo un’iniziativa APERTA riceve assegnazioni e consumi;
- la chiusura è atomica e dispone tutto il non consumato;
- una iniziativa CHIUSA non accetta operazioni ordinarie;
- la modifica anagrafica non cambia saldi o provenienze.

### 4.4 Quota assegnata

Evolvere [`WalletAllocation`](../backend/wallet/models.py:104) in quota immutabile:

- riferimento obbligatorio al lotto;
- riferimento all’iniziativa;
- giornate assegnate positive;
- data/ora di assegnazione ed eventuale data efficace;
- anno/contenitore di reporting mantenuto per compatibilità, ma non usato come origine del credito;
- motivo, autore, affidabilità e batch.

La richiesta di N giornate può creare più quote. Le quote non vengono “ridotte al consumato”: consumi e disposizioni spiegano il loro saldo.

### 4.5 Restituzione e perdita

Introdurre [`WalletAllocationDisposition`](../backend/wallet/models.py:1) come ledger append-only collegato alla quota:

- tipo RESTITUITA oppure PERSA;
- giornate positive;
- data efficace;
- motivo obbligatorio;
- autore e audit.

Alla chiusura dell’iniziativa, per ogni quota:

- residuo quota = assegnato − consumo netto − disposizioni già registrate;
- se residuo zero, nessun movimento;
- se il lotto è valido alla data di chiusura, registrare RESTITUITA;
- altrimenti registrare PERSA.

La somma di consumo netto e disposizioni non può superare l’assegnato. Il vincolo trasversale è verificato nel servizio sotto lock; i vincoli locali di positività e tipo sono anche a database.

### 4.6 Consumi e storni

Conservare [`TimesheetEntry`](../backend/timesheets/models.py:34) senza update e delete. I servizi applicativi devono:

- registrare un consumo diretto su progetto soltanto finché è operativo;
- registrare un consumo wallet distribuendolo sulle quote aperte secondo FIFO;
- creare una riga per quota coinvolta;
- creare storni con [`TimesheetEntry.build_reversal()`](../backend/timesheets/models.py:162), senza modificare l’originale;
- rifiutare un consumo che supera il saldo assegnato dell’iniziativa;
- su iniziativa chiusa consentire solo una rettifica amministrativa compensativa, che nello stesso comando crea lo storno e la nuova disposizione necessaria, senza riaprire né riscrivere la chiusura.

---

## 5. Servizi applicativi e confini transazionali

Creare moduli piccoli, senza introdurre un framework di command bus:

- [`backend/projects/services.py`](../backend/projects/services.py): creazione completa, transizioni offerta, avvio, anteprima e chiusura progetto, revisione storica;
- [`backend/wallet/services.py`](../backend/wallet/services.py): anteprima FIFO, assegnazione, consumo, storno, anteprima chiusura e chiusura iniziativa;
- [`backend/timesheets/services.py`](../backend/timesheets/services.py): primitive append-only condivise e validazioni del target;
- [`backend/domain/wallet_balance.py`](../backend/domain/wallet_balance.py): sole query/formule di lettura sul nuovo modello;
- [`backend/domain/residuals.py`](../backend/domain/residuals.py): saldo progetto e validità lotto separati.

Ogni comando contabile deve:

1. aprire una transazione;
2. controllare ruolo e ownership a livello API;
3. verificare la versione attesa;
4. acquisire lock sulle righe progetto, iniziativa, lotto e quote interessate in ordine stabile;
5. ricalcolare il saldo dentro la transazione;
6. validare la richiesta senza fidarsi dell’anteprima;
7. scrivere tutti o nessun record;
8. restituire saldo aggiornato, spiegazione e nuova versione.

### Chiusura progetto

Un unico servizio deve, atomicamente:

- validare la transizione e la data;
- calcolare il consumo diretto netto;
- produrre l’anteprima del residuo;
- impostare stato e data di chiusura;
- creare al massimo un lotto positivo;
- non creare lotto se il residuo è nullo o negativo;
- registrare audit e far emergere eventuale anomalia di sforamento.

Nessun endpoint separato deve più “rilasciare” giornate da un progetto attivo. La route corrente collegata a [`ReleaseProjectToWalletView`](../backend/api/domain_views.py:328) va prima disabilitata semanticamente e poi rimossa dopo il periodo di compatibilità.

### Assegnazione FIFO

L’anteprima e il comando usano lo stesso selettore. Per una richiesta D alla data T:

1. selezionare solo lotti affidabili, nati entro T, non scaduti a T e con disponibilità positiva;
2. ordinare per scadenza, nascita, codice progetto e identificativo;
3. prendere da ciascun lotto il minimo tra disponibilità e fabbisogno restante;
4. fallire integralmente se la somma non copre D;
5. in esecuzione ripetere selezione e calcolo sotto lock;
6. creare una quota per ciascun lotto usato.

La risposta espone sorgente, scadenza, giorni prima/dopo e totale; nessun arrotondamento usa valori floating point.

### Chiusura iniziativa

Anteprima e comando condividono il calcolo. Il comando chiude una sola volta e crea disposizioni per ogni quota residua. Un doppio invio con stessa chiave idempotente restituisce l’esito precedente; un secondo invio incompatibile risponde con conflitto.

---

## 6. Contratti API target

Le route definitive possono essere distribuite in più moduli sotto [backend/api](../backend/api/) per ridurre il monolite corrente. Tutte restituiscono decimali come stringhe, date ISO, versione e permessi oggetto; gli errori restano problem details.

### Progetti

- **GET /projects**: filtri per offerta, stato operativo, fatturazione, referente e revisione.
- **POST /projects**: crea l’anagrafica completa; non accetta stati incoerenti impliciti.
- **GET /projects/{id}**: dettaglio, azioni ammesse, saldi spiegati, lotto collegato, milestone, ledger e audit.
- **PATCH /projects/{id}**: modifica solo dati anagrafici/annotazioni consentiti; non modifica stati contabili.
- **POST /projects/{id}/actions/{azione}/preview**: valida senza scrivere, in particolare la chiusura.
- **POST /projects/{id}/actions/{azione}**: comandi ACCETTA_OFFERTA, RIFIUTA_OFFERTA, SCADI_OFFERTA, AVVIA, CHIUDI e CONFERMA_REVISIONE.
- **GET e POST /projects/{id}/timesheets**: elenco e inserimento manuale.
- **POST /timesheets/{id}/reverse**: storno append-only con motivo.

Payload minimo dei comandi: versione attesa, data efficace quando pertinente, motivo; intestazione di idempotenza per le mutation contabili. Le risposte includono progetto aggiornato e side effect creati.

### Wallet

- **GET /wallet/lots**: lotti, stato calcolato, disponibile e spiegazione.
- **GET /wallet/years/{year}/balance**: basket non assegnato, quote aperte consumabili, consumato, restituito e perso senza doppio conteggio.
- **GET e POST /wallet/activities**: elenco e creazione iniziative.
- **GET e PATCH /wallet/activities/{id}**: dettaglio e soli dati descrittivi.
- **POST /wallet/activities/{id}/allocation-preview**: scomposizione FIFO senza scrittura.
- **POST /wallet/activities/{id}/allocate**: assegnazione atomica multi-lotto.
- **POST /wallet/activities/{id}/consume**: consumo, eventualmente suddiviso su più quote.
- **POST /wallet/timesheets/{id}/reverse**: storno append-only.
- **POST /wallet/activities/{id}/close-preview**: restituzioni e perdite previste.
- **POST /wallet/activities/{id}/close**: chiusura e disposizioni atomiche.

L’endpoint legacy di regolazione collegato a [`WalletAllocationAdjustView.post()`](../backend/api/domain_views.py:652) viene ritirato: una quota assegnata non viene riscritta per farla coincidere con il consumo.

### Impostazioni e amministrazione

- **GET /settings**: leggibile da tutti gli autenticati.
- **PATCH /settings**: solo Admin, allowlist esplicita, versione attesa, validazione e audit; la durata residuo resta bloccata a 1 in questa release.
- **GET /admin/imports**: elenco batch e report, solo Admin; Fornitore vede soltanto i propri dry-run PPM secondo le regole esistenti.
- **POST /admin/imports/historical/dry-run**: upload Excel, mai applicazione implicita.
- **POST /admin/imports/{batch}/apply**: applicazione esplicita solo Admin su hash del file già validato.
- **POST /admin/imports/{batch}/rollback**: solo quando [`rollback_seed()`](../backend/importers/rollback.py:87) dichiara il batch annullabile.
- **GET /admin/audit** e gestione utenti/ruoli: capability amministrative separate dalle impostazioni di dominio.

### Errori attesi

- 400 per payload o date non validi;
- 403 per capability negata;
- 404 senza divulgare oggetti non visibili;
- 409 per versione obsoleta, transizione illegale, idempotenza incompatibile o saldo cambiato dall’anteprima;
- 422 per richiesta contabilmente valida nel formato ma non soddisfacibile, con saldo e deficit;
- nessun errore espone stack trace, path server o contenuto completo dei file caricati.

---

## 7. Permessi

La matrice corrente resta la base, ma va estesa prima di esporre le nuove route.

| Capability | Admin | Responsabile BMED | Referente BMED | Fornitore |
|---|---:|---:|---:|---:|
| Lettura progetti, wallet, impostazioni | sì | sì | sì, nel perimetro previsto | sì, nel perimetro previsto |
| Creazione/transizioni progetto | sì | sì | no | no |
| Annotazioni proprio progetto | sì | sì | sì | no |
| Consuntivi manuali e storni ordinari | sì | sì | no | no |
| Creazione/assegnazione/consumo/chiusura iniziativa | sì | sì | no | no |
| Rettifiche su entità chiuse | sì | no | no | no |
| Modifica impostazioni | sì | no | no | no |
| Import storico apply/rollback | sì | no | no | no |
| Upload PPM dry-run | sì | sì | no | sì |
| Gestione utenti e ruoli | sì | no | no | no |

Azioni nascoste nel frontend migliorano l’esperienza ma non costituiscono sicurezza. Aggiornare [`core/permissions.py`](../backend/core/permissions.py), [`session_payload()`](../backend/api/auth_views.py:36) e [permissions.ts](../frontend/src/lib/permissions.ts) con capability esplicite quando il solo campo can_write non basta.

---

## 8. Migrazione dati: expand, backfill, validate, contract

La migrazione non deve inventare provenienze o date. Ogni ambiguità genera un record di revisione e resta fuori dal disponibile ufficiale.

### 8.1 Expand

- Aggiungere lotto, lifecycle iniziativa, riferimento quota→lotto, data assegnazione e disposizioni come campi/tabelle inizialmente compatibili con i dati legacy.
- Aggiungere indici su scadenza lotto, stato iniziativa, lotto della quota e date efficaci.
- Mantenere temporaneamente [`Project.released_to_wallet_days`](../backend/projects/models.py:89), origine progetto e stato legacy dell’allocazione.
- Estendere storico, admin, factory ed export prima di fare backfill.

### 8.2 Inventario e classificazione

Produrre un report immutabile con conteggi e chiavi per:

- progetti chiusi con data e residuo positivo;
- progetti chiusi senza data;
- progetti attivi con released_to_wallet_days maggiore di zero;
- allocazioni con origine chiusa valida;
- allocazioni con origine attiva, assente o ambigua;
- iniziative con evidenza certa o incerta di apertura/chiusura;
- consumo netto maggiore della quota;
- record tecnici e storici introdotti dal seed.

Il caso PROGETTO_DEMO e ogni altra rettifica D-16 non possono diventare automaticamente lotti validi da progetto attivo. Devono essere riconciliati con il workbook o quarantinati.

### 8.3 Backfill conservativo

- Creare un lotto solo per un progetto chiuso con data, residuo positivo e provenienza verificabile.
- Usare la data effettiva per nascita, anno e scadenza.
- Collegare una quota legacy al lotto solo se sorgente, giorni e cronologia sono coerenti.
- Usare created_at come data di assegnazione solo se la provenienza del record ne garantisce il significato; altrimenti segnare DA_VERIFICARE.
- Impostare iniziativa APERTA o CHIUSA soltanto con evidenza; in assenza usare DA_VERIFICARE.
- Non far rientrare lotti, quote o iniziative DA_VERIFICARE nei saldi spendibili.
- Conservare il riferimento al batch e una mappa prima/dopo per rollback e audit.

### 8.4 Validazione

Per ogni progetto e iniziativa confrontare:

- budget e consumo netto;
- residuo di chiusura e lotto iniziale;
- totale quote per sorgente;
- consumi per quota;
- restituzioni/perdite;
- saldo prima e dopo, spiegando ogni differenza.

La migrazione si ferma se esistono saldi negativi non spiegati, quote orfane, duplicati progetto–lotto o differenze aggregate oltre la tolleranza configurata.

### 8.5 Contract

Solo dopo due esecuzioni idempotenti e riconciliazione approvata:

- rendere obbligatorio il lotto sulle quote nuove;
- rimuovere le letture dei campi legacy;
- rimuovere endpoint di release/adjust;
- eliminare [`Project.released_to_wallet_days`](../backend/projects/models.py:89) e gli stati allocazione sostituiti in una migrazione separata;
- mantenere una vista/export di compatibilità se necessaria per audit storico.

Il rollback applicativo deve tornare alla release precedente senza perdita; una migrazione distruttiva parte solo dopo backup verificato e chiusura della finestra di rollback del backfill.

---

## 9. Riconciliazione Excel → JSON

Il workbook è la fonte completa; il JSON deve essere una rappresentazione ripetibile e tracciabile, non una selezione editoriale.

### Pipeline raccomandata

1. **Acquisizione:** calcolare hash, dimensione e lista fogli del workbook; conservare nome originale e data di elaborazione.
2. **Estrazione raw:** leggere i fogli info, OA-attività S1, OA-attività S2, Progetti, Wallet proposta e Capacity Mensile, mantenendo numero riga, celle originali, tipo, formula e valore materializzato se presente.
3. **Normalizzazione:** applicare alias dichiarativi per intestazioni, persone, codici e stati; non correggere silenziosamente.
4. **Classificazione:** trasformare ogni riga in entità, duplicato, esclusione motivata, warning o errore.
5. **Risoluzione formule:** usare il valore cached quando presente; se manca, calcolare solo formule esplicitamente supportate oppure bloccare la riga come non verificabile. Non assumere che openpyxl calcoli formule.
6. **Produzione seed:** generare un nuovo schema versionato con metadati di provenienza per entità e Decimal serializzati come stringhe compatibili.
7. **Validazione:** schema, chiavi uniche, riferimenti, somme per foglio, conteggi e invarianti di dominio.
8. **Diff:** confrontare workbook, seed corrente e database con report machine-readable e leggibile.
9. **Dry-run/apply:** riusare [`dry_run_seed()`](../backend/importers/batch.py:106), [`apply_seed()`](../backend/importers/batch.py:123), issue e rollback; nessun apply diretto dal converter.

### Tracciabilità obbligatoria

Ogni entità generata deve indicare almeno:

- hash e nome della sorgente;
- foglio e riga o intervallo di righe;
- chiave naturale originale;
- regole/alias applicati;
- eventuali formule e valore usato;
- affidabilità;
- motivo di esclusione o merge, quando applicabile.

Mantenere un file di mapping dichiarativo versionato, non condizioni sparse nel parser. Aggiornare [HISTORICAL_IMPORT_ANALYSIS.md](HISTORICAL_IMPORT_ANALYSIS.md) eliminando l’affermazione obsoleta che il workbook non è disponibile.

### Criteri quantitativi

- Il report spiega il 100% delle righe non vuote dei fogli inclusi.
- Il numero di progetti non è imposto a circa 130: deve coincidere con le righe classificate dopo duplicati ed esclusioni esplicite.
- Ogni riga esclusa ha codice motivo e coordinate.
- Totali di budget, allocato e consumato sono confrontati per foglio e globalmente.
- Due esecuzioni sullo stesso hash producono seed e report semanticamente identici.
- L’import ripetuto del seed non crea duplicati.

---

## 10. Piano di implementazione incrementale

Ogni blocco produce un incremento verificabile. Non iniziare il blocco successivo se la relativa stop condition non è soddisfatta, salvo lavoro preparatorio che non dipende dal risultato.

### Blocco 0 — Contratto eseguibile e baseline

**Dipendenze:** nessuna.  
**File principali:** questo piano, [DECISIONI_APERTE.md](DECISIONI_APERTE.md), [MATRICE_PERMESSI_RUOLI.md](MATRICE_PERMESSI_RUOLI.md), test di dominio esistenti.

**Attività**

- Registrare le regole normative e risolvere le quattro assunzioni della sezione 2.
- Scrivere esempi tabellari 2024–2027, chiusura senza data, FIFO multi-lotto, quota assegnata oltre scadenza, restituzione e perdita.
- Congelare fixture e conteggi baseline di database, workbook e seed.
- Inventariare endpoint/client che usano release e adjust legacy.
- Definire la matrice transizioni e la matrice permessi target.

**Test/evidenze:** nuovi test puri inizialmente rossi o marcati come specifica; snapshot dei report baseline; nessuna modifica dati.  
**Criterio di accettazione:** ogni regola ha almeno un esempio positivo e uno negativo, proprietario e fonte.  
**Rischio:** implementare una scelta implicita e dover migrare due volte.  
**Stop condition:** assunzioni approvate, baseline archiviata, nessuna contraddizione aperta su chiusura/FIFO.

### Blocco 1 — Correzione semantica senza nuova UI

**Dipendenze:** Blocco 0.  
**File principali:** [residuals.py](../backend/domain/residuals.py), [wallet_balance.py](../backend/domain/wallet_balance.py), [checks.py](../backend/domain/checks.py), [domain_views.py](../backend/api/domain_views.py), test di residui e wallet.

**Attività**

- Separare saldo progetto da spendibilità wallet.
- Escludere progetti attivi e chiusi senza data dalle fonti spendibili.
- Bloccare release da progetto attivo con errore esplicito e deprecare la route.
- Correggere il controllo “allocazione da scaduto”: è anomala solo se assegnata dopo la scadenza o senza prova della data, non perché la sorgente è scaduta oggi.
- Adeguare bilanci e descrizioni API senza ancora creare il modello nuovo.

**Test/evidenze:** aggiornare intenzionalmente [test_residuals.py](../backend/tests/domain/test_residuals.py), [test_wallet_balance.py](../backend/tests/domain/test_wallet_balance.py), [test_phase2_refinements.py](../backend/tests/test_phase2_refinements.py).  
**Criterio di accettazione:** nessun progetto attivo aumenta il disponibile wallet; i chiusi senza data sono solo in revisione; il saldo progetto resta visibile.  
**Rischio:** dashboard e fixture seed cambiano valori; il cambiamento deve essere dichiarato, non mascherato.  
**Stop condition:** test di dominio/API verdi con semantica nuova e report delle differenze attese.

### Blocco 2 — Modello lotto, lifecycle e migrazione espansiva

**Dipendenze:** Blocchi 0–1.  
**File principali:** [wallet/models.py](../backend/wallet/models.py), [projects/models.py](../backend/projects/models.py), nuove migrazioni wallet/progetti, [factories.py](../backend/tests/factories.py), admin ed export.

**Attività**

- Introdurre lotto, lifecycle iniziativa, quota collegata al lotto e disposizione.
- Aggiungere constraint locali, indici, storico e registrazione admin.
- Rendere i nuovi campi compatibili col legacy durante l’espansione.
- Scrivere comando/report di classificazione e backfill dry-run.
- Non rimuovere ancora campi o endpoint esistenti.

**Test/evidenze:** model validation, constraint database, storico, query plan sui filtri principali, migrazione avanti/indietro su copia dati.  
**Criterio di accettazione:** schema nuovo installabile senza cambiare saldi o perdere record; inventario classifica ogni record legacy.  
**Rischio:** attribuzione artificiale di date/origini; mitigazione con DA_VERIFICARE.  
**Stop condition:** backup ripristinabile, dry-run senza record inspiegati, migrazione reversibile.

### Blocco 3 — Servizi atomici di progetto e FIFO

**Dipendenze:** Blocco 2.  
**File principali:** nuovi [projects/services.py](../backend/projects/services.py), [wallet/services.py](../backend/wallet/services.py), [timesheets/services.py](../backend/timesheets/services.py), domini residui/wallet.

**Attività**

- Implementare macchina di stato progetto e anteprime.
- Rendere chiusura progetto e creazione lotto un’unica transazione idempotente.
- Implementare selezione e split FIFO sotto lock.
- Implementare consumo multi-quota, storno, chiusura iniziativa e disposizioni.
- Ricalcolare saldi esclusivamente dai ledger.

**Test/evidenze:** test unitari delle transizioni, transazionali, concorrenza con due richieste sul medesimo lotto, rollback su errore intermedio, property test sui vincoli contabili se già supportati senza nuova dipendenza.  
**Criterio di accettazione:** nessun oversubscription anche con richieste concorrenti; chiusura doppia non duplica lotto o disposizioni.  
**Rischio:** deadlock; mitigare con ordine di lock deterministico e transazioni brevi.  
**Stop condition:** invarianti contabili dimostrate e nessuna scrittura stato fuori dai servizi.

### Blocco 4 — API applicative e compatibilità

**Dipendenze:** Blocco 3.  
**File principali:** [backend/api](../backend/api/), [urls.py](../backend/api/urls.py), [permissions.py](../backend/core/permissions.py), schema OpenAPI e test API.

**Attività**

- Esporre comandi e anteprime descritti nella sezione 6.
- Separare viste progetto, wallet, timesheet, settings e admin.
- Applicare capability, ownership, versione e idempotenza.
- Mantenere temporaneamente endpoint GET compatibili; marcare mutation legacy deprecate e poi rispondere 409/410 secondo finestra concordata.
- Aggiornare OpenAPI e client types.

**Test/evidenze:** contratti request/response, 401/403/404/409/422, object permission, idempotenza e nessun side effect sui fallimenti.  
**Criterio di accettazione:** tutte le mutation UI future sono disponibili e nessuna consente di saltare il servizio.  
**Rischio:** differenza tra permesso mostrato e applicato; testare ogni ruolo su ogni comando.  
**Stop condition:** schema OpenAPI valido, matrice API verde, endpoint legacy censiti.

### Blocco 5 — UI progetti e timesheet

**Dipendenze:** Blocco 4.  
**File principali:** [NewProjectDialog.tsx](../frontend/src/features/projects/NewProjectDialog.tsx), [ProjectDetailPage.tsx](../frontend/src/features/projects/ProjectDetailPage.tsx), [ProjectsPage.tsx](../frontend/src/features/projects/ProjectsPage.tsx), [ReviewQueuePage.tsx](../frontend/src/features/review/ReviewQueuePage.tsx).

**Attività**

- Completare creazione con dati obbligatori, owner e validazione server.
- Sostituire placeholder con panoramica, milestone, documenti se supportati, consuntivi, anomalie e storico.
- Mostrare solo azioni ammesse: accetta/rifiuta/scadi offerta, avvia, chiudi.
- Prima della chiusura mostrare anteprima residuo, lotto o sforamento e richiedere conferma.
- Aggiungere elenco consuntivi, inserimento manuale e storno con motivo.
- Rafforzare revisione con data obbligatoria, errori inline e feedback persistente.

**Test/evidenze:** component test, accessibilità tastiera/label/focus, E2E reali con reload e verifica API/database indiretta.  
**Criterio di accettazione:** un Responsabile completa il lifecycle senza admin Django; un Referente annota solo il proprio progetto; un Fornitore non muta.  
**Rischio:** form troppo ampio; usare passi coerenti senza nascondere errori server.  
**Stop condition:** workflow nominale e casi negati passano in database isolato.

### Blocco 6 — UI wallet e iniziative

**Dipendenze:** Blocchi 4–5.  
**File principali:** [WalletPage.tsx](../frontend/src/features/wallet/WalletPage.tsx), nuove pagine/componenti sotto [frontend/src/features/wallet](../frontend/src/features/wallet/).

**Attività**

- Separare vista basket lotti, iniziative e flusso contabile.
- Creare iniziativa con tipo, riferimenti, owner e data apertura.
- Richiedere giornate mostrando anteprima FIFO e split per sorgente.
- Registrare consumi/storni mostrando a quali quote sono attribuiti.
- Chiudere con anteprima distinta tra restituito e perso.
- Mostrare quote assegnate ancora consumabili anche se il lotto sorgente è ormai scaduto.

**Test/evidenze:** component test di saldi/decimali, E2E multi-lotto, oltre-scadenza, perdita e restituzione.  
**Criterio di accettazione:** l’utente può ricostruire per ogni giornata origine, destinazione, consumo ed esito finale.  
**Rischio:** doppio conteggio tra basket e quote; confrontare ogni card col payload server.  
**Stop condition:** tutti gli scenari 2024–2027 hanno saldo finale atteso e persistenza dopo reload.

### Blocco 7 — Pannello Impostazioni e Amministrazione

**Dipendenze:** Blocco 4; può procedere in parallelo al Blocco 6 dopo stabilizzazione API.  
**File principali:** [App.tsx](../frontend/src/App.tsx), [AppShell.tsx](../frontend/src/components/AppShell.tsx), [CommandPalette.tsx](../frontend/src/components/CommandPalette.tsx), nuove feature settings/admin.

**Attività**

- Creare pagina Impostazioni visibile a tutti in lettura, con edit solo Admin.
- Mostrare descrizione, unità, valore corrente, impatto e audit; salvare con versione.
- Rendere la durata del residuo read-only e pari a 1 per questa release.
- Creare area Amministrazione separata per import/export, batch, rollback, audit, utenti/ruoli e controlli.
- Riallineare menu, route, command palette e capability.
- Chiedere conferma rafforzata per apply, rollback e modifiche sensibili.

**Test/evidenze:** route guard UX, API 403 reali, conflitto versione, audit del cambio, test menu per ruolo.  
**Criterio di accettazione:** nessun non-Admin modifica impostazioni o vede comandi amministrativi azionabili; URL diretto non aggira l’API.  
**Rischio:** confondere configurazione con operazioni; mantenere due sezioni e permessi distinti.  
**Stop condition:** matrice ruoli aggiornata e verificata frontend/backend.

### Blocco 8 — Converter e riconciliazione Excel/JSON

**Dipendenze:** modello target e schema seed stabilizzati nei Blocchi 2–4.  
**File principali:** nuovi moduli sotto [backend/importers](../backend/importers/), schema seed versionato, [seed_imola_2026-10-16.json](../data/seed/seed_imola_2026-10-16.json), [HISTORICAL_IMPORT_ANALYSIS.md](HISTORICAL_IMPORT_ANALYSIS.md).

**Attività**

- Implementare pipeline e tracciabilità della sezione 9.
- Versionare lo schema senza rompere l’import del formato precedente durante la transizione.
- Produrre seed completo, report righe, alias, esclusioni, duplicati e diff.
- Eseguire dry-run e due import idempotenti su database usa-e-getta.
- Integrare UI amministrativa solo dopo stabilità CLI/API.

**Test/evidenze:** fixture minimali per ogni foglio, golden file, formule mancanti, duplicati, alias, righe escluse, hash e idempotenza.  
**Criterio di accettazione:** 100% righe spiegate e totali riconciliati entro tolleranza; nessun sottoinsieme editoriale occulto.  
**Rischio:** workbook con formule non materializzate; bloccare e segnalare, non inventare valori.  
**Stop condition:** report approvato, zero errori bloccanti, seed validato e import dry-run pulito.

### Blocco 9 — Controlli e anomalie

**Dipendenze:** Blocchi 3 e 8.  
**File principali:** [checks.py](../backend/domain/checks.py), [anomalies/models.py](../backend/anomalies/models.py), [AnomaliesPage.tsx](../frontend/src/features/anomalies/AnomaliesPage.tsx).

**Attività**

- Aggiornare regole esistenti alla distinzione progetto/lotto/quota.
- Aggiungere controlli per lotto duplicato, chiusura senza lotto atteso, quota post-scadenza, oversubscription, disposizione incompleta, iniziativa chiusa con saldo aperto, provenienza incerta e divergenza workbook/seed.
- Conservare fingerprint stabili, supersession e workflow take/resolve/accept.
- Evitare warning per una quota legalmente assegnata prima della scadenza.

**Test/evidenze:** un finding e un non-finding per regola, rerun idempotente, supersession, UI di presa/risoluzione.  
**Criterio di accettazione:** ogni violazione di invariante produce un’anomalia azionabile senza falsi positivi sull’eccezione confermata.  
**Rischio:** rumore operativo; severità e deduplica devono essere testate.  
**Stop condition:** run ripetuto stabile e backlog anomalie iniziale classificato.

### Blocco 10 — Suite integrata e validazione manuale

**Dipendenze:** Blocchi 5–9.  
**File principali:** [backend/tests](../backend/tests/), [frontend/src](../frontend/src/), [frontend/e2e](../frontend/e2e/), documentazione manuale.

**Attività**

- Aggiornare i test che codificano la vecchia release attiva e l’allocazione scaduta.
- Aggiungere test di modello, dominio, servizio, API, permessi, import e frontend.
- Rendere ogni E2E indipendente con database/fixture ripristinati; niente dipendenza dall’ordine o da dati consumati da test precedenti.
- Coprire lifecycle progetto, chiusura→lotto, FIFO split, consumo oltre scadenza, ritorno/perdita, settings e import dry-run.
- Eseguire validazione manuale con i quattro ruoli e registrare evidenze.

**Test/evidenze:** backend completo, TypeScript, lint, Vitest, Playwright reale, controllo migrazioni mancanti e OpenAPI.  
**Criterio di accettazione:** zero failure e zero skip non giustificati; E2E verificano persistenza dopo reload; checklist manuale firmata.  
**Rischio:** suite seriale fragile; isolare dati per test invece di aumentare retry.  
**Stop condition:** tutte le pipeline verdi su ambiente pulito e anomalie note formalmente accettate.

### Blocco 11 — Rollout, contract migration e rollback

**Dipendenze:** Blocco 10.  
**File principali:** migrazioni, [backup.py](../backend/core/management/commands/backup.py), runbook deploy e changelog.

**Attività**

- Provare backup e restore su copia dell’ambiente target.
- Eseguire expand e backfill con applicazione in modalità manutenzione per le sole mutation contabili.
- Confrontare conteggi e saldi pre/post; sbloccare scritture solo dopo approvazione.
- Monitorare 409, 422, anomalie e differenze di riconciliazione.
- Dopo la finestra di stabilità eseguire contract migration e rimuovere i percorsi legacy.
- Conservare export prima/dopo e report batch.

**Test/evidenze:** rehearsal completo, tempi misurati, procedura rollback eseguita realmente su copia.  
**Criterio di accettazione:** saldi riconciliati, nessun record orfano, rollback entro l’obiettivo concordato, operatori informati.  
**Rischio:** rollback dopo nuove scritture sul modello target; la finestra deve bloccare mutation o prevedere restore completo, non downgrade parziale.  
**Stop condition:** approvazione go-live, backup verificato e piano di rollback con responsabile nominato.

---

## 11. Matrice minima dei test di accettazione

| Scenario | Preparazione | Azione | Esito osservabile |
|---|---|---|---|
| Progetto attivo pluriennale | Progetto ATTIVO dal 2024 con saldo positivo | Consultazione nel 2026 | Saldo progetto visibile; nessun lotto e zero disponibile wallet. |
| Chiusura senza data storica | Progetto CHIUSO importato senza data | Run controlli | In revisione; nessun lotto; assegnazione impossibile. |
| Chiusura valida | Budget 100, consumo diretto 70, chiusura 15/11/2025 | Chiudi progetto | Lotto 30, anno 2025, assegnabile fino al 31/12/2026. |
| Confine scadenza | Lotto precedente non assegnato | Assegna il 31/12/2026 e il 01/01/2027 | Prima operazione ammessa, seconda esclusa/rifiutata. |
| FIFO multi-lotto | Lotto A 3 giorni scadenza prima, lotto B 10 | Richiedi 8 | Due quote: 3 da A e 5 da B. |
| Concorrenza | Lotto disponibile 5 | Due richieste simultanee da 5 | Una sola riesce; nessuna sovra-allocazione. |
| Persistenza oltre scadenza | Quota assegnata nel 2026 da lotto che scade 31/12/2026 | Consuma nel 2027 con iniziativa aperta | Consumo ammesso e attribuito alla quota originaria. |
| Restituzione valida | Quota 10, consumo 6, lotto ancora valido | Chiudi iniziativa | 4 RESTITUITE e di nuovo disponibili nel lotto. |
| Perdita | Quota 10, consumo 6, lotto ormai scaduto | Chiudi iniziativa | 4 PERSE, non disponibili nel basket. |
| Storno ordinario | Consumo 3 su iniziativa aperta | Storna 1 con motivo | Originale invariato; nuova riga −1; saldo aumenta di 1. |
| Rettifica chiusa | Iniziativa chiusa con consumo errato | Admin esegue rettifica | Storno e disposizione compensativa atomici; iniziativa resta chiusa. |
| Doppia chiusura | Progetto o iniziativa già chiusi | Reinvia stesso comando | Nessun duplicato; esito idempotente o conflitto esplicito. |
| Permessi | Utenti dei quattro ruoli | Provano ogni mutation | Esito conforme alla matrice, anche chiamando direttamente l’API. |
| Import completo | Workbook noto | Converti due volte e dry-run | Stesso output semantico, 100% righe spiegate, zero duplicati. |
| E2E isolato | Database pulito per test | Esegui singolo test o intera suite | Stesso risultato in ogni ordine, nessun dato condiviso consumato. |

---

## 12. Requisiti non funzionali e sicurezza

- **Precisione:** usare Decimal e [`DaysField`](../backend/core/fields.py); mai float per giornate.
- **Audit:** autore, timestamp, motivo e versione per ogni comando; storico non sostituisce i ledger di consumo/disposizione.
- **Concorrenza:** versione attesa per UX e lock database per integrità contabile.
- **Idempotenza:** obbligatoria per chiusure, assegnazioni, import apply e rettifiche.
- **Upload:** allowlist estensioni, limite dimensione, filename neutralizzato, parsing fuori dai path pubblici, hash e scansione infrastrutturale se disponibile.
- **CSRF/sessione:** mantenere protezioni Django; nessuna autorizzazione derivata solo dal frontend.
- **Privacy:** report e log non devono duplicare dati personali non necessari né includere workbook interi.
- **Prestazioni:** evitare query per riga; annotazioni e prefetch; testare lista progetti/lotti al volume reale e con margine almeno 10×.
- **Osservabilità:** log strutturati con command id, batch id, user id e risultato, senza contenuti sensibili.
- **Backup:** nessuna migrazione contract senza restore provato.

---

## 13. Deliverable finali

Il programma è completo solo quando sono disponibili e coerenti:

1. regole approvate e casi eseguibili;
2. modello lotto/iniziativa/quota/disposizione migrato;
3. servizi atomici e API documentate;
4. UI completa per progetti, timesheet, wallet, impostazioni e amministrazione;
5. converter ripetibile e seed completo rispetto al workbook;
6. controlli e anomalie aggiornati;
7. matrice permessi verificata per API e GUI;
8. suite automatica isolata e validazione manuale registrata;
9. report migrazione e riconciliazione pre/post;
10. runbook di rollout e rollback provato.

Non rientrano automaticamente nel perimetro: nuovi stati di sospensione/riapertura, cancellazioni fisiche di ledger, scadenze automatiche del progetto, modifica arbitraria della validità dei lotti o servizi distribuiti. Richiedono una decisione di business separata.

---

## 14. Vincoli di esecuzione

- Preservare [scripts/load_demo.py](../scripts/load_demo.py) e adeguarlo solo in modo compatibile quando il modello target lo richiederà.
- Non cancellare [BLOCCO0_PIANO_OPERATIVO.md](BLOCCO0_PIANO_OPERATIVO.md) né [AUDIT_INDIPENDENTE_BLOCCO0.md](AUDIT_INDIPENDENTE_BLOCCO0.md).
- Nessun commit, push o deploy implicito durante l’esecuzione dei blocchi.
- Ogni blocco deve produrre diff, test eseguiti, risultati e decisioni residue prima del checkpoint.
- I test oggi verdi sono baseline tecnica, non prova di conformità alle nuove regole.
- L’implementazione futura deve partire dal Blocco 0 e non dal frontend: la UI dipende da contratti contabili già stabilizzati.
