#!/usr/bin/env python3

import os
import sys
import json
import base64
import logging
import tempfile
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
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

# --- Clients -----------------------------------------------------------------
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

# --- FastAPI App -----------------------------------------------------------------
app = FastAPI(title="Music Separation API", version="1.0.0")

@app.get("/")
def root():
    return {
        "service": "Music Separation Server",
        "version": "1.0.0",
        "endpoints": {
            "GET /healthz": "Health check",
            "GET /readyz": "Readiness check",
            "POST /apiv1/separate": "Queue song for separation",
            "GET /apiv1/queue": "View queued jobs",
            "GET /apiv1/track/{songhash}/{track}": "Download separated track",
            "DELETE /apiv1/remove/{songhash}/{track}": "Delete track"
        }
    }

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/readyz")
def readyz():
    try:
        r.ping()
        # Try one trivial MinIO op: fetch at most one listing item
        _one = next(minio_client.list_objects(QUEUE_BUCKET, recursive=False), None)
        return {"ready": True, "minio_seen": bool(_one)}
    except Exception as e:
        raise HTTPException(status_code=503, detail={"ready": False, "error": str(e)})

@app.post("/apiv1/separate")
def separate(data: dict):
    try:
        mp3_b64 = data.get("mp3")
        if not mp3_b64:
            raise HTTPException(status_code=400, detail={"error": "Field 'mp3' (base64) is required"})

        # quick size guard (~4/3 overhead for base64)
        approx_mb = (len(mp3_b64) * 3) / (4 * 1024 * 1024)
        if approx_mb > MAX_MP3_MB:
            raise HTTPException(status_code=413, detail={"error": f"MP3 too large (~{approx_mb:.1f} MiB), limit is {MAX_MP3_MB} MiB"})

        songhash = data.get("songhash") or os.urandom(16).hex()

        # write temp mp3 and upload to MinIO queue bucket
        with tempfile.TemporaryDirectory() as tmpd:
            mp3_path = os.path.join(tmpd, f"{songhash}.mp3")
            with open(mp3_path, "wb") as f:
                f.write(base64.b64decode(mp3_b64))
            minio_client.fput_object(QUEUE_BUCKET, f"{songhash}.mp3", mp3_path)
            log.info(f"Queued object uploaded: {QUEUE_BUCKET}/{songhash}.mp3")

        # push a job to Redis (worker only needs the hash)
        job = {"songhash": songhash}
        if data.get("callback"):
            job["callback"] = data["callback"]

        r.lpush(QUEUE_NAME, json.dumps(job))
        log.info(f"Enqueued job to '{QUEUE_NAME}': {job}")

        return {"hash": songhash, "reason": "Song enqueued for separation"}

    except HTTPException:
        raise
    except Exception as e:
        log.exception("Error in /apiv1/separate")
        raise HTTPException(status_code=500, detail={"error": str(e)})

@app.get("/apiv1/queue")
def get_queue():
    try:
        items = [json.loads(x) for x in r.lrange(QUEUE_NAME, 0, 49)]
        return {"queue": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})

@app.get("/apiv1/track/{songhash}/{track}")
def get_track(songhash: str, track: str):
    """
    track in {vocals, drums, bass, other}
    Worker uploads flat names: <songhash>-<track>.mp3 to OUTPUT_BUCKET
    """
    try:
        object_name = f"{songhash}-{track}.mp3"
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmpf:
            tmp_path = tmpf.name
        minio_client.fget_object(OUTPUT_BUCKET, object_name, tmp_path)
        return FileResponse(tmp_path, media_type="audio/mpeg", filename=object_name)
    except S3Error as e:
        raise HTTPException(status_code=404, detail={"error": f"MinIO: {e}"})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})

@app.delete("/apiv1/remove/{songhash}/{track}")
def remove_track(songhash: str, track: str):
    try:
        object_name = f"{songhash}-{track}.mp3"
        minio_client.remove_object(OUTPUT_BUCKET, object_name)
        return {"removed": object_name}
    except S3Error as e:
        raise HTTPException(status_code=404, detail={"error": f"MinIO: {e}"})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
