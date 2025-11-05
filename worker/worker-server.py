#!/usr/bin/env python3
import os, sys, time, json, logging, subprocess
import redis
from minio import Minio
from minio.error import S3Error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WORKER] %(message)s",
    stream=sys.stdout,
)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "rootpass123")

QUEUE_BUCKET = "queue"
OUTPUT_BUCKET = "output"

r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

minio = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False,
)

def process(songhash):
    input_file = f"/tmp/{songhash}.mp3"
    output_dir = f"/tmp/output"

    minio.fget_object(QUEUE_BUCKET, f"{songhash}.mp3", input_file)

    cmd = ["python3", "-m", "demucs.separate", "-o", output_dir, input_file]
    subprocess.run(cmd, check=True)

    for track in ["vocals.mp3", "bass.mp3", "drums.mp3", "other.mp3"]:
        full_path = f"{output_dir}/htdemucs/{songhash}/{track}"
        if os.path.exists(full_path):
            minio.fput_object(OUTPUT_BUCKET, f"{songhash}-{track}", full_path)
            logging.info(f"Uploaded: {songhash}-{track}")

if __name__ == "__main__":
    logging.info("Worker running…")
    while True:
        _, msg = r.blpop("toWorker")
        job = json.loads(msg)
        try:
            logging.info(f"Processing {job['songhash']}")
            process(job["songhash"])
            logging.info(f"Done {job['songhash']}")
        except Exception as e:
            logging.error(f"Error: {e}")
