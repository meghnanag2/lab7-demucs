FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY rest/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rest/rest-server.py .

EXPOSE 5000
CMD ["python", "rest-server.py"]
