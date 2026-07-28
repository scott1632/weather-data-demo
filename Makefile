.PHONY: up down reset ingest build test docs app fresh clean

setup:
	# docker network inspect data-platform >/dev/null 2>&1 || docker network create data-platform
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
	docker compose up -d streamlit dbt-docs cloudbeaver

ingest:
	docker compose run --rm ingestion

build:
	docker compose run --rm dbt dbt build

test:
	docker compose run --rm dbt dbt test

docs:
	docker compose up -d dbt-docs

app:
	docker compose up -d streamlit

fresh:
	docker compose down -v
	# docker image rm -f weather-data-demo-ingestion weather-data-demo-dbt weather-data-demo-streamlit
	# docker network rm data-platform 2>/dev/null || true
	# docker network create data-platform
	docker compose up -d postgres streamlit cloudbeaver dbt-docs
	@echo ""
	@echo "✅ Fresh start complete!"
	@echo ""
	@echo "Open http://localhost:8501 and use the Pipeline Controls to:"
	@echo "  1. Run ingestion"
	@echo "  2. Run dbt build"
	@echo "  3. Run dbt tests"

clean:
	docker compose down -v
	# docker image rm -f weather-data-demo-ingestion weather-data-demo-dbt weather-data-demo-streamlit
	# docker network rm data-platform 2>/dev/null || true

