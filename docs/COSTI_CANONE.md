# Costo forfettario del canone

In Amministrazione / Configurazione, `Costo forfettario per canone (EUR)` indica
l'importo complessivo pagato all'attivazione di ciascun contratto di Organico
Allargato. Il valore iniziale è zero: inserire l'importo contrattuale effettivo.
La tariffa giornaliera resta dedicata a progetti e wallet.

In Analisi Costi i consuntivi delle attività del canone sono sempre esclusi dai
costi e dalle giornate a tariffa giornaliera. Il flag `Considera i costi del canone`
è inizialmente disattivato; viene applicato con `Applica filtri`, insieme alle date.
Quando è attivo, ogni canone già iniziato contribuisce per l'intero forfait alla
data di inizio, se questa rientra nell'intervallo selezionato (estremi inclusi).
Se manca la data di inizio viene usato l'inizio del semestre o trimestre indicato
dal periodo contrattuale. I contratti futuri non sono conteggiati.

Il forfait confluisce nei totali, nella barra `Canone`, nella ripartizione per
fornitore e origine e nel mese di attivazione. Non genera giornate fatturabili:
le righe esclusivamente a forfait mostrano un trattino nella colonna giornate.
Eventuali consuntivi wallet senza progetto restano distinti sotto `Senza progetto`.

La configurazione è globale e corrente: si applica a ciascun canone selezionato,
anche nei periodi passati. Non rappresenta uno storico delle tariffe contrattuali.
Non sono introdotti movimenti di pagamento o modifiche ai consuntivi.

La migrazione `core.0005_appsettings_canone_fixed_cost` aggiunge il campo alle
impostazioni e al relativo storico. Va applicata al database durante il deploy,
prima di utilizzare la nuova versione dell'API. Non è stata eseguita sul database
locale durante questa modifica.

Su richiesta dell'utente non sono stati eseguiti test, build, TypeScript, lint o
screenshot. Sono state eseguite soltanto formattazione e revisione del diff Git.
