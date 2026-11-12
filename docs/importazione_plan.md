# Piano di sviluppo — Importazione settimanale dei consuntivi

> Revisione del 12/11/2026. Rispetto alla prima stesura sono fissate le decisioni rimaste
> aperte: chiave di aggancio, riconciliazione come sezione autonoma, censimento dei
> collaboratori, granularità della data, semestre del canone. Ogni affermazione tecnica è
> verificata contro il codice e contro `docs/Andamento_operativo_Banca_mediolanum_2026.xlsx`.

## 1. Obiettivo e perimetro

Sostituire la pagina "Riconciliazione PPM" con una pagina **Importazione**, attraverso la
quale l'utente carica ogni settimana un file Excel contenente i nuovi consuntivi da
aggiungere a quelli già presenti.

Il file alimenta tre sezioni:

| Foglio Excel | Sezione applicativa | Destinazione tecnica |
| --- | --- | --- |
| `Progetti` | Progetti | `TimesheetEntry.project` |
| `Wallet` | Wallet | `TimesheetEntry.wallet_allocation` |
| `Organico_Allargato` | Organico allargato | `TimesheetEntry.canone_subactivity` |

L'importazione è incrementale, in append:

- aggiunge nuovi movimenti;
- conserva i consuntivi precedenti;
- conserva i dati inseriti manualmente;
- non modifica anagrafiche, budget, riserve o allocazioni esistenti;
- aggiorna i totali calcolati dal software.

L'unica anagrafica che l'importazione crea da sé è il **collaboratore mancante**, con un
avviso e in forma incompleta da rifinire (§4). Tutto il resto — progetti, voci wallet,
allocazioni, sotto-attività del canone — si censisce fuori dall'importazione.

Il file contiene **solo gli aggiornamenti della settimana**. Ogni singola voce va riportata
così com'è, anche quando si ripete. Vedi §3.5 per la sovrapposizione fra fogli.

Il workbook in `docs/` serve all'analisi del formato ed è un esempio: l'inserimento
operativo avviene dalla nuova pagina.

## 2. Fonti e stato dell'applicazione

### 2.1 File di riferimento

- `docs/Andamento_operativo_Banca_mediolanum_2026.xlsx` — esempio di estratto settimanale.
- `docs/TEMPLATE.md` — struttura del template.

Il `config.json` citato in TEMPLATE.md non fa parte di questo repository: appartiene allo
script esterno che genera il template. Non è una fonte per l'importer.

Contenuto verificato del workbook di esempio: tre fogli nell'ordine `Progetti`, `Wallet`,
`Organico_Allargato`; intestazioni identiche a TEMPLATE.md; date dal 30/10/2026 al
05/11/2026. Il foglio `Progetti` non ha riga di totale.

| Foglio | Righe dati | Giornate | Righe formula |
| --- | --- | --- | --- |
| `Progetti` | 21 | 8,6875 | 0 |
| `Wallet` | 7 | 3,1250 | 1 |
| `Organico_Allargato` | 17 | 5,7500 | 1 |
| **Totale** | **45** | **17,5625** | 2 |

I totali per foglio combaciano con quelli che Excel mostra nelle righe di formula, pur
senza valore in cache (§8.3).

Accettare `Progetto` come alias del foglio `Progetti`.

### 2.2 Struttura del registro esistente

I consuntivi stanno in `TimesheetEntry` (`backend/timesheets/models.py`). Il check
constraint `timesheet_exactly_one_target` impone esattamente una destinazione fra
`project`, `wallet_allocation` e `canone_subactivity`; `timesheet_days_not_zero` vieta le
giornate a zero. `save()` su un record esistente e `delete()` sollevano eccezione: il
registro è append-only e le rettifiche richiedono storni.

Campi utili all'importazione:

| Campo | Tipo | Nota |
| --- | --- | --- |
| `period` | `DateField` | data di competenza |
| `days` | `DaysField` = `Decimal(8,4)` | giornate |
| `source` | choices | nuovo valore `EXCEL_IMPORT` |
| `note` | `CharField(300)` | descrizione |
| `created_by` | FK `auth.User` | autore, da `TrackedModel` |
| `import_batch` | FK `ImportBatch` | da `ImportedRecordMixin` |

L'autore **non** è un campo dedicato: è `created_by`, popolato da `resolve_author`
(`backend/api/timesheet_authors.py`) sotto la capability riservata
`timesheets.assign_author`. L'anagrafica persone è `directory.Person`, entità distinta da
`auth.User`.

### 2.3 Componenti riutilizzabili

- `backend/imports/models.py` — `ImportBatch` con `content_hash`, `status`, `report`,
  `applied_by`/`applied_at`; `ImportIssue`; `ImportedRecordMixin`.
- `backend/importers/report.py` — struttura dei report.
- `backend/directory/normalization.py` — `comparison_key` ordina i token, quindi
  "Ravagli Andrea" e "Andrea Ravagli" collidono già: l'inversione cognome/nome è gestita.
- `frontend/src/features/admin/AdminPage.tsx` — pattern upload, simulazione, conferma.
- `frontend/src/lib/api.ts` — richieste multipart.
- Servizi wallet: sincronizzazione consumi e finanziamento FIFO.
- Capability `imports.upload` e `imports.apply`.

L'importer PPM legge totali aggregati e applica differenze: serve un importer nuovo, di
righe giornaliere, con percorso operativo distinto.

### 2.4 Attenzione al nome "riconciliazione"

Nel codice la parola indica già un'altra cosa: il confronto fra giornate PPM e ledger
interno, in `backend/domain/reconciliation.py`, con `reconciliation_tolerance_days` in
`backend/core/models.py`, che alimenta dashboard e anomalie. Rimuovendo la pagina
"Riconciliazione PPM" l'etichetta si libera per l'utente, ma **nel codice** la nuova
funzione usa un nome distinto — `import_mapping` — per non confondere le due logiche.

## 3. Chiave di aggancio e mapping

### 3.1 Regola generale

La chiave è il **codice** dove il codice esiste. Dove il modello non espone un codice, la
chiave è il **titolo normalizzato**. In entrambi i casi il confronto è esatto: nessun
aggancio euristico su nomi simili. Ciò che non aggancia va in Riconciliazione (§6).

| Colonna Excel | Chiave | Destinazione |
| --- | --- | --- |
| `Progetti!Progetto` | `Project.code` | `Project` |
| `Wallet!Progetto` | `Project.code` | contesto dell'allocazione |
| `Wallet!Sottoprogetto` | titolo normalizzato | `WalletAllocation` |
| `Organico_Allargato!Sotto progetto` | titolo normalizzato | `CanoneSubactivity` |
| `Collaboratore` | nome normalizzato | `auth.User` (autore) |

Perché titolo e non codice per le ultime due: `CanoneSubactivity` non ha alcun campo
codice, solo `title` (`backend/canone/models.py`); `WalletAllocation` ha `external_ref`,
riferimento di import, e punta a una `WalletActivity` il cui `code` per le attività non
progettuali è generato (`ATT-…-7391744E`) e non è un valore che un utente scriva in Excel.
Esporre un codice utente su queste due entità è un lavoro a sé, fuori perimetro.

### 3.2 Progetti

`Excel.Progetto` → `Project.code`, match esatto. Ogni riga valida genera un
`TimesheetEntry` con `project` valorizzato.

Verificato sull'esempio: i valori della colonna A sono già codici esatti
(`IM26018-3313-BMED-ARCH-SOLUTION-DESIGN-ONBOARDING-MINORI`,
`IM26254-3313-BMED-ARCH-SOLUTION-DESIGN-GESTIONE-DOPPIO-CR`), entrambi presenti fra i 142
progetti censiti. Questo foglio aggancia senza intervento.

### 3.3 Wallet

`Excel.Progetto` + `Excel.Sottoprogetto` → voce wallet → allocazione destinataria. Ogni
riga valida genera un `TimesheetEntry` con `wallet_allocation` valorizzato.

La risoluzione considera l'anno della data e le relazioni effettive della voce wallet. Con
più allocazioni compatibili, l'utente sceglie in Riconciliazione. L'associazione si
memorizza **senza** modificare le fonti di finanziamento dell'allocazione.

Verificato sull'esempio: `Wallet 2026 Migrazione OSB14 POC` non ha corrispondenza esatta,
ma **non è un nome arbitrario**: è la concatenazione dell'anno wallet e del titolo
dell'allocazione, cioè `Wallet 2026` + `Migrazione OSB14 POC`, che nell'applicativo esiste
come allocazione di `WalletYear` 2026 con origine Monte Wallet.

È il caso d'uso tipico della Riconciliazione: l'utente associa la voce Excel a una voce
applicativa esistente, anagrafata parzialmente o con nome diverso (`… POC WAVE1` contro
`… POC`), oppure la crea prima dall'interfaccia wallet decidendo giornate allocate e
finanziamenti. L'import non crea allocazioni.

Una strategia di aggancio che spogli il prefisso `Wallet <anno>` risolverebbe questo caso
da sola, ma resta **fuori perimetro**: il §3.1 impone il match esatto, e un'euristica sui
nomi è esattamente ciò che la Riconciliazione esiste per evitare. Dopo la prima
associazione il problema non si ripresenta.

### 3.4 Organico allargato

`Excel.Sotto progetto` → titolo della `CanoneSubactivity`, cercato nel canone pertinente.
Il **canone si deduce dall'anno e dal semestre della data** della riga.

Verificato sull'esempio: le 7 sotto-attività del foglio esistono tutte nel canone
`IM26179-3313-BMED-ARCH-ORGANICO-ALLARGATO-2026-S2`. `[EA] Revisione Modello dati BBA`
esiste solo in 2026-S2; `Assestment dismissione FileNet` esiste in **entrambi** i canoni
2026-S1 e 2026-S2, e senza la regola del semestre resterebbe ambiguo. Le date 30/10–05/11
risolvono su 2026-S2.

#### Vincoli specifici di questa sezione

`CanoneSubactivityTimesheetListView.post` impone due controlli che le altre due sezioni
**non** hanno, e che l'importer deve riprodurre:

1. **Finestra temporale dell'attività.** Se `start_date` o `end_date` sono valorizzate, la
   data del consuntivo deve cadere nell'intervallo. Una riga fuori finestra è un errore, e
   la console deve dichiarare l'intervallo ammesso: altrimenti il messaggio è
   incomprensibile a chi guarda solo l'Excel.
2. **Capienza riservata per attività.** `consumed + days > reserved_days` blocca. Il
   controllo va fatto sul cumulato del batch per singola attività, non per riga: il foglio
   porta più righe sulla stessa sotto-attività (8 su `[EA] Standardizzazione dei BBA`).

Il monte giornate del canone può essere interamente assegnato — nell'esempio
`Riservato 173,00 gg · disponibile da assegnare 0,00 gg` — quindi non c'è margine per
creare sotto-attività nuove senza sottrarre giornate a un'altra. Ulteriore ragione per cui
la Riconciliazione associa e non crea.

Avviso utile: quando un'attività resta sotto mezza giornata di residuo dopo l'applicazione,
segnalarlo. Nell'esempio `[EA] Revisione Modello dati BBA` scende a 0,10 gg e
`SAL - Enterprise Architecture (CON cliente)` a 0,12 gg: la settimana dopo diventerebbero
errori bloccanti senza preavviso.

### 3.5 Indipendenza dei fogli

Applicare i mapping di ciascun foglio in modo indipendente. Non eliminare una riga di
`Progetti` perché compare anche in `Wallet`.

Nel workbook di esempio la sovrapposizione è totale: tutte e 7 le righe di `Wallet` sono lo
stesso movimento già presente in `Progetti` — identici progetto, collaboratore, data, nota
e giornate — per 3,125 gg su 8,6875 gg. **È il comportamento atteso**: il file contiene gli
aggiornamenti della settimana e ogni voce va riportata, anche se ripetuta. L'anteprima
evidenzia la sovrapposizione a titolo informativo, senza escludere nulla.

Qualunque futura regola di esclusione fra sezioni sarà una decisione funzionale esplicita.

## 4. Collaboratori

L'autore del consuntivo è un `auth.User` scritto in `created_by`. Il resolver:

1. riconosce le corrispondenze certe fra nomi completi normalizzati, usando
   `comparison_key` che rende equivalenti "Cognome Nome" e "Nome Cognome";
2. usa i mapping già confermati;
3. per un nome **ambiguo** — più candidati plausibili — non decide: chiede in
   Riconciliazione;
4. per un nome **assente** censisce il collaboratore e prosegue, con un avviso.

In nessun caso attribuisce silenziosamente il consuntivo all'operatore che carica il file.

### 4.1 Censimento automatico del collaboratore assente

Il nuovo collaboratore viene creato come **"Nome Cognome"**, invertendo la forma
"Cognome Nome" dell'Excel per allinearsi alla convenzione dell'anagrafica: `Nicoletti
Pietro` → `Pietro Nicoletti`. Usare `titlecase_name` di
`backend/directory/normalization.py`.

I nomi di questo Excel sono consulenti Imola, quindi il collaboratore nasce con ruolo
**`fornitore`** (`roles.SUPPLIER`, etichetta "Fornitore (Imola)") e `directory.Person` con
organizzazione `IMOLA`. Nessuna deduzione da fare: è una costante dell'estratto operativo.

Il record nasce **utilizzabile come autore ma non come accesso**:

- gruppo `fornitore`, che possiede `timesheets.create`: necessario perché
  `assignable_authors()` lo includa nel menu degli autori;
- `is_active = True`, ma `set_unusable_password()`: senza password utilizzabile non può
  autenticarsi. L'unico backend configurato è `ModelBackend`, a password, quindi
  l'accesso è effettivamente impossibile fino a che un amministratore non ne imposta una;
- contrassegnato come creato dall'importazione e da rifinire, sullo stesso modello di
  `CanoneSubactivity.needs_review`.

Attenzione a non crearlo `is_active = False`: `assignable_authors()` filtra
`is_active=True` (`backend/api/timesheet_authors.py`), quindi un utente disattivato
sparirebbe dal menu degli autori e non potrebbe ricevere consuntivi.

L'importazione emette un **avviso**, non un errore: la riga si importa e il collaboratore
resta in evidenza nella schermata di anagrafica, dove si completano gli attributi residui
(email, referenze, eventuale password). L'avviso compare nella console (§7.1) e nel report
del batch, così da essere rintracciabile anche a importazione conclusa.

Perché serve comunque un utente applicativo: l'autore del consuntivo è `created_by`, una
FK a `auth.User`. Censire solo la `Person` non basta a dare un autore alla riga.

Verificato sull'esempio, 4 collaboratori:

```text
Ravagli Andrea      -> Andrea Ravagli      OK
Venturi Simone      -> Simone Venturi      OK
Vignati Pier Mauro  -> Pier Mauro Vignati  OK
Nicoletti Pietro    -> assente in anagrafica: da censire
```

`Nicoletti Pietro` viene quindi censito come `Pietro Nicoletti`, disattivato, con avviso, e
la sua riga si importa.

## 5. Data e giornate

### 5.1 Granularità della data — decisione

I consuntivi importati portano **la data esatta del giorno**, non il primo del mese.

Non è un cambio di impostazione: il registro è **già** giornaliero in tutte e tre le
sezioni. `ProjectLedgerView.post`, `parse_entry` in `backend/api/wallet_timesheets.py` e
`CanoneSubactivityTimesheetListView.post` salvano `date.fromisoformat(...)` senza
normalizzare, e i dati reali lo confermano: 2026-10-25 e 2026-11-05 su un progetto,
2026-11-02 e 2026-11-04 su un'allocazione wallet, 2026-10-29 e 2026-11-05 su una
sotto-attività del canone.

La normalizzazione a inizio mese sopravvive in tre punti marginali, da cui provengono le
righe tipo "2026-10-01 … storico": `backend/importers/ppm.py`,
`backend/importers/seed_json.py` e la rettifica sintetica del consuntivato in
`WalletAllocationAdjustView`. Nessuno dei tre è sul percorso della nuova importazione.

La verifica prevista in fase 1 si riduce quindi a un controllo di sicurezza sui report e
sull'analisi costi: dove assumano `period` uguale al primo del mese, correggere aggregando
per mese in lettura invece che in scrittura.

### 5.2 Formati accettati

- date native Excel (seriali: nell'esempio 46325 = 30/10/2026);
- stringhe `gg/mm/aaaa`;
- stringhe ISO `aaaa-mm-gg`.

Una data mancante o invalida è un errore. Non usare mai la data odierna come ripiego.

### 5.3 Giornate

Aritmetica `Decimal`, precisione `DaysField` = `Decimal(8,4)`.

```text
valore Excel 0.125   -> 0.1250
testo Excel  "0,375" -> 0.3750
```

Non importare il valore arrotondato mostrato dalla cella. Rifiutare valori non numerici,
non finiti, zero o negativi.

I valori dell'esempio sono frazioni binarie (0,0625 / 0,1875 / 0,3125 / 0,4375 / 0,625 /
0,875): quattro decimali li rappresentano esattamente, senza perdita.

**La cella mostra un valore diverso da quello che contiene.** TEMPLATE.md impone formato
contabile a due decimali sulla colonna `gg tot`, quindi nel foglio `Wallet` si legge `0,38`
dove il valore è `0,375`, `0,06` dove è `0,0625`, `0,19` dove è `0,1875`. Lo stesso accade
nell'interfaccia dell'applicativo, che mostra `0,19 gg` per `0,1875`. Leggere il valore
visualizzato invece di quello grezzo introduce un errore sistematico che si accumula ogni
settimana. Con `openpyxl` significa `data_only=False` e lettura del valore della cella, mai
del testo formattato.

## 6. Riconciliazione

Sezione **autonoma e permanente**, non un passaggio interno all'anteprima. Mostra le voci
Excel non agganciate e consente di associarle a una voce dell'applicativo. L'associazione è
memorizzata e riusata nelle settimane successive, così che il caso non si ripresenti.

Registro di mapping per:

- codici progetto esterni;
- coppie progetto/sottoprogetto wallet;
- titoli delle sotto-attività dell'organico allargato;
- nomi dei collaboratori.

Ogni mapping conserva: tipo, valore esterno, contesto necessario (anno, canone, semestre),
destinazione applicativa, operatore e data della conferma.

La sezione non crea destinazioni: associa valori Excel a entità già censite. Quando
l'entità manca, rimanda al censimento nella sezione competente (wallet, canone) e poi
permette l'associazione. L'unica eccezione sono i collaboratori, creati dall'importazione
con avviso (§4.1).

## 7. Flusso della pagina "Importazione"

**Passaggio 1 — Caricamento.** Selettore `.xlsx`, descrizione del formato atteso, nome e
dimensione del file, pulsante "Analizza file". Cambiare file annulla l'anteprima.

**Passaggio 2 — Analisi.** Il backend verifica struttura e intestazioni, legge le righe
informative, normalizza date e giornate, risolve destinazioni e collaboratori, verifica i
vincoli applicativi e produce il report. La pagina mostra le associazioni mancanti o
ambigue con rimando alla Riconciliazione. Al cambio di un'associazione, ricalcolare.

**Passaggio 3 — Anteprima.** Tre schede, Progetti / Wallet / Organico allargato. Per ogni
riga: numero di riga Excel, destinazione originale, destinazione risolta, collaboratore e
utente associato, data, giornate, descrizione, esito e motivazione. Riepilogo per foglio:
righe lette, importabili, righe di totale escluse, errori, avvisi, giornate da aggiungere.

**Passaggio 4 — Conferma.** "Conferma importazione" si abilita quando tutte le righe
informative sono valide, tutte le associazioni sono risolte, l'utente ha i permessi e il
batch non è già stato applicato. La conferma si riferisce esattamente al file e alle
associazioni dell'anteprima.

**Passaggio 5 — Esito e storico.** Identificativo, file, operatore, data e ora, righe e
giornate aggiunte per sezione, eventuale errore, collegamenti alle sezioni aggiornate. La
pagina include lo storico delle importazioni accessibili all'utente.

### 7.1 Console dei problemi

Riquadro sempre presente nella pagina di importazione, popolato dall'analisi. Ogni voce
indica **foglio e cella** in notazione Excel, così da poter correggere il file senza
cercare a mano:

```text
ERRORE   Progetti!E7            gg tot vuota
ERRORE   Progetti!C12           data non leggibile: "3 nov"
ERRORE   Wallet!F4              gg tot non numerica: "mezza giornata"
ERRORE   Organico_Allargato!A9  sotto-attività non trovata nel canone 2026-S2
ERRORE   Organico_Allargato!C6  data fuori dal periodo dell'attività (01/11 – 31/12/2026)
ERRORE   Organico_Allargato!E8  supera le giornate riservate: 12,00 riservate, 11,80 già
                                consuntivate, il batch ne porta 0,50
AVVISO   Organico_Allargato!A3  dopo l'applicazione l'attività resta a 0,10 gg di residuo
AVVISO   Progetti!B3            collaboratore "Nicoletti Pietro" censito come
                                "Pietro Nicoletti": completare l'anagrafica
AVVISO   Wallet!A2              riga già presente nel foglio Progetti (destinazione distinta)
```

Requisiti della console:

- due livelli, `ERRORE` e `AVVISO`, coerenti con `ImportIssueLevel` già esistente;
- riferimento di cella cliccabile che evidenzia la riga nell'anteprima;
- filtro per livello e per foglio, e conteggio per foglio;
- esportabile o copiabile, per poter correggere l'Excel con l'elenco sotto gli occhi;
- persistita come `ImportIssue` del batch, consultabile dallo storico anche dopo.

Gli **errori** impediscono la conferma: l'applicazione resta atomica sull'intero workbook
(§10), si corregge il file o l'anagrafica e si ricarica. Gli **avvisi** non bloccano nulla.
Un collaboratore assente è un avviso, non un errore (§4.1): non ferma l'importazione.

## 8. Parser Excel

### 8.1 Regole di lettura

- Intestazioni nella prima riga.
- Colonne abbinate per nome, non per posizione.
- Normalizzazione di maiuscole e spazi.
- Equivalenza fra `Sotto progetto` e `Sottoprogetto`.
- Lettura di tutte le righe informative, **compresa la riga 2**.
- Esclusione delle righe completamente vuote.
- Identificazione esplicita delle righe finali di totale.

TEMPLATE.md descrive la riga 2 anche come modello di formato; nell'estratto operativo
contiene dati (`Progetti!A2` = `IM26018-…-ONBOARDING-MINORI`, Venturi Simone, 0,125 gg) e va
importata.

### 8.2 Dettagli tecnici verificati

Il workbook **non ha** `sharedStrings.xml`: tutte le stringhe sono inline
(`<is><t>…</t></is>`). Un parser che legga solo `<v>` perde progetto, collaboratore e note.
Usare `openpyxl`, che gestisce entrambe le forme.

### 8.3 Formule

Le formule di totale non generano consuntivi. Calcolare i totali sommando le righe
importabili, senza dipendere dalla cache Excel.

Verificato: `Wallet!F9` = `SUM(F2:F8)` e `Organico_Allargato!A19` =
`SUBTOTAL(109;Tabella1[gg tot])`, entrambe **senza valore in cache**, e il workbook ha
`fullCalcOnLoad="1"`. Il foglio `Progetti` non ha riga di totale: il conteggio "righe di
totale escluse" vale legittimamente zero.

Una formula in un campo di una riga informativa, priva di valore disponibile, deve produrre
un errore comprensibile.

## 9. Append e prevenzione dei reimport

### 9.1 Regola principale

Un nuovo batch aggiunge i nuovi consuntivi ai precedenti. Nessuna riga esistente viene
aggiornata o eliminata dal caricamento settimanale.

### 9.2 Protezione dai retry

- hash SHA-256 del file (`ImportBatch.content_hash`, già presente);
- controllo dello stato del batch;
- applicazione una sola volta;
- protezione da doppio clic e richieste concorrenti;
- impronta del contenuto normalizzato, per riconoscere lo stesso estratto ripresentato con
  ordine o formattazione diversi. L'impronta include foglio, destinazione e numero di
  occorrenze delle righe.

### 9.3 Righe simili fra settimane

Senza un identificativo esterno del movimento, due righe identiche possono essere un
reimport o due registrazioni legittime. Quindi:

- bloccare il riutilizzo di un batch già applicato;
- riconoscere la ripresentazione dello stesso estratto;
- segnalare le sovrapposizioni con i movimenti già presenti, come da §9.4;
- **non** deduplicare globalmente in silenzio sulla base di data, autore e giornate.

### 9.4 Sovrapposizione con movimenti già presenti

Il controllo del §9.2 riconosce lo stesso **file** ripresentato. Non basta: il rischio
concreto è un'altra cosa, cioè righe già inserite a mano nell'applicativo che tornano
nell'estratto settimanale.

Prima della conferma, ogni riga in ingresso va confrontata con i movimenti già esistenti
**sulla stessa destinazione**, cercando coincidenza di data, giornate e descrizione
normalizzata. Ogni corrispondenza produce un **avviso** nella console, con indicati data,
autore e giornate del movimento già presente, più il suo identificativo.

Non scartare automaticamente la riga: due giornate identiche sulla stessa attività possono
essere legittime, e il §9.3 vieta la deduplicazione silenziosa. L'avviso serve a far vedere
all'operatore "queste righe esistono già" **prima** di applicare, perché è il solo momento
in cui la cosa è ancora reversibile a costo zero.

Se la corrispondenza è su data, giornate e descrizione ma **l'autore differisce**,
l'avviso lo dice esplicitamente: una delle due fonti ha l'autore sbagliato e va corretta
prima di importare, altrimenti la stessa giornata risulta di due persone diverse.

Caso reale osservato sull'allocazione `Migrazione OSB14 POC` (Wallet 2026): cinque delle
sette righe del foglio `Wallet` erano già registrate a mano con data, giornate e
descrizione identiche, e una sesta coincideva su tutto tranne l'autore — Excel
`Ravagli Andrea`, applicativo `Pietro Nicoletti`. In quel caso l'importazione si sarebbe
fermata soltanto per capienza (8,32 + 3,125 oltre le 10,00 riservate): una salvaguardia
fortuita, non un controllo.

### 9.5 Rollback

I consuntivi non si cancellano. Se un batch operativo deve essere annullabile, l'annullo
genera storni (`build_reversal`) e porta il batch a `ROLLED_BACK`, senza toccare le righe
originali. Da confermare se la prima versione lo include.

## 10. Applicazione backend

Nuovi moduli:

```text
backend/importers/operational_excel.py     parser e normalizzazione
backend/importers/operational_mapping.py   risoluzione delle destinazioni
backend/importers/operational_batch.py     validazione e applicazione
backend/api/operational_import_views.py    upload, anteprima, mapping, conferma, storico
```

Estensioni dei modelli:

- `ImportKind.OPERATIONAL_XLSX` (`max_length=20`, il valore sta in 16 caratteri);
- `TimesheetSource.EXCEL_IMPORT` (`max_length=15`, il valore sta in 12);
- righe normalizzate con provenienza (foglio e numero di riga Excel);
- registro delle associazioni (§6);
- collegamento fra riga sorgente e movimento creato.

### Transazione e vincoli

Prima del commit: acquisire i lock necessari, ricontrollare lo stato del batch, verificare
permessi e destinazioni, ricalcolare le capienze considerando **tutte** le righe del batch,
creare i movimenti, sincronizzare consumi e stati wallet, registrare esito e operatore.

L'applicazione è atomica sull'intero workbook: un errore impedisce aggiornamenti parziali.

Superamento della capienza di un'allocazione: errore bloccante. Lo sforamento resta
possibile solo dall'interfaccia wallet, con `override_reason` e `override_by`, prima
dell'importazione.

Riutilizzare o estrarre i controlli già presenti nelle API dei consuntivi, così che
importazione e inserimento manuale rispettino le stesse regole. In particolare, da
tutte e tre le viste di consuntivazione. I controlli comuni: giornate maggiori di zero,
descrizione obbligatoria entro 300 caratteri, data valida. Poi, per destinazione:

| Sezione | Vista | Controlli propri |
| --- | --- | --- |
| Progetti | `ProjectLedgerView.post` | progetto non chiuso; `budget_days − consumato_diretto − allocato_a_wallet` |
| Wallet | `WalletAllocationTimesheetListView.post` | allocazione non chiusa; `consumed + days > allocated_days` |
| Organico allargato | `CanoneSubactivityTimesheetListView.post` | finestra `start_date`–`end_date`; `consumed + days > reserved_days` |

Differenza rispetto al flusso manuale: ogni capienza va calcolata sul **cumulato del
batch** per singola destinazione, non riga per riga. Sei righe da 1,5 gg sullo stesso
progetto passerebbero una per una e sfonderebbero il budget insieme; il foglio
`Organico_Allargato` porta 8 righe sulla stessa sotto-attività.

## 11. API

```text
POST   /api/v1/imports/operational/preview
PATCH  /api/v1/imports/operational/{batch_id}/mappings
POST   /api/v1/imports/operational/{batch_id}/apply
GET    /api/v1/imports/operational
GET    /api/v1/imports/operational/{batch_id}
GET    /api/v1/imports/mappings
POST   /api/v1/imports/mappings
```

La preview può salvare staging e report, ma non crea movimenti. L'apply usa il batch
validato e ricontrolla le condizioni.

## 12. Frontend e navigazione

```text
frontend/src/features/importazione/ImportazionePage.tsx
frontend/src/features/riconciliazione/RiconciliazionePage.tsx
```

Componenti separati per upload, associazioni, riepilogo, tabella di anteprima, esito,
storico.

Aggiornare `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`,
`frontend/src/components/CommandPalette.tsx`, le traduzioni italiane e inglesi, e i test
della vecchia pagina `frontend/src/features/reconciliation/`.

Route `/importazione` e `/riconciliazione`, con redirect dalla vecchia `/riconciliazione`
PPM.

Dopo l'applicazione, invalidare le query di progetti, ledger, wallet, canoni, dashboard,
report e analisi costi interessate.

## 13. Permessi e vecchia riconciliazione PPM

Distinguere con le capability esistenti: caricamento e anteprima, conferma, consultazione
dello storico. L'importazione per collaboratori diversi dall'operatore rispetta
`timesheets.assign_author`.

**Conseguenza da verificare con il committente: solo un Admin può confermare
l'importazione.** Ogni riga dell'estratto è intestata a un collaboratore diverso da chi
carica il file, quindi l'applicazione richiede `timesheets.assign_author`, che è in
`RESERVED_CAPABILITIES` e non è assegnabile ad altri ruoli nemmeno via override. Dalla
mappa in `backend/core/capabilities.py`:

| Ruolo | Carica e anteprima | Conferma | Intesta ad altri |
| --- | --- | --- | --- |
| `admin` | sì | sì | sì |
| `responsabile_bmed` | sì | sì | **no** |
| `fornitore` | sì | **no** | **no** |
| `referente_bmed` | no | no | no |

Un fornitore può quindi preparare e verificare l'anteprima, ma non applicarla; un
responsabile BMED può applicare solo consuntivi a proprio nome, inutile per questo flusso.
Se l'importazione settimanale deve poter essere confermata da un non-Admin, va deciso
esplicitamente se concedere `timesheets.assign_author` limitatamente al percorso di
importazione — modifica alla riserva delle capability, non banale e da autorizzare.

Analizzare i consumer attuali della riconciliazione PPM — dashboard, anomalie,
esportazioni, pannelli amministrativi — e definire gli aggiornamenti perché non presentino
i nuovi movimenti come vecchi snapshot aggregati.

## 14. Test e criteri di accettazione

**Backend:** parsing dei tre fogli; stringhe inline; alias e ordine delle colonne; date e
virgole decimali; precisione a quattro decimali; esclusione dei totali e formule senza
cache; risoluzione delle destinazioni per codice e per titolo; semestre del canone dedotto
dalla data; collaboratore assente censito come "Nome Cognome" con ruolo `fornitore`,
password inutilizzabile e avviso, senza bloccare la riga; collaboratore appena censito che
compare in `assignable_authors()`; collaboratore ambiguo che richiede la scelta;
riferimento di cella corretto in ogni problema della console; append su registri popolati;
protezione dal reimport; **avviso di sovrapposizione** su riga già presente con stessa
data, giornate e descrizione, e avviso distinto quando coincide tutto tranne l'autore;
lettura del valore grezzo e non di quello formattato a due decimali; conservazione delle
destinazioni distinte fra fogli; capienza cumulativa per destinazione sulle tre sezioni;
finestra `start_date`–`end_date` della sotto-attività del canone, con intervallo ammesso
nel messaggio; avviso di residuo sotto mezza giornata; atomicità; sincronizzazione FIFO e
stato wallet; permessi e concorrenza.

**Frontend:** voce di menu "Importazione" e "Riconciliazione"; caricamento; completamento
delle associazioni; anteprima delle tre sezioni; conferma disabilitata in presenza di
errori; prevenzione del doppio invio; esito, storico e aggiornamento delle schermate.

**Accettazione funzionale.** Il processo è completo quando:

1. un Excel valido aggiunge i movimenti alle tre sezioni secondo i mapping;
2. i consuntivi preesistenti restano presenti;
3. data esatta, utente, giornate e descrizione corrispondono alla sorgente;
4. il secondo caricamento settimanale aggiunge nuovi movimenti;
5. la ripetizione di un'importazione già applicata non duplica i dati;
6. ogni movimento è riconducibile al batch e alla riga Excel;
7. un errore bloccante non lascia aggiornamenti parziali;
8. una voce Excel non agganciata è associabile dalla Riconciliazione e l'associazione vale
   anche per le settimane successive.

**Comandi di verifica.**

```text
make test-backend
npm run test -- --run      # da frontend/
npm run typecheck          # da frontend/
npm run build              # da frontend/
```

Sul workbook di esempio l'esito atteso è quello della tabella del §2.1: 21 + 7 + 17 = **45
movimenti** per 17,5625 gg, nessuno scartato come duplicato, una volta associata
l'allocazione wallet.

### Esempio tracciato — riga che ripete una descrizione esistente

Caso reale, da usare come test di non-regressione sulla deduplicazione.

Riga Excel, foglio `Progetti`:

```text
IM26294-3313-BMED-ARCH-SELEZIONE-SOFTWARE-RISK | Venturi Simone | 03/11/2026 |
Redazione paragrafo 4.1.2.1 Clonazione Campagne | 0,25
```

Stato del progetto prima dell'importazione: budget 10,00 gg, consumato 3,76 gg, residuo
6,24 gg. Nel ledger esiste già `2026-10-25 · Simone Venturi · 0,25 gg` con **la stessa
descrizione identica**.

Comportamento atteso:

| Passaggio | Esito |
| --- | --- |
| Codice progetto | match esatto, nessuna riconciliazione |
| Collaboratore | `comparison_key("Venturi Simone")` → Simone Venturi |
| Data | `period = 2026-11-03`, giorno esatto |
| Giornate | `Decimal("0.2500")` |
| Capienza | `0,25 ≤ 6,24` meno allocazioni wallet: passa |
| Duplicato | **no**: stessa descrizione ma data diversa, è lavoro di un altro giorno |
| Dopo l'apply | consumato 3,76 → 4,01; residuo 6,24 → 5,99; 37,6% → 40,1% del budget |

La riga del 25/10 resta invariata. Un importer che deduplicasse su progetto, autore e
descrizione perderebbe questa giornata: è il comportamento che il §9.3 vieta.

Nota sulla precisione: nello stesso ledger un consuntivo è visualizzato `0,13 gg` ma vale
`0,1250`. L'Excel lavora in ottavi di giornata (0,0625 / 0,125 / 0,1875), quindi leggere il
valore mostrato invece di quello grezzo perde frazioni ogni settimana.

## 15. Sequenza di realizzazione

| Fase | Deliverable |
| --- | --- |
| 1 | Verifica dell'assunzione `period` = inizio mese nelle aggregazioni wallet e canone; correzione dove serve (§5.1) |
| 2 | Parser `operational_excel.py` con test sul workbook di esempio: tre fogli, stringhe inline, formule senza cache, 4 decimali |
| 3 | Modelli: `OPERATIONAL_XLSX`, `EXCEL_IMPORT`, righe di staging con provenienza, registro dei mapping |
| 4 | Resolver delle destinazioni: codice progetto, titolo wallet, titolo canone con semestre dalla data |
| 5 | Resolver dei collaboratori su `comparison_key`, con censimento automatico del nome assente e avviso |
| 6 | Validazione del batch: capienze cumulative, permessi, impronta anti-reimport, avvisi di sovrapposizione con i movimenti esistenti (§9.4) |
| 7 | Applicazione atomica con sincronizzazione wallet, e API di preview/mappings/apply/storico |
| 8 | Pagina Importazione: upload, anteprima a tre schede, console dei problemi con riferimenti di cella, riepiloghi, conferma, esito |
| 9 | Sezione Riconciliazione autonoma, con associazioni memorizzate e riusate |
| 10 | Rimozione della pagina PPM, redirect, aggiornamento dei consumer, traduzioni, test end-to-end |

Deliverable finale: una pagina di importazione settimanale utilizzabile dall'utente, con
associazioni riutilizzabili, anteprima, inserimento in append e tracciamento completo.
