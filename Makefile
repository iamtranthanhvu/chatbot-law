SHELL := /bin/bash
COMPOSE_DEV := docker compose -f compose.dev.yml
BACKEND := cd backend && uv run

.PHONY: setup infra-up infra-down migrate lint format typecheck test test-all ingest reindex docs

setup:
	@test -f .env || cp .env.example .env
	cd backend && uv sync

infra-up:
	$(COMPOSE_DEV) up -d --wait

infra-down:
	$(COMPOSE_DEV) down

lint:
	$(BACKEND) ruff check . && $(BACKEND) ruff format --check .

format:
	$(BACKEND) ruff check --fix . && $(BACKEND) ruff format .

typecheck:
	$(BACKEND) mypy

test:
	$(BACKEND) pytest -q

test-all:
	$(BACKEND) pytest -q -m ''

ingest:
	$(BACKEND) lawqa ingest ../$(FILE) $(ARGS)
