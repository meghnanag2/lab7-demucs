# Demucs worker (CPU) + Redis + MinIO
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Demucs needs ffmpeg; use minimal base
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Python deps (context is worker/)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY worker-server.py .

CMD ["python", "worker-server.py"]
