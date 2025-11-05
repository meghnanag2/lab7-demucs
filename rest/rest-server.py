from flask import Flask, request, jsonify, send_file
import os, sys, json, base64, tempfile, logging
import redis
from minio import Minio
from minio.error import S3Error

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [REST] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("rest")

# --- ENV CONFIG ---
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
QUEUE_NAME = os.getenv("QUEUE_NAME", "toWorker")

MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "rootpass123")
MINIO_SECURE     = False

QUEUE_BUCKET  = "queue"
OUTPUT_BUCKET = "output"

# --- CLIENTS ---
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)

def ensure_bucket(b):
    try:
        if not minio_client.bucket_exists(b):
            minio_client.make_bucket(b)
            log.info(f"Created bucket: {b}")
    except Exception as e:
        log.error(f"Bucket check/create failed for {b}: {e}")
        raise

for b in (QUEUE_BUCKET, OUTPUT_BUCKET):
    ensure_bucket(b)

app = Flask(__name__)

@app.get("/")
def root():
    return "<h2>Music Separation API</h2>POST /apiv1/separate"

@app.get("/healthz")
def healthz():
    try:
        r.ping()
        list(minio_client.list_buckets())
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 503

@app.post("/apiv1/separate")
def separate():
    try:
        data = request.get_json()
        mp3_b64 = data.get("mp3")
        if not mp3_b64:
            return jsonify({"error": "Field 'mp3' required"}), 400

        songhash = data.get("songhash") or os.urandom(16).hex()

        with tempfile.TemporaryDirectory() as tmpd:
            mp3_file = os.path.join(tmpd, f"{songhash}.mp3")
            with open(mp3_file, "wb") as f:
                f.write(base64.b64decode(mp3_b64))

            minio_client.fput_object(QUEUE_BUCKET, f"{songhash}.mp3", mp3_file)

        r.lpush(QUEUE_NAME, json.dumps({"songhash": songhash}))
        log.info(f"Queued job: {songhash}")

        return jsonify({"hash": songhash, "status": "queued"}), 200

    except Exception as e:
        log.exception("Failure in /separate")
        return jsonify({"error": str(e)}), 500

@app.get("/apiv1/track/<songhash>/<track>")
def get_track(songhash, track):
    name = f"{songhash}-{track}.mp3"
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmpf:
            path = tmpf.name
        minio_client.fget_object(OUTPUT_BUCKET, name, path)
        return send_file(path, as_attachment=True, download_name=name)
    except S3Error:
        return jsonify({"error": "Track not ready"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
