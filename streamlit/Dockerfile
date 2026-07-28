FROM python:3.12-slim

WORKDIR /app

COPY streamlit/requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY streamlit/app.py .

COPY ingestion /app/ingestion

COPY dbt /app/dbt

WORKDIR /app

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]

