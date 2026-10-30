SHELL := /bin/bash
COMPOSE_DEV := docker compose -f compose.dev.yml
BACKEND := cd backend && uv run

.PHONY: setup infra-up infra-down models dev-models dev-api dev-web migrate lint format typecheck test test-e2e test-all test-models ingest reindex docs eval eval-compare

MODEL_SERVER := cd model-server && uv run
# Node version comes from .nvmrc (`nvm use`); pnpm runs through corepack, nothing global.
WEB := cd web && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 NEXT_TELEMETRY_DISABLED=1 corepack pnpm

setup:
	@test -f .env || cp .env.example .env
	cd backend && uv sync
	cd model-server && uv sync
	$(WEB) install

infra-up:
	$(COMPOSE_DEV) up -d --wait

infra-down:
	$(COMPOSE_DEV) down

migrate:
	$(BACKEND) alembic upgrade head

models:
	$(MODEL_SERVER) python -m model_server.download

dev-models:
	$(MODEL_SERVER) uvicorn model_server.main:app_factory --factory --host 127.0.0.1 --port 8001

dev-api:
	$(BACKEND) uvicorn lawqa.main:app_factory --factory --reload --host 127.0.0.1 --port 8000

dev-web:
	$(WEB) dev --hostname 127.0.0.1 --port 3000

lint:
	$(BACKEND) ruff check .
	$(BACKEND) ruff format --check .
	$(MODEL_SERVER) ruff check .
	$(MODEL_SERVER) ruff format --check .
	$(WEB) lint

format:
	$(BACKEND) ruff check --fix .
	$(BACKEND) ruff format .
	$(MODEL_SERVER) ruff check --fix .
	$(MODEL_SERVER) ruff format .

typecheck:
	$(BACKEND) mypy
	$(MODEL_SERVER) mypy
	$(WEB) typecheck

test:
	$(BACKEND) pytest -q
	$(MODEL_SERVER) pytest -q
	$(WEB) test

test-models:
	$(MODEL_SERVER) pytest -q -m models

test-e2e:
	cd web && PLAYWRIGHT_BROWSERS_PATH=0 COREPACK_ENABLE_DOWNLOAD_PROMPT=0 NEXT_TELEMETRY_DISABLED=1 corepack pnpm test:e2e

test-all:
	$(BACKEND) pytest -q -m ''

ingest:
	$(BACKEND) lawqa ingest ../$(FILE) $(ARGS)

reindex:
	$(BACKEND) lawqa reindex

docs:
	$(BACKEND) lawqa documents list

SET ?= eval/datasets/seed.jsonl
MODE ?= retrieval
eval:
	$(BACKEND) lawqa eval $(MODE) --set ../$(SET) $(ARGS)

eval-compare:
	$(BACKEND) lawqa eval compare $(patsubst %,../%,$(wildcard eval/results/*.json))
