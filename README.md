# Supplier Ledger

Gestione della consuntivazione e del wallet delle giornate/uomo del fornitore **Imola
Informatica** per l'ufficio Architetture IT di **Banca Mediolanum**.

L'applicazione è la fonte di verità per **pianificazione, allocazioni wallet e regole**; i
**consuntivi** restano di competenza del PPM di Imola e vengono importati e riconciliati.

- Piano di lavoro a fasi: [`docs/PLAN.md`](docs/PLAN.md)
- Interpretazioni conservative e punti aperti: [`docs/DECISIONI_APERTE.md`](docs/DECISIONI_APERTE.md)
- Storico delle modifiche: [`docs/CHANGELOG.md`](docs/CHANGELOG.md)
- Manuale utente: `docs/MANUALE.md` (Fase 6)

## Regole di business da ricordare

| Regola | In sintesi |
|---|---|
| **R1** | Stato della consuntivazione e stato della fatturazione sono **indipendenti**: Imola può fatturare tutto a consuntivazione aperta, e questo non tocca residui, wallet o scadenze. |
| **R2** | Un progetto ATTIVO non ha scadenza dei residui. Da CHIUSO, il residuo vale nell'anno di chiusura e in quello successivo; dal 1 gennaio dell'anno +2 è perso. |
| **R3** | `residuo = budget − consuntivi diretti − allocazioni wallet`. Nessun totale è mai digitato a mano: tutto è calcolato dal database. |
| **R4** | Canone: `target = min(monte, base + settimane × gg_per_settimana)`; `delta = target − consuntivato` (positivo = a favore di BMED). |
| **R6** | Il PPM è la fonte dei consuntivi; la riconciliazione tollera 0,01 gg. |

## Test backend

La suite backend usa PostgreSQL nello stack Docker e deve essere eseguita dal repository con:

```bash
make test-backend
```

Il target esegue `pytest` nel container `backend`. L'esecuzione diretta dalla virtualenv host
non è supportata: la configurazione di test usa il nome DNS Docker `db`, non risolvibile
all'esterno dello stack.

## PostgreSQL portatile di fallback su Windows

L'ambiente ufficiale usa Docker. Se Docker non è disponibile, lo script PowerShell gestisce
l'istanza PostgreSQL 16 portatile in `C:\dev\pgdata` sulla porta `5433`:

```powershell
.\scripts\pg-local.ps1 start
.\scripts\pg-local.ps1 status
.\scripts\pg-local.ps1 psql
.\scripts\pg-local.ps1 stop
```

È possibile personalizzare directory, porta, database e utente con `PGDATA`, `PGPORT`,
`POSTGRES_DB` e `POSTGRES_USER`. Lo script non inizializza e non cancella mai i dati.

## Requisiti

- Docker Desktop (o Container Manager su Synology) con Docker Compose v2.
  Su Windows serve **WSL2 attivo**, altrimenti l'engine Linux non parte.
- Per lo sviluppo senza Docker: Python 3.12+ e Node 20+ (vedi *Sviluppo locale*).

## Avvio in locale con Docker

```bash
cp .env.example .env            # poi genera le due chiavi (sotto)
make up                         # db + backend + frontend + nginx
make superuser                  # crea il primo amministratore
make seed                       # import del seed reale, se presente in data/seed/
```

Generazione dei segreti:

```bash
python -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64))"
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(18))"
```

Indirizzi: interfaccia su <http://localhost:8080>, API su <http://localhost:8080/api/v1>,
admin Django su <http://localhost:8080/admin/>, healthcheck su <http://localhost:8080/health>.

`make help` elenca tutti i comandi.

## Sviluppo locale senza Docker

Utile per lavorare su dominio, test e frontend. Serve comunque un PostgreSQL 16 raggiungibile.

```bash
python -m venv .venv && .venv/Scripts/activate      # su Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend && python manage.py migrate && python manage.py bootstrap_roles
python manage.py runserver 8000

cd ../frontend && npm install && npm run dev        # Vite su http://localhost:5173
```

I test di dominio che non toccano il database girano senza PostgreSQL:

```bash
cd backend && pytest tests/domain/test_money.py -q
```

### PostgreSQL portatile (macchine senza WSL2 o Docker)

Se Docker non è disponibile, `scripts/pg-local.sh` governa un'istanza PostgreSQL 16 avviata
dai binari ufficiali scompattati in `PG_BIN` (default `/c/dev/pg-download/extract/pgsql/bin`),
con i dati in `PG_DATA` (default `C:/dev/pgdata`) e in ascolto su `127.0.0.1:5433`:

```bash
scripts/pg-local.sh start      # avvia
scripts/pg-local.sh status     # verifica
scripts/pg-local.sh psql       # console sul database applicativo
scripts/pg-local.sh stop       # arresta
```

Nel `.env` basta impostare `POSTGRES_HOST=127.0.0.1` e `POSTGRES_PORT=5433`. L'istanza
ascolta solo su loopback e serve esclusivamente allo sviluppo: la produzione usa il
servizio `db` di Docker Compose.

## I dati reali non sono versionati

`data/seed/seed_imola_2026-10-16.json` contiene progetti, budget e nominativi reali: è in
`.gitignore` e un hook di pre-commit (`scripts/check_no_real_seed.py`) impedisce di
committarlo per sbaglio. Nel repository stanno solo `seed_schema_v1.json` e le fixture demo.
I test di accettazione che lo richiedono sono marcati `@pytest.mark.seedfile` e si saltano
da sé quando il file non c'è.

## Deploy su Synology Container Manager

1. **Cartelle** (via SSH o File Station):

   ```bash
   sudo mkdir -p /volume1/docker/supplier-ledger/{pgdata,media,static,backups,seed}
   sudo chown -R 1026:100 /volume1/docker/supplier-ledger
   ```

2. **Codice**: copia il repository in `/volume1/docker/supplier-ledger/app`
   (`git clone` oppure File Station).

3. **Configurazione**: copia `.env.example` in `.env` e imposta almeno
   `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `DJANGO_ALLOWED_HOSTS`,
   `CSRF_TRUSTED_ORIGINS`, `COOKIE_SECURE=True` e
   `SL_DATA_DIR=/volume1/docker/supplier-ledger`.

4. **Avvio**: in Container Manager crea un progetto che punta a
   `/volume1/docker/supplier-ledger/app` usando solo `docker-compose.yml`
   (l'override serve allo sviluppo), oppure da SSH:

   ```bash
   cd /volume1/docker/supplier-ledger/app
   docker compose -f docker-compose.yml up -d --build
   ```

   Il servizio applica le migrazioni, raccoglie gli static e crea i gruppi dei ruoli da sé.

5. **Primo amministratore**:

   ```bash
   docker compose -f docker-compose.yml exec backend python manage.py createsuperuser
   ```

6. **HTTPS**: in DSM → *Portale applicazioni → Reverse Proxy* pubblica l'host verso
   `localhost:8080` (`SL_HTTP_PORT`), con WebSocket non necessari. Il backend si fida di
   `X-Forwarded-Proto`, quindi con `COOKIE_SECURE=True` i cookie restano `Secure`.

7. **Backup**: in *Utilità di pianificazione* aggiungi un'attività giornaliera

   ```bash
   cd /volume1/docker/supplier-ledger/app && docker compose -f docker-compose.yml \
     exec -T backend python manage.py backup --keep 14
   ```

   che scrive in `/volume1/docker/supplier-ledger/backups`; includi quella cartella in
   Hyper Backup.

Nessun servizio usa porte privilegiate: il solo ingresso è `SL_HTTP_PORT` (8080 per
impostazione predefinita).

## Struttura

```
backend/     Django 5 + DRF. domain/ contiene le formule (R2/R3/R4/R6) e i controlli,
             importers/ gli import; su questi due pacchetti vale il gate di copertura 85%.
frontend/    React 18 + TypeScript + Vite + Tailwind.
deploy/      Dockerfile, configurazioni nginx, note per Synology.
docs/        Piano, decisioni aperte, changelog, manuale.
data/seed/   Dati reali, non versionati.
scripts/     Utilità di supporto (guardia anti-commit del seed).
```
