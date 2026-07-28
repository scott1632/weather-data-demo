.PHONY: up down reset ingest build test docs app

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

ingest:
	docker compose run --rm ingestion


