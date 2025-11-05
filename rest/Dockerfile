# FastAPI + Redis + MinIO client
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (curl only for health/debug), keep image small
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY rest/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY rest/rest-server.py

# Uvicorn on 0.0.0.0:8080
EXPOSE 8080
CMD ["uvicorn", "rest-server:app", "--host", "0.0.0.0", "--port", "8080"]
