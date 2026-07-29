.PHONY: up down reset ingest build test docs app fresh clean

setup:
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
	docker compose up -d streamlit dbt-docs cloudbeaver airflow-webserver airflow-scheduler

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
	docker compose up -d postgres streamlit cloudbeaver dbt-docs airflow-webserver airflow-scheduler
	@echo ""
	@echo "✅ Fresh start complete!"
	@echo ""
	@echo "Open http://localhost:8501 and use the Pipeline Controls to:"
	@echo "  1. Run ingestion"
	@echo "  2. Run dbt build"
	@echo "  3. Run dbt tests"
	@echo ""
	@echo "Or open the Airflow UI (http://localhost:8088) and trigger the"
	@echo "weather_pipeline DAG to run the same steps on a schedule."

clean:
	docker compose down -v
	# docker image rm -f weather-data-demo-ingestion weather-data-demo-dbt weather-data-demo-streamlit

