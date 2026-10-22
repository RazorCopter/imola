# FASE 7 — BLOCCO 0
# REMEDIATION DELLE FONDAMENTA FUNZIONALI

> Specifica completa. Il file termina con la riga `FINE SPECIFICA`.
> Se quella riga non è presente, il file è troncato: fermati e segnalalo.

## CONTESTO

Il Blocco 0000 è concluso.

`docs/FUNCTIONAL_GAP_ANALYSIS.md` è la baseline canonica della Fase 7 ed è stata sottoposta a verifica indipendente read-only.

Situazione certificata:

- COMPLETA: 0
- PARZIALE: 20
- SOLO BACKEND: 13
- NON IMPLEMENTATA: 6
- Totale capability: 39

La Functional Gap Analysis è la fonte di verità per lo stato funzionale dell'applicazione.
NON modificare retroattivamente la baseline per far risultare capability complete.
Ogni avanzamento deve essere dimostrato da nuove evidenze reali.

## IMPORTANTE

Le fasi precedenti hanno dimostrato che:

- test backend verdi non implicano completezza funzionale;
- presenza di pulsanti o schermate non implica un workflow funzionante;
- test Playwright che verificano solo heading, cookie, navigazione o presenza di un bottone NON sono E2E funzionali;
- `page.route` / mock delle API non costituisce prova dell'integrazione reale;
- una mutation è verificata solo se viene realmente eseguita e il risultato persistito viene verificato dopo reload o tramite API/DB reale.

Priorità da ora in avanti:

FUNZIONALITÀ REALE → GUI → PERSISTENZA → PERMESSI → E2E REALE → VERIFICA MANUALE

e non il semplice aumento della copertura di test.

## OBIETTIVO DEL BLOCCO 0

Prima di implementare le nuove capability principali della Fase 7, eliminare le ambiguità funzionali e tecniche che potrebbero contaminare i blocchi successivi.

NON implementare ancora:

- FG-013 assegnazione wallet ad architetto;
- FG-014 consumo/residuo per architetto;
- FG-026 conversione Excel storico;
- GUI completa di Amministrazione;
- nuove funzionalità non previste dalla baseline.

Queste capability saranno affrontate nei blocchi successivi. Il Blocco 0 deve preparare una base affidabile per farlo.

## 0.1 — SEMANTICA RICONCILIAZIONE / KPI

Analizza FG-017 e FG-018.

È stata verificata una situazione semanticamente ambigua: `delta = 0` con `allineamento = 0%`, oppure, in assenza di righe/snapshot, combinazioni che fanno apparire il sistema riconciliato quando non esistono dati sufficienti (vedi `backend/domain/reconciliation.py:147` e `:154`).

Definire esplicitamente almeno questi stati:

1. dati presenti e perfettamente riconciliati;
2. dati presenti ma non riconciliati;
3. snapshot/riferimento PPM assente;
4. nessuna riga confrontabile;
5. riconciliazione parziale.

NON rappresentare l'assenza di dati come successo.

La GUI deve distinguere chiaramente:

- ALLINEATO
- NON ALLINEATO
- PARZIALE
- NON VERIFICABILE / DATI ASSENTI

Verificare che colori, badge e KPI non comunichino "verde/successo" quando il confronto non è stato realmente possibile.

Aggiungere test backend e frontend coerenti con questa semantica e almeno un E2E reale con backend e database reali.

## 0.2 — RESIDUI E SCADENZE

Analizza FG-015 e le capability correlate. È classificata SOLO BACKEND, ma alcune informazioni risultano già esposte in GUI.

Prima di modificarne lo stato:

1. identifica quali calcoli esistono nel dominio;
2. identifica quali risultati vengono esposti dalle API;
3. identifica quali sono già visualizzati in progetto, wallet, revisione e dashboard (se pertinente);
4. verifica che la GUI non ricalcoli valori contabili con `Number`/float;
5. verifica che i valori derivati arrivino dal backend.

Regola di business da preservare: un progetto ancora in corso NON genera automaticamente residuo trasferibile/scadente solo perché esiste una differenza tra preventivato e consuntivato. Esempio noto: Protection Model può risultare ancora in corso.

Non alterare il motore contabile senza una motivazione documentata.

## 0.3 — PERMESSI E NAVIGAZIONE PER RUOLO

Analizza FG-034 e le capability di autenticazione/navigazione collegate. I permessi backend object-level già presenti non sono sufficienti.

Verificare il comportamento della GUI per almeno: Admin, Responsabile BMED, Referente BMED, Fornitore.

Per ogni ruolo determinare:

- pagine raggiungibili;
- voci di menu visibili;
- azioni consentite e non consentite;
- comportamento in caso di accesso diretto via URL;
- comportamento in caso di chiamata API non autorizzata.

Nascondere un pulsante NON è una misura di sicurezza: il backend deve continuare ad applicare l'autorizzazione indipendentemente dalla GUI.

Creare e versionare in documentazione una matrice ruolo → capability → read/write.

## 0.4 — E2E REALI DELLE CAPABILITY ESISTENTI

NON riscrivere indiscriminatamente tutta la suite E2E.

Identificare le capability già realmente utilizzabili da browser a cui manca solo una prova end-to-end reale, e per queste sostituire o affiancare ai test nominali test Playwright reali.

Un E2E valido deve:

1. partire da uno stato DB conosciuto;
2. usare frontend reale;
3. usare backend reale;
4. NON usare `page.route` per simulare l'API oggetto del test;
5. eseguire realmente l'azione;
6. verificare il risultato;
7. ricaricare la pagina;
8. verificare che il risultato sia ancora presente;
9. quando opportuno verificare anche via API/DB;
10. verificare almeno un caso negativo/autorizzativo quando pertinente.

NON promuovere automaticamente una capability a COMPLETA solo perché l'E2E passa. La DoD della Functional Gap Analysis resta vincolante.

## 0.5 — FIX DEGLI E2E NOMINALI DI FASE 6

Test già identificati come insufficienti (`frontend/e2e/phase6.spec.ts`):

- import seed (riga 20);
- chiusura/modifica progetto (riga 27);
- wallet (riga 38);
- anomalie (riga 45).

NON trasformare il test "import seed" in un workflow GUI se la GUI di import non esiste: resta SOLO BACKEND o PARZIALE secondo la matrice.

Per le capability realmente presenti in GUI, sostituire il controllo "pulsante presente" con il workflow reale.

ERRATO:

```
goto pagina
expect(button).toBeVisible()
```

CORRETTO:

```
goto pagina
inserimento dati
azione utente
conferma
request reale
risposta backend
reload
verifica persistenza
```

## 0.6 — VERIFICA MANUALE

Predisporre dati DEMO deterministici. Non usare dati aziendali reali.

Utenti demo per almeno: admin, responsabile BMED, referente BMED, fornitore.

Creare `docs/MANUAL_VALIDATION_FASE7.md` con una checklist eseguibile personalmente da browser:

```
[ ] login admin
[ ] login responsabile BMED
[ ] login referente
[ ] login fornitore
[ ] dashboard
[ ] progetti
[ ] dettaglio progetto
[ ] wallet
[ ] anomalie
[ ] revisione
[ ] riconciliazione
[ ] audit
```

Per ogni voce indicare: URL/percorso GUI, utente demo, azione da effettuare, risultato atteso.

NON dichiarare la verifica manuale completata: la eseguirò io.

## 0.7 — NON ALTERARE ANCORA IL MODELLO WALLET

FG-013 e FG-014 richiederanno una modifica funzionale importante.

NON aggiungere campi arbitrari come `architect_id`, `person_id`, `assigned_to` senza prima progettare il modello.

Produrre esclusivamente `docs/WALLET_ARCHITECTURE_ANALYSIS.md`, che descriva lo stato attuale di Wallet, WalletActivity, WalletAllocation, eventuali referenti (vedi `backend/wallet/models.py:45` e `:125`), TimesheetEntry, Project, eventuali modelli Person/User, e le relazioni esistenti.

Il documento deve rispondere alla domanda:

> "Come rappresentiamo in modo contabile e auditabile che N giornate del wallet vengono riservate a una determinata attività/progetto e affidate a uno specifico architetto, mantenendo consumo, residuo e storico?"

Proporre opzioni con pro/contro, senza implementarle. Il documento sarà l'input del blocco successivo.

## 0.8 — PREPARAZIONE IMPORT STORICO

FG-026 resta NON IMPLEMENTATA.

NON scrivere ancora alcun converter Excel → JSON.

Creare `docs/HISTORICAL_IMPORT_ANALYSIS.md` analizzando:

- schema seed 1.0.0;
- modelli Django coinvolti;
- importer attuale (`backend/imports/management/commands/import_seed.py`);
- informazioni obbligatorie e opzionali;
- vincoli e chiavi;
- fingerprint/idempotenza;
- dipendenze fra entità e ordine di import.

Produrre una tabella con colonne:

| CAMPO SEED | ENTITÀ | TIPO | OBBLIGATORIO | SIGNIFICATO | VINCOLI | ORIGINE DA IDENTIFICARE NELL'EXCEL |

Non inventare mapping dell'Excel se il file sorgente non è nel workspace. Indicare esplicitamente cosa richiede il file storico per essere determinato.

## VINCOLI

NON:

- fare refactoring estetico non necessario;
- cambiare stack;
- introdurre nuove framework/library senza necessità;
- modificare formule contabili non coinvolte;
- usare float per valori economici o giornate;
- usare dati aziendali reali negli E2E;
- dichiarare capability complete basandosi solo sui test;
- implementare FG-013, FG-014 o FG-026;
- iniziare autonomamente il blocco successivo.

Le modifiche devono essere minimali, versionabili e tracciabili.

## AGGIORNAMENTO GAP ANALYSIS

NON riscrivere la Functional Gap Analysis. Aggiornare solo le righe interessate da modifiche realmente implementate.

Per ogni cambio di stato mostrare: FG-ID, stato precedente, stato nuovo, evidenza backend, evidenza GUI, evidenza E2E, verifica manuale (indicandone esplicitamente l'assenza).

Non promuovere a COMPLETA se la DoD non è interamente soddisfatta.

## CHECKPOINT OBBLIGATORIO

Al termine del Blocco 0 FERMA LO SVILUPPO e restituisci:

1. file modificati;
2. migration create;
3. comportamento modificato;
4. test backend eseguiti e risultato;
5. test frontend eseguiti e risultato;
6. E2E reali eseguiti e risultato;
7. E2E che usano ancora mock/`page.route`;
8. capability FG coinvolte;
9. variazioni di classificazione;
10. capability ancora PARZIALI;
11. capability ancora SOLO BACKEND;
12. capability ancora NON IMPLEMENTATE;
13. sintesi di `WALLET_ARCHITECTURE_ANALYSIS.md`;
14. sintesi di `HISTORICAL_IMPORT_ANALYSIS.md`;
15. utenti demo e credenziali NON sensibili;
16. istruzioni esatte per avviare applicazione e dipendenze in locale;
17. URL locale da aprire nel browser;
18. `git status`;
19. commit creati.

Separa chiaramente: FATTI VERIFICATI / MODIFICHE IMPLEMENTATE / TEST AUTOMATICI / VERIFICA MANUALE ANCORA DA ESEGUIRE / DECISIONI APERTE.

Non usare "funziona", "completo", "verificato" senza indicare l'evidenza concreta.

## STOP CONDITION

Terminato il checkpoint: FERMATI.

- NON iniziare il Blocco 1.
- NON implementare FG-013.
- NON implementare FG-014.
- NON implementare FG-026.

Attendi la validazione del checkpoint e la verifica manuale dell'applicazione.

FINE SPECIFICA
