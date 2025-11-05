# ============================================================================
# Worker Service Dockerfile for Lab7 Music Separation
# ============================================================================
# This Dockerfile extends the pre-built DEMUCS image with worker service code
# DEMUCS base image already includes:
#   - Python 3.9+
#   - PyTorch with audio processing
#   - DEMUCS library
#   - All dependencies for audio separation
#
# We only need to add:
#   - Additional Python packages (redis, minio, etc.)
#   - Worker service code
# ============================================================================

FROM xserrat/facebook-demucs:latest

# Set working directory
WORKDIR /app

# Create necessary directories for DEMUCS processing
RUN mkdir -p /app/demucs/input /app/demucs/output /app/demucs/models && \
    chmod -R 777 /app/demucs

# Copy Python requirements (must be in build context)
COPY requirements.txt .

# Install additional Python dependencies
# Using --no-cache-dir to keep image size smaller
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy worker server code
COPY worker-server.py .

# Create a non-root user for security (optional but recommended)
# RUN useradd -m worker && chown -R worker /app
# USER worker

# Health check (optional)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python3 -c "import redis; r = redis.Redis(host='redis', port=6379); r.ping()" || exit 1

# Set the command to run when container starts
CMD ["python3", "worker-server.py"]

# ============================================================================
# BUILD INSTRUCTIONS:
# ============================================================================
# From the worker/ directory:
#
#   docker build -t <REGION>-docker.pkg.dev/<PROJECT>/<REPO>/worker:v1 \
#     -f Dockerfile .
#
# Example:
#   docker build -t us-central1-docker.pkg.dev/my-project/lab7/worker:v1 \
#     -f Dockerfile .
#
# Then push to registry:
#   docker push us-central1-docker.pkg.dev/my-project/lab7/worker:v1
#
# ============================================================================
# NOTES:
# ============================================================================
# - Base image is xserrat/facebook-demucs:latest (~3.5GB)
# - We add minimal additional dependencies
# - DEMUCS models will be downloaded on first run (~2GB)
# - Working directory /app/demucs stores temporary files during processing
# - Redis health check verifies worker can connect to Redis service
#
# ============================================================================
