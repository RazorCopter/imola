# Analisi per l'import storico

## Stato della capability

**FG-026 resta NON IMPLEMENTATA.** Il sistema sa validare e importare via CLI un seed JSON versione 1.0.0, ma non converte un Excel storico nel seed e non espone un flusso web/API di upload, dry-run e apply.

Questo documento descrive il formato di destinazione e le informazioni da identificare nel file storico. Non implementa converter né API.

## Flusso di import esistente

### Management command `import_seed`

`backend/imports/management/commands/import_seed.py` espone:

- file JSON opzionale; in assenza usa `settings.SEED_FILE`;
- `--dry-run`, che esegue realmente l'import in transazione e forza il rollback;
- `--apply`, esplicito ma equivalente al comportamento predefinito;
- `--schema`, per indicare uno schema alternativo;
- `--json`, per il report strutturato.

Il comando legge e valida il file, invoca l'orchestrazione, stampa il report e converte errori di file, schema, conflitto o esecuzione in `CommandError`. L'interfaccia è esclusivamente CLI; non riceve file da HTTP.

### Validazione in `backend/importers/schema.py`

- supporta soltanto `schema_version = 1.0.0`;
- valida con JSON Schema Draft 2020-12 e `FormatChecker`;
- raccoglie tutti gli errori prima di interrompere;
- esegue una lettura numerica per jsonschema e una seconda con `Decimal`, evitando `float` per giornate e valori contabili.

Lo schema canonico è `seed_schema_v1.json`. Il payload radice richiede `meta`, `configurazione`, `persone`, `progetti`, `canoni`, `wallet`, `snapshot_ppm` e `anomalie_aperte`. Lo schema consente proprietà aggiuntive: il file analizzato contiene infatti alcuni campi usati dall'importer ma non obbligatori nello schema.

### Orchestrazione e idempotenza

L'orchestratore in `backend/importers/batch.py`:

1. legge i byte UTF-8 e calcola SHA-256;
2. valida il JSON;
3. costruisce un report per entità;
4. in dry-run crea un batch temporaneo, esegue l'import reale e annulla la transazione;
5. in apply crea `ImportBatch`, importa atomicamente, registra report e issue e porta il batch ad `APPLIED`;
6. conserva un batch `FAILED` con il report in caso di errore;
7. rifiuta contenuti già applicati con lo stesso hash SHA-256.

Il modello `ImportBatch` registra tipo, stato, nome file, hash, report, autore/data di applicazione e storico. Il tipo `EXCEL_LEGACY` esiste nell'enum, ma non implica la presenza di un importer Excel storico.

`backend/importers/seed_json.py` effettua upsert tramite chiavi naturali, assegna il batch solo ai record creati e crea i consumi iniziali come movimenti `TimesheetEntry` append-only. L'idempotenza ha quindi due livelli:

- fingerprint dell'intero file, SHA-256, per impedire il ri-apply dello stesso contenuto;
- chiavi naturali per aggiornare/non duplicare entità già note.

Chiavi osservate nell'importer:

- organizzazione: `code`;
- persona: nome normalizzato (`name_key`) + organizzazione;
- progetto: `code`;
- milestone: progetto + data prevista + stato;
- canone: progetto + semestre;
- sotto-attività canone: canone + ufficio + titolo;
- wallet annuale: anno;
- attività wallet: codice;
- allocazione wallet: `external_ref = id_import`, univoco se valorizzato;
- snapshot PPM: tipo + data estrazione + file origine;
- riga snapshot: snapshot + codice progetto;
- anomalia seed: fingerprint costruita dai dati dell'anomalia.

### Ordine e dipendenze di import

L'ordine attuale rispetta le FK:

1. configurazione applicativa;
2. organizzazioni cliente/fornitore;
3. persone, dipendenti dalle organizzazioni;
4. progetti, con referenti risolti sulle persone;
5. milestone e consuntivi diretti dei progetti;
6. canoni, sotto-attività e relativi consuntivi;
7. anno wallet, attività, allocazioni e consumi iniziali;
8. wallet storico tecnico derivato dai campi previsti;
9. snapshot PPM e righe;
10. anomalie aperte, eventualmente associate al progetto.

Un convertitore futuro deve produrre riferimenti risolvibili in questo ordine: per esempio ogni referente deve comparire in `persone`, un progetto origine deve esistere in `progetti` e ogni allocazione deve riferire un codice attività presente in `wallet.attivita`.

## Struttura del seed JSON analizzato

L'analisi di `data/seed/seed_imola_2026-10-16.json` riguarda solamente la struttura, non i valori o i dati aziendali contenuti.

```text
radice
├── $schema
├── meta
├── configurazione
│   ├── fornitore
│   ├── cliente
│   └── regola_scadenza_residui
├── persone[]
├── progetti[]
│   └── milestone_fatturazione[]
├── canoni[]
│   ├── formula_target
│   └── sottoattivita[]
├── wallet
│   ├── anno
│   ├── attivita[]
│   └── allocazioni[]
├── snapshot_ppm[]
│   ├── righe[]
│   └── totali
└── anomalie_aperte[]
```

Le sezioni sono aggregate per entità e si collegano tramite codici/nome normalizzato, non tramite UUID Django. Le giornate sono numeri JSON convertiti in `Decimal`; le date conformi allo schema sono stringhe ISO `YYYY-MM-DD` o `null` dove previsto.

## Mappatura da determinare nell'Excel storico

La colonna “origine” non dichiara un mapping già noto: indica l'intestazione o la regola che deve essere individuata nel file Excel storico. Il file sorgente Excel non è stato fornito nel workspace, quindi fogli, colonne, celle, formule e semantica effettiva restano da verificare.

### Metadati e configurazione

| CAMPO SEED | ENTITÀ | TIPO | OBBLIGATORIO | SIGNIFICATO | VINCOLI | ORIGINE DA IDENTIFICARE NELL'EXCEL |
|---|---|---:|:---:|---|---|---|
| `meta.schema_version` | Meta | stringa | sì | Versione contratto seed | costante `1.0.0` | Valore del converter, non necessariamente una colonna Excel |
| `meta.generato_il` | Meta | data | sì | Data generazione JSON | ISO date | Timestamp/data di esecuzione del converter |
| `meta.data_riferimento_dati` | Meta | data | sì | Data a cui si riferiscono i dati | ISO date; usata come periodo iniziale | Data situazione/estrazione dichiarata nel workbook |
| `meta.fonte_principale` | Meta | stringa | no | Nome fonte primaria | testo | Nome file/workbook storico |
| `meta.fonti_secondarie[]` | Meta | array stringhe | no | Altre fonti | testo | Eventuali workbook/fogli complementari documentati |
| `meta.note` | Meta | stringa | no | Note generali | testo | Note di copertina o note prodotte dal converter |
| `configurazione.fornitore.codice` | Organizzazione | stringa | sì | Codice fornitore | chiave organizzazione | Anagrafica/intestazione fornitore o configurazione esterna certificata |
| `configurazione.fornitore.ragione_sociale` | Organizzazione | stringa | sì | Nome fornitore | testo | Anagrafica/intestazione fornitore |
| `configurazione.cliente.codice` | Organizzazione | stringa | sì | Codice cliente | chiave organizzazione | Anagrafica/intestazione cliente o configurazione esterna certificata |
| `configurazione.cliente.ragione_sociale` | Organizzazione | stringa | sì | Nome cliente | testo | Anagrafica/intestazione cliente |
| `configurazione.unita_misura` | Configurazione | stringa | no | Unità delle quantità | costante `giornata_uomo` | Legenda/unità del workbook; altrimenti decisione esplicita |
| `configurazione.ore_per_giornata` | Configurazione | numero | sì | Conversione ore/giorno | numero | Parametro/legenda; chiarire se i dati Excel sono ore o giornate |
| `configurazione.granularita_ppm_gg` | Configurazione | numero | no | Granularità PPM | numero decimale | Parametro PPM o configurazione certificata |
| `configurazione.tolleranza_riconciliazione_gg` | Configurazione | numero | sì | Tolleranza scostamenti | numero decimale | Parametro di controllo, probabilmente non una riga operativa |
| `configurazione.regola_scadenza_residui.*` | Configurazione | oggetto | sì | Politica scadenza residui | valori/costanti previsti dallo schema | Regola documentata; non inferire da formule senza conferma |

### Persone e progetti

| CAMPO SEED | ENTITÀ | TIPO | OBBLIGATORIO | SIGNIFICATO | VINCOLI | ORIGINE DA IDENTIFICARE NELL'EXCEL |
|---|---|---:|:---:|---|---|---|
| `persone[].nome` | Persona | stringa | sì | Nome completo | univoco dopo normalizzazione per organizzazione | Colonne referenti/responsabili/anagrafica persone |
| `persone[].organizzazione` | Persona | enum | sì | Appartenenza | `BMED` o `IMOLA` | Foglio/anagrafica o regola certa basata sul ruolo/colonna |
| `persone[].email` | Persona | stringa/null | no | Email | email valida o null | Anagrafica; non ricavare dal nome |
| `progetti[].codice` | Progetto | stringa | sì | Chiave progetto | min 3; univoca nell'applicazione | Codice progetto/commessa/PPM |
| `progetti[].titolo` | Progetto | stringa | sì | Descrizione | testo | Titolo/descrizione progetto |
| `progetti[].tipo_contratto` | Progetto | enum | sì | Categoria contrattuale | `CANONE`, `AQL`, `CORPO`, `PPM`, `ATTIVITA` | Tipo offerta/contratto; serve tabella di normalizzazione |
| `progetti[].codice_aro` | Progetto | stringa/null | no | Riferimento ARO | testo | Colonna ARO |
| `progetti[].codice_rda` | Progetto | stringa/null | no | Riferimento RDA | testo | Colonna RDA |
| `progetti[].deliverable` | Progetto | stringa/null | no | Deliverable | testo | Colonna deliverable |
| `progetti[].referente_bmed` | Progetto | stringa/null | no | Referente cliente | deve risolversi in `persone` BMED | Colonna referente/responsabile BMED |
| `progetti[].referente_imola` | Progetto | stringa/null | no | Referente fornitore | deve risolversi in `persone` IMOLA | Colonna referente/responsabile Imola |
| `progetti[].gg_budget` | Progetto | numero | sì | Budget in giornate | Decimal | Budget/monte giornate; chiarire formule e unità |
| `progetti[].gg_consumati_su_progetto` | Consuntivo progetto | numero | sì | Consumo iniziale diretto | Decimal; genera movimento append-only | Consuntivato cumulato; evitare doppio conteggio con righe mensili |
| `progetti[].gg_wallet_storico_gia_usati` | Wallet storico tecnico | numero | no schema, usato dall'importer | Consumo wallet pregresso | Decimal | Colonna esplicita del wallet storico e relativa data di competenza |
| `progetti[].data_inizio` | Progetto | data/null | no | Inizio | ISO date | Data avvio |
| `progetti[].data_fine_prevista` | Progetto | data/null | no | Fine pianificata | ISO date | Data fine prevista |
| `progetti[].data_chiusura_consuntivazione` | Progetto | data/null | no | Chiusura consuntivazione | ISO date | Data chiusura effettiva; non confondere con fatturazione |
| `progetti[].anno_riferimento_residuo` | Progetto | intero/null | no schema, usato dall'importer | Anno residuo dichiarato | confrontato con anno derivato dalla chiusura | Colonna anno residuo o regola documentata |
| `progetti[].stato_offerta` | Progetto | enum | sì | Stato commerciale | enum schema | Stato offerta; definire mapping valori legacy |
| `progetti[].stato_consuntivazione` | Progetto | enum | sì | Stato operativo | enum schema | Stato consuntivazione; separarlo dallo stato fattura |
| `progetti[].stato_fatturazione` | Progetto | enum | sì | Stato fatturazione | enum schema | Stato fattura; definire mapping legacy |
| `progetti[].stato_excel_originale` | Progetto | stringa/null | no | Valore legacy originale | testo conservativo | Colonna stato originale non normalizzato |
| `progetti[].note` | Progetto | stringa/null | no | Note | testo | Note/osservazioni |
| `progetti[].affidabilita` | Verifica | enum | sì | Qualità del dato | `CERTO`/`DA_VERIFICARE` | Regola esplicita basata su completezza/conflitti, da approvare |
| `progetti[].punti_da_verificare[]` | Verifica | array stringhe | no | Dubbi puntuali | testo | Errori, ambiguità o celle mancanti rilevate dal converter |
| `progetti[].milestone_fatturazione[].data_prevista` | Milestone | data/null | sì per riga | Data milestone | parte della chiave con stato | Colonne/righe scadenze fatturazione |
| `progetti[].milestone_fatturazione[].stato` | Milestone | enum | sì per riga | Stato milestone | enum schema | Stato milestone/fattura, con mapping documentato |

### Canoni

| CAMPO SEED | ENTITÀ | TIPO | OBBLIGATORIO | SIGNIFICATO | VINCOLI | ORIGINE DA IDENTIFICARE NELL'EXCEL |
|---|---|---:|:---:|---|---|---|
| `canoni[].codice_progetto` | Canone | stringa | sì | Progetto contenitore | deve esistere in `progetti` | Codice progetto canone |
| `canoni[].semestre` | Canone | stringa | sì | Periodo | pattern `YYYY-S1`/`YYYY-S2` | Semestre o derivazione da data esplicitamente validata |
| `canoni[].monte_gg` | Canone | numero | sì | Monte giornate | Decimal | Monte giorni contrattuale |
| `canoni[].data_estrazione` | Canone | data/null | no | Data fonte | ISO date | Data estrazione del foglio canone |
| `canoni[].formula_target.*` | Canone | oggetto | no | Parametri target | numeri/intero/booleano | Celle di formula e parametri; distinguere formula da valore calcolato |
| `canoni[].sottoattivita[].ufficio` | Sotto-attività | enum/null | no | Ufficio | `EA`, `SA`, `TA`, `CROSS` o null | Colonna ufficio/team |
| `canoni[].sottoattivita[].titolo` | Sotto-attività | stringa | sì | Nome attività | chiave con canone e ufficio | Colonna attività |
| `canoni[].sottoattivita[].gg_consuntivati` | Consuntivo canone | numero | sì | Consumo iniziale | Decimal; movimento append-only | Consuntivo cumulato per attività |
| `canoni[].sottoattivita[].stima_trimestre` | Sotto-attività | numero/null | no | Stima | Decimal/null | Colonna forecast trimestrale |
| `canoni[].sottoattivita[].forecast_residuo_31_12` | Sotto-attività | numero/null | no | Forecast residuo | Decimal/null | Colonna forecast a fine anno |
| `canoni[].sottoattivita[].note` | Sotto-attività | stringa/null | no | Note | testo | Note riga |

### Wallet

| CAMPO SEED | ENTITÀ | TIPO | OBBLIGATORIO | SIGNIFICATO | VINCOLI | ORIGINE DA IDENTIFICARE NELL'EXCEL |
|---|---|---:|:---:|---|---|---|
| `wallet.anno` | WalletYear | intero | sì | Anno wallet | chiave univoca | Anno del foglio/periodo wallet |
| `wallet.attivita[].codice` | WalletActivity | stringa | sì | Codice destinazione | univoco | Codice progetto/ticket/attività |
| `wallet.attivita[].titolo` | WalletActivity | stringa | sì | Descrizione | testo | Titolo attività |
| `wallet.attivita[].tipo` | WalletActivity | enum | sì | Tipo destinazione | `PROGETTO`, `ATTIVITA`, `REDMINE` | Natura della riga; regola di classificazione da concordare |
| `wallet.attivita[].referente_bmed` | WalletActivity | stringa/null | no | Referente cliente | deve risolversi in persone BMED | Colonna referente BMED |
| `wallet.attivita[].referente_imola` | WalletActivity | stringa/null | no | Referente fornitore | deve risolversi in persone IMOLA | Colonna referente Imola |
| `wallet.attivita[].note` | WalletActivity | stringa/null | no | Note | testo | Note riga |
| `wallet.allocazioni[].id_import` | WalletAllocation | stringa | sì | Identità stabile dell'allocazione | diventa `external_ref`, univoco | ID legacy stabile; se assente serve una regola deterministica approvata |
| `wallet.allocazioni[].anno_wallet` | WalletAllocation | intero | sì | Wallet di appartenenza | deve coincidere con/risolversi all'anno | Anno riga/foglio |
| `wallet.allocazioni[].progetto_origine` | WalletAllocation | stringa/null | sì, null ammesso | Provenienza giornate | codice progetto esistente o wallet generale | Colonna progetto sorgente; distinguere null reale da dato mancante |
| `wallet.allocazioni[].attivita` | WalletAllocation | stringa | sì | Destinazione | codice presente in `wallet.attivita` | Codice attività/progetto/ticket di destinazione |
| `wallet.allocazioni[].gg_allocati` | WalletAllocation | numero | sì | Giornate riservate | Decimal, non negative nel modello | Colonna allocato/assegnato |
| `wallet.allocazioni[].gg_consumati_iniziali` | Timesheet wallet | numero | sì | Consumo iniziale | Decimal; movimento append-only | Consuntivo cumulato wallet, con periodo e regola anti-doppio conteggio |
| `wallet.allocazioni[].stato` | WalletAllocation | enum | sì | Stato allocazione | `APERTA`/`CHIUSA` | Stato riga, con mapping legacy |
| `wallet.allocazioni[].note` | WalletAllocation | stringa/null | no | Note | testo | Note riga |
| `wallet.allocazioni[].affidabilita` | WalletAllocation | enum | sì | Qualità dato | `CERTO`/`DA_VERIFICARE` | Regola di qualità approvata |
| `wallet.allocazioni[].punti_da_verificare[]` | WalletAllocation | array stringhe | no | Dubbi | testo | Ambiguità/celle mancanti rilevate |

### Snapshot PPM e anomalie

| CAMPO SEED | ENTITÀ | TIPO | OBBLIGATORIO | SIGNIFICATO | VINCOLI | ORIGINE DA IDENTIFICARE NELL'EXCEL |
|---|---|---:|:---:|---|---|---|
| `snapshot_ppm[].tipo` | Snapshot PPM | enum | sì | Ambito estrazione | `PPM_WALLET`, `PPM_CANONE`, `PPM_PROGETTI` | Foglio/report di origine |
| `snapshot_ppm[].titolo` | Snapshot PPM | stringa | no | Titolo | testo | Titolo report |
| `snapshot_ppm[].data_estrazione` | Snapshot PPM | stringa | sì | Data/istante estrazione | parser importer; definire formato certo | Metadato estrazione workbook |
| `snapshot_ppm[].file_origine` | Snapshot PPM | stringa | no | Nome fonte | parte della chiave naturale | Nome workbook/file |
| `snapshot_ppm[].righe[].codice_progetto` | Riga PPM | stringa | sì | Progetto | normalizzato; chiave nella snapshot | Codice progetto PPM |
| `snapshot_ppm[].righe[].responsabile_imola` | Riga PPM | stringa/null | no | Responsabile dichiarato | testo | Colonna responsabile |
| `snapshot_ppm[].righe[].stato_ppm` | Riga PPM | stringa | no | Stato PPM | testo | Colonna stato |
| `snapshot_ppm[].righe[].gg_previsti` | Riga PPM | numero | sì | Previsto | Decimal | Colonna giorni previsti |
| `snapshot_ppm[].righe[].gg_residui` | Riga PPM | numero | no | Residuo | Decimal | Colonna giorni residui |
| `snapshot_ppm[].righe[].gg_totali` | Riga PPM | numero | sì | Totale | Decimal | Colonna giorni totali |
| `snapshot_ppm[].totali` | Snapshot PPM | oggetto | no | Totali dichiarati | struttura libera nello schema | Celle totali; definire se controllare o importare |
| `anomalie_aperte[].id_import` | Anomalia | stringa | sì | Identità fonte | contribuisce alla tracciabilità | ID anomalia legacy o regola deterministica |
| `anomalie_aperte[].severita` | Anomalia | enum | sì | Priorità | `ALTA`, `MEDIA`, `BASSA` | Severità originale o mapping approvato |
| `anomalie_aperte[].ambito` | Anomalia | enum | sì | Dominio | enum schema | Tipo/causa anomalia |
| `anomalie_aperte[].descrizione` | Anomalia | stringa | sì | Dettaglio | testo | Messaggio/nota oppure controllo deterministico documentato |
| `anomalie_aperte[].codice_progetto` | Anomalia | stringa/null | no | Progetto associato | codice progetto risolvibile o null | Codice progetto della riga problematica |
| `anomalie_aperte[].stato` | Anomalia | enum | sì | Workflow | enum schema | Stato anomalia legacy |

## Informazioni richieste dal file storico

Per rendere deterministico il mapping occorre disporre del workbook storico e documentare almeno:

1. elenco dei fogli, intestazioni effettive, righe di header e intervalli dati;
2. tipo cella e formato delle date, inclusi seriali Excel e celle formula;
3. unità di misura di ogni quantità e regola ore → giornate;
4. separatore decimale, arrotondamento e significato di vuoto, zero, trattino ed errore formula;
5. chiavi stabili di progetto, attività, allocazione, persona e snapshot;
6. dizionari di normalizzazione per stati, tipo contratto, ufficio, severità e ambito;
7. distinzione tra quantità cumulative e movimenti periodici, per evitare doppio conteggio;
8. data di competenza dei consumi iniziali;
9. provenienza e destinazione delle allocazioni wallet;
10. distinzione tra dato assente, non applicabile e incerto;
11. modalità di derivazione di `affidabilita` e `punti_da_verificare`;
12. politica per duplicati, righe annullate, formule non calcolate e riferimenti mancanti;
13. eventuali dati presenti in più fogli e relativa precedenza;
14. conferma che nomi e contenuti possano essere trattati secondo le regole di protezione dati.

Senza queste evidenze non è corretto inventare una corrispondenza basata sulla sola somiglianza dei nomi delle colonne.

## Lacune e lavoro futuro

- **Non esiste un convertitore Excel → JSON seed 1.0.0.** Non sono implementati lettura workbook, mapping colonne, normalizzazione, gestione formule o report di conversione.
- **Non esiste un'API di upload del seed.** Nessun endpoint riceve Excel o JSON.
- **Non esistono API dry-run/apply per seed.** Simulazione e applicazione sono disponibili soltanto tramite management command.
- **L'import seed è solo CLI.** Non è presente un flusso GUI con anteprima, conferma, autorizzazione e avanzamento.
- **Lo schema è permissivo sulle proprietà aggiuntive.** Alcuni campi letti dall'importer non sono formalmente richiesti/descritti nello schema; un converter futuro dovrà seguire sia schema sia contratto effettivo dell'importer fino al loro allineamento.
- **Manca il workbook storico nel workspace.** Non sono determinabili fogli, colonne e mapping reali.
- **Mancano decisioni di dominio.** In particolare servono regole certificate per chiavi sintetiche, stati legacy, periodi dei consumi, cumulati e qualità del dato.

FG-026 deve pertanto restare dichiarata non implementata fino a quando converter, contratto verificato, dry-run/apply controllati e percorso utente non saranno progettati, implementati e validati su un file storico autorizzato.