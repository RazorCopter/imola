# SOL - gap analysis eseguibile

Stato iniziale: 73 test dichiarati, modifiche locali preservate. Ambito frontend soltanto; backend/api/admin_views.py escluso. Ogni gap viene chiuso contro il criterio indicato; il backend reale e tracciato separatamente.

| ID | Priorita | Pagina/componente e problema | Impatto / intervento | Accettazione e prova | Stato |
|---|---|---|---|---|---|
| SOL-01 | P2 | Controlli nativi con stili duplicati in tutte le pagine | Primitivi Button/Input/Select, focus e disabled coerenti, mantenendo props e payload | Unit suite + tutte le route renderizzate nei due temi | NOT_STARTED |
| SOL-02 | P2 | KPI dashboard duplicato; intestazioni/toolbar ripetute | Riutilizzare KPI e primitivi layout dove la semantica coincide | Nessuna perdita di tooltip, hint, azioni o valori | NOT_STARTED |
| SOL-03 | P1 | Import: preview non invalidata alla sostituzione file | Azzerare preview e risultato quando cambia il file; rendere visibili fasi e feedback | File diverso disabilita Conferma; browser test simula/applica solo fixture | NOT_STARTED |
| SOL-04 | P1 | Organico: dettaglio lungo, form creazione sempre aperto e dati precedenti durante cambio canone | Sezioni capacita/attivita, creazione esplicita, loading/error del dettaglio, stato form isolato | Browser CRUD canone/attivita/consuntivo e cambio selezione | NOT_STARTED |
| SOL-05 | P1 | Wallet: detail affiancato restringe tabella, verifica form incompleta | Detail come drawer accessibile, invariati FIFO e input cumulativo | Apertura/chiusura/focus, update e creazione con fixture | NOT_STARTED |
| SOL-06 | P1 | Anomalie e revisione: feedback generico e validazioni UI poco esplicite | Errori effettivi, pending per azione e feedback di successo | Error fixture e retry, payload e permessi testati | NOT_STARTED |
| SOL-07 | P1 | Amministrazione: navigazione e storico non uniformi, dialog custom | Navigazione secondaria coerente, storico tabellare, dialog focus/accessibilita | Tab utenti/referenti/ruoli/config, import/export e dialog con fixture | NOT_STARTED |
| SOL-08 | P0 | Dashboard: possibili errori mostrati accanto a KPI senza stato per fonte | Mantenere separati errore, loading, assenza e zero | Scenari error/empty e valori null verificati | NOT_STARTED |
| SOL-09 | P3 | Dialog e resizer: description/focus/tastiera da verificare | Correggere nomi, descrizioni, overflow e resizing tastiera | Audit automatico disponibile e test focus Escape/Tab | NOT_STARTED |
| SOL-10 | P3 | Contrasto e token non verificati globalmente | Audit dark/light, correzioni semantiche documentate | Screenshot + misure/audit senza violazioni critiche note | NOT_STARTED |
| SOL-11 | P3 | Tutte le pagine: matrice responsive incompleta | 1920/1600/1440/1366/1024, testi lunghi e tabelle piene | Nessun overflow documento; scroll tabelle locale fruibile | NOT_STARTED |
| SOL-12 | P1 | Copertura workflow browser frammentata in script temporanei | Harness deterministico in e2e isolato, nessuna API reale per scritture | CRUD frontend, filtri, form, dialog e scenari per nove sezioni | NOT_STARTED |
| SOL-13 | P3 | Evidenze visuali non tutte della versione finale | Nuove catture sol-final e ispezione reale | 27 viste principali piu componenti critici esaminate | NOT_STARTED |
| SOL-14 | P2 | Documentazione con generico PARTIAL | Matrice di accettazione, risultati e riproducibilita | Report e checkpoint aggiornati con riferimenti alle prove | NOT_STARTED |
| SOL-BE | P0 | Backend in riavvio per modifica preesistente esclusa | Solo log e descrizione; nessuna modifica | E2E reale resta esplicitamente non verificato | BLOCKED |
