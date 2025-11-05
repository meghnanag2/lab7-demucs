#!/usr/bin/env python3

import os
import redis
import json
import time
import logging
from minio import Minio
from minio.error import S3Error
import subprocess
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [worker] %(message)s",
    handlers=[logging.StreamHandler()]
)

log = logging.getLogger("worker")

# Environment variables
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "rootpass123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

QUEUE_BUCKET = os.getenv("QUEUE_BUCKET", "queue")
OUTPUT_BUCKET = os.getenv("OUTPUT_BUCKET", "output")
DEMUCS_BASE = os.getenv("DEMUS_WORKDIR", "/app/demucs")

INPUT_DIR = os.path.join(DEMUCS_BASE, "input")
OUTPUT_DIR = os.path.join(DEMUCS_BASE, "output")
MODELS_DIR = os.path.join(DEMUCS_BASE, "models")

# Ensure directories exist
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# Connect to Redis
r = None
while not r:
    try:
        r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
        log.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
    except redis.ConnectionError as e:
        log.warning(f"Redis not ready yet: {e}. Retrying in 3 seconds...")
        r = None
        time.sleep(3)

# Connect to MinIO
minio_client = None
while not minio_client:
    try:
        minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE
        )
        minio_client.list_buckets()
        log.info(f"Connected to MinIO at {MINIO_ENDPOINT}")
    except Exception as e:
        log.warning(f"MinIO not ready yet: {e}. Retrying in 3 seconds...")
        minio_client = None
        time.sleep(3)

# Ensure required buckets exist
for bucket in [QUEUE_BUCKET, OUTPUT_BUCKET]:
    try:
        if not minio_client.bucket_exists(bucket):
            log.info(f"Creating bucket: {bucket}")
            minio_client.make_bucket(bucket)
    except Exception as e:
        log.error(f"Bucket check/create failed for {bucket}: {e}")

def download_from_minio(songhash):
    """Download MP3 file from MinIO to local input directory."""
    filename = f"{songhash}.mp3"
    local_path = os.path.join(INPUT_DIR, filename)
    log.info(f"Downloading {filename} from bucket '{QUEUE_BUCKET}' to {local_path}")
    try:
        minio_client.fget_object(QUEUE_BUCKET, filename, local_path)
        log.info(f"File successfully downloaded: {local_path}")
        return filename
    except S3Error as e:
        log.error(f"MinIO download failed: {e}")
        return None

def run_demucs(songhash, mp3_filename):
    """Run Demucs separation using Python module."""
    input_path = os.path.join(INPUT_DIR, mp3_filename)
    
    demucs_cmd = [
        "python3", "-m", "demucs.separate",
        "-o", OUTPUT_DIR,
        "--mp3",
        input_path
    ]

    log.info(f"Running Demucs for {songhash}...")
    log.info(f"Command: {' '.join(demucs_cmd)}")
    try:
        result = subprocess.run(demucs_cmd, check=True, capture_output=True, text=True)
        log.info(f"Demucs separation completed for {songhash}")
        log.debug(f"stdout: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"Demucs failed for {songhash}: {e}")
        log.error(f"stdout: {e.stdout}")
        log.error(f"stderr: {e.stderr}")
        return False

def upload_results_to_minio(songhash):
    """
    Upload separated tracks back to MinIO output bucket.
    DEMUCS outputs to: OUTPUT_DIR/htdemucs/{songhash}/{bass,drums,vocals,other}.mp3
    We upload as: {songhash}-{track}.mp3 (flat naming to match REST API)
    """
    # DEMUCS uses htdemucs directory (not mdx_extra_q)
    result_dir = os.path.join(OUTPUT_DIR, "htdemucs", songhash)
    
    if not os.path.exists(result_dir):
        log.error(f"No output directory found for {songhash}: {result_dir}")
        return False

    uploaded = False
    
    for root, _, files in os.walk(result_dir):
        for file in files:
            if file.endswith('.mp3'):
                local_file = os.path.join(root, file)
                # Flat naming: songhash-trackname.mp3 (e.g., "abc123-vocals.mp3")
                remote_name = f"{songhash}-{file}"
                try:
                    minio_client.fput_object(OUTPUT_BUCKET, remote_name, local_file)
                    log.info(f"Uploaded {remote_name} to {OUTPUT_BUCKET} bucket")
                    uploaded = True
                except S3Error as e:
                    log.error(f"Failed to upload {file} to MinIO: {e}")
    
    return uploaded

# Main Worker Loop
if __name__ == "__main__":
    log.info("=" * 60)
    log.info("Worker started. Listening for Redis jobs on 'toWorker'...")
    log.info("=" * 60)
    log.info(f"Config: REDIS={REDIS_HOST}:{REDIS_PORT}")
    log.info(f"Config: MINIO={MINIO_ENDPOINT}")
    log.info(f"Config: Buckets: {QUEUE_BUCKET} -> {OUTPUT_BUCKET}")
    log.info(f"Config: Working Dir: {DEMUCS_BASE}")
    log.info("=" * 60)
    
    while True:
        try:
            _, msg = r.blpop("toWorker", timeout=0)
            job = json.loads(msg)
            songhash = job.get("songhash")
            
            log.info("=" * 60)
            log.info(f"Job received: {job}")

            mp3_filename = download_from_minio(songhash)
            if not mp3_filename:
                log.error(f"Failed to download MP3 for {songhash}")
                continue

            if run_demucs(songhash, mp3_filename):
                if upload_results_to_minio(songhash):
                    log.info(f"✓ Job {songhash} completed successfully")
                else:
                    log.error(f"✗ Failed to upload results for {songhash}")
            else:
                log.error(f"✗ Job {songhash} failed during Demucs run")

            log.info("=" * 60)

        except Exception as e:
            log.exception(f"Unexpected error in worker loop: {e}")
            time.sleep(3)
