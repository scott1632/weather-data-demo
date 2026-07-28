.PHONY: up down reset ingest build test docs

setup:
	docker network inspect data-platform >/dev/null 2>&1 || docker network create data-platform
	docker compose up -d

up:
	docker compose up -d

down:
	docker compose down

reset:
	docker compose down -v
	docker compose up -d postgres
	sleep 5
	docker compose run --rm ingestion
	docker compose run --rm dbt dbt build
	docker compose up -d cloudbeaver

ingest:
	docker compose run --rm ingestion
analytics_staging
build:
	docker compose run --rm dbt dbt build

test:
	docker compose run --rm dbt dbt test

docs:
	docker compose up -d dbt-docs

