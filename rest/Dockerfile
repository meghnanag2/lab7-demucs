# ============================================================================
# Worker Service Dockerfile for Lab7 Music Separation
# ============================================================================

FROM xserrat/facebook-demucs:latest

# Set working directory
WORKDIR /app

# Create necessary directories for DEMUCS processing
RUN mkdir -p /app/demucs/input /app/demucs/output /app/demucs/models && \
    chmod -R 777 /app/demucs

# Copy Python requirements
COPY requirements.txt .

# Install additional Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy worker server code
COPY worker-server.py .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python3 -c "import redis; r = redis.Redis(host='redis', port=6379); r.ping()" || exit 1

# Set the command to run when container starts
CMD ["python3", "worker-server.py"]
