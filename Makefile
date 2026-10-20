# Comandi di uso quotidiano. Richiede Docker Compose v2.
COMPOSE ?= docker compose
SEED ?= /srv/seed/seed_imola_2026-10-16.json

.DEFAULT_GOAL := help
.PHONY: help up down logs build migrate makemigrations superuser seed seed-dry shell \
        test test-backend test-frontend lint format e2e backup checks reset

help: ## Elenca i comandi disponibili
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Avvia lo stack in sviluppo
	$(COMPOSE) up -d --build
	@echo "Interfaccia: http://localhost:$${SL_HTTP_PORT:-8080}  -  API: http://localhost:$${SL_BACKEND_PORT:-8000}/api/v1"

down: ## Ferma lo stack
	$(COMPOSE) down

logs: ## Segue i log di tutti i servizi
	$(COMPOSE) logs -f --tail=100

build: ## Ricostruisce le immagini
	$(COMPOSE) build

migrate: ## Applica le migrazioni
	$(COMPOSE) run --rm backend python manage.py migrate

makemigrations: ## Genera le migrazioni
	$(COMPOSE) run --rm backend python manage.py makemigrations

superuser: ## Crea un utente amministratore
	$(COMPOSE) run --rm backend python manage.py createsuperuser

seed: ## Importa il seed reale (richiede data/seed/seed_imola_2026-10-16.json)
	$(COMPOSE) run --rm backend python manage.py import_seed $(SEED)

seed-dry: ## Simula l'import del seed senza scrivere nulla
	$(COMPOSE) run --rm backend python manage.py import_seed $(SEED) --dry-run

checks: ## Esegue il motore controlli
	$(COMPOSE) run --rm backend python manage.py run_checks

shell: ## Shell Django
	$(COMPOSE) run --rm backend python manage.py shell

test: test-backend test-frontend ## Esegue tutti i test

test-backend: ## pytest con gate di copertura su domain/ e importers/
	$(COMPOSE) run --rm -e DJANGO_SETTINGS_MODULE=config.settings.test backend \
		pytest --cov --cov-report=term-missing

test-frontend: ## Vitest
	$(COMPOSE) run --rm frontend npm run test -- --run

lint: ## ruff, black --check, mypy, eslint
	$(COMPOSE) run --rm backend sh -c "ruff check . && black --check . && mypy ."
	$(COMPOSE) run --rm frontend npm run lint

format: ## Applica black e ruff --fix, prettier
	$(COMPOSE) run --rm backend sh -c "ruff check --fix . && black ."
	$(COMPOSE) run --rm frontend npm run format

e2e: ## Playwright, 5 flussi chiave
	$(COMPOSE) run --rm frontend npm run e2e

backup: ## Dump del database e dei media
	$(COMPOSE) run --rm backend python manage.py backup

reset: ## ATTENZIONE: cancella il database e riparte da zero
	$(COMPOSE) down -v
	rm -rf .docker-data/pgdata
	$(COMPOSE) up -d --build
