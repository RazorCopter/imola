# Struttura del template

Il template contiene tre fogli, uno per ogni rendicontazione. 

| #    | Foglio               | Rendicontazione (`nome` in config.json) | Colonne |
| ---- | -------------------- | --------------------------------------- | ------- |
| 1    | `Progetti`           | Progetti                                | A–E     |
| 2    | `Wallet`             | Wallet                                  | A–F     |
| 3    | `Organico_Allargato` | Organico allargato                      | A–E     |

## Regole comuni a tutti i fogli

- **Riga 1 = intestazioni.** Le colonne vengono abbinate a quelle della sorgente
  per nome, ignorando maiuscole e spazi ("Sotto progetto" = "Sottoprogetto").
- **Riga 2 = modello di formato.** Da questa riga lo script copia stile, formato
  numerico e altezza da applicare a tutte le righe dati.
- **Riga totali:** la prima riga sotto le intestazioni che contiene una formula.
  Lo script la sposta sotto l'ultima riga dati e aggiorna l'intervallo della formula.
- Eventuali righe di esempio presenti nel template vengono sostituite dai dati.
- Formati: **Data** = data breve, **gg tot** = contabile con 2 decimali.

## 1. Progetti

| Col. | Intestazione  | Formato        |
|------|---------------|----------------|
| A    | Progetto      | Generale       |
| B    | Collaboratore | Generale       |
| C    | Data          | Data           |
| D    | Note          | Generale       |
| E    | gg tot        | Contabile, 2 dec. |

## 2. Wallet

| Col. | Intestazione  | Formato        |
|------|---------------|----------------|
| A    | Progetto      | Generale       |
| B    | Sottoprogetto | Generale       |
| C    | Collaboratore | Generale       |
| D    | Data          | Data           |
| E    | Note          | Generale       |
| F    | gg tot        | Contabile, 2 dec. |

## 3. Organico_Allargato

| Col. | Intestazione   | Formato        |
|------|----------------|----------------|
| A    | Sotto progetto | Generale       |
| B    | Collaboratore  | Generale       |
| C    | Data           | Data           |
| D    | Note           | Generale       |
| E    | gg tot         | Contabile, 2 dec. |

