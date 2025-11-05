from flask import Flask, request, jsonify, send_file
import os, sys, json, base64, logging, tempfile
import redis
from minio import Minio
from minio.error import S3Error

# --- Logging -----------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("rest")

# --- Config (env first, with sensible defaults) -------------------------------
REDIS_HOST   = os.getenv("REDIS_HOST", "redis")
REDIS_PORT   = int(os.getenv("REDIS_PORT", "6379"))
QUEUE_NAME   = os.getenv("QUEUE_NAME", "toWorker")

MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "rootpass123")
MINIO_SECURE     = os.getenv("MINIO_SECURE", "false").lower() == "true"

QUEUE_BUCKET  = os.getenv("QUEUE_BUCKET", "queue")
OUTPUT_BUCKET = os.getenv("OUTPUT_BUCKET", "output")

MAX_MP3_MB = int(os.getenv("MAX_MP3_MB", "20"))  # base64 payload guard

# --- Clients ------------------------------------------------------------------
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)

def ensure_bucket(name: str):
    try:
        if not minio_client.bucket_exists(name):
            minio_client.make_bucket(name)
            log.info(f"Created bucket: {name}")
    except S3Error as e:
        log.error(f"Bucket check/create failed for {name}: {e}")
        raise

for b in (QUEUE_BUCKET, OUTPUT_BUCKET):
    ensure_bucket(b)

# --- App ----------------------------------------------------------------------
app = Flask(__name__)

@app.get("/")
def root():
    return "<h1>Music Separation Server</h1><p>Try /healthz or POST /apiv1/separate</p>"

@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200

@app.get("/readyz")
def readyz():
    try:
        r.ping()
        # trivial MinIO op: list objects in queue bucket (no fetch)
        _ = minio_client.list_objects(QUEUE_BUCKET, max_keys=1)
        return jsonify({"ready": True}), 200
    except Exception as e:
        return jsonify({"ready": False, "error": str(e)}), 503

@app.post("/apiv1/separate")
def separate():
    try:
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415

        data = request.get_json(silent=True) or {}
        mp3_b64 = data.get("mp3")
        if not mp3_b64:
            return jsonify({"error": "Field 'mp3' (base64) is required"}), 400

        # quick size guard (~4/3 overhead for base64)
        approx_mb = (len(mp3_b64) * 3) / (4 * 1024 * 1024)
        i
