# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/it/1.1.0/). Una voce per fase del piano.

## [Non rilasciato]

### Fase 1 - Fondamenta

**Aggiunto**
- Scaffolding del repository: backend Django 5 / DRF / PostgreSQL 16, frontend React 18 +
  TypeScript + Vite + Tailwind, Docker Compose (db, backend, frontend, nginx) con porte non
  privilegiate, volumi bind e healthcheck su ogni servizio, `.env.example` completo.
- Modello dati completo con migrazioni iniziali: organizzazioni e persone, progetti e
  milestone, canone e sotto-attività, wallet (anni, attività, allocazioni), consuntivi,
  snapshot PPM e profili di import, anomalie, batch di import, impostazioni globali.
- Tracciatura su tutte le entità: UUID, timestamp, autore, `version` per il lock ottimistico
  e storico delle modifiche con django-simple-history.
- Invarianti contabili a livello di database: budget non negativo, fine prevista dopo
  l'inizio, data di chiusura obbligatoria per i progetti chiusi (salvo import, vedi D-03),
  consuntivi append-only con esattamente un bersaglio e giornate diverse da zero.
- `domain/` con le formule, in un punto solo: `money.py` (Decimal a 4 cifre, mai float),
  `residuals.py` (R2 e R3), `wallet_balance.py` (R3 lato wallet), `canone_status.py` (R4),
  `reconciliation.py` (R6).
- API v1 di autenticazione a sessione con CSRF, astrazione del provider pronta per Entra ID
  ma non attiva, e endpoint delle viste calcolate (bilanci progetti, wallet, canone,
  riconciliazione) con errori in formato RFC 7807 in italiano.
- Ruoli applicativi (admin, responsabile BMED, referente BMED, fornitore) con permessi
  applicati lato API, comando `bootstrap_roles` e comando `backup` per Synology.
- Frontend: tema chiaro e scuro con rispetto della preferenza di sistema, sidebar
  collassabile, Command Palette (Ctrl/Cmd+K), catalogo i18n italiano con scheletro inglese,
  formattazione italiana dei numeri (`1.234,56 gg`) e modale di sessione scaduta che
  conserva il lavoro in corso invece di eseguire il logout.
- Qualità: ruff, black, mypy, eslint, prettier, pre-commit e una guardia che impedisce di
  versionare il seed con i dati reali del fornitore.

**Corretto durante la verifica**
- Le richieste non autenticate rispondevano 403: DRF declassa `NotAuthenticated` quando
  l'autenticazione è a sessione. Ora tornano **401** con `code=session_expired`, che è la
  condizione su cui il frontend apre il modale di re-login senza perdere il lavoro.
- I Decimal inseriti direttamente in una Response uscivano come float (7.5 invece di
  "7.5000"): `COERCE_DECIMAL_TO_STRING` vale solo per i serializer. Aggiunto
  `api/renderers.py`, che serializza ogni Decimal come stringa.
- L'applicazione `core` era priva del pacchetto migrazioni: le sue tabelle venivano create
  via syncdb prima di `auth`, rompendo la chiave esterna dello storico. Migrazione aggiunta.

**Test**
- 142 test backend, tutti verdi su PostgreSQL 16.4, copertura di `domain/` al **97%**
  (gate 85%). Fra questi i casi obbligatori del par. 11: 11.1 (progetto
  del 2024 ancora attivo, residuo 0), 11.3 (chiuso il 15/11/2025: valido al 31/12/2026,
  in scadenza il 02/10/2026, scaduto dal 01/01/2027), 11.4 (wallet 2026: allocato 130,89 -
  consumato 120,79 = 10,10 disponibili, residui da verificare esclusi), 11.5 (residuo da
  10 gg con allocazione a zero), 11.7 (canone S2: target 102,35 e delta +2,08), 11.9
  (riconciliazione IM25138 entro tolleranza).
- 8 test sulla formattazione lato frontend (Vitest); build di produzione e lint puliti.
- Verifica manuale degli endpoint: `/health`, sessione anonima 401, login, impostazioni,
  bilancio wallet, riconciliazione e PATCH con permessi.

**Nota sull'ambiente di questa macchina**
- Docker non parte perché WSL2 non è installato: lo sviluppo e i test usano un PostgreSQL 16
  portatile avviato da `scripts/pg-local.sh`. Lo stack Docker Compose resta quello previsto
  per il deploy su Synology, ma su questa macchina non è ancora stato eseguito.
