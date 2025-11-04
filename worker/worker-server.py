#!/usr/bin/env python3

import os
import redis
import json
import time
import logging
from minio import Minio
from minio.error import S3Error
import subprocess

logging.basicConfig(
level=logging.INFO,
format="%(asctime)s [%(levelname)s] [worker] %(message)s",
handlers=[logging.StreamHandler()]
)

# --------------------------

# Environment variables

# --------------------------

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "rootpass123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "queue")
DEMUCS_BASE = os.getenv("DEMUS_WORKDIR", "/app/demucs")

INPUT_DIR = os.path.join(DEMUCS_BASE, "input")
OUTPUT_DIR = os.path.join(DEMUCS_BASE, "output")
MODELS_DIR = os.path.join(DEMUCS_BASE, "models")

# --------------------------

# Ensure directories exist

# --------------------------

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# --------------------------

# Connect to Redis

# --------------------------


while True:
    try:
        r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
        logging.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        break
    except redis.ConnectionError:
        logging.warning("Redis not ready yet. Retrying in 3 seconds...")
        time.sleep(3)



while True:
    try:
        minio_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
        )
        # Test connection by listing buckets
        minio_client.list_buckets()
        logging.info(f"Connected to MinIO at {MINIO_ENDPOINT}")
        break
    except S3Error as e:
        logging.warning(f"MinIO not ready yet: {e}. Retrying in 3 seconds...")
        time.sleep(3)

# --------------------------

# Connect to MinIO

# --------------------------

minioClient = Minio(
MINIO_ENDPOINT,
access_key=MINIO_ACCESS_KEY,
secret_key=MINIO_SECRET_KEY,
secure=False
)

logging.info(f"Connected to MinIO at {MINIO_ENDPOINT}")

# Ensure required buckets exist

for bucket in [MINIO_BUCKET, "output"]:
    if not minioClient.bucket_exists(bucket):
        logging.info(f"Bucket '{bucket}' does not exist. Creating...")
        minioClient.make_bucket(bucket)

# --------------------------

# Functions

# --------------------------

def download_from_minio(songhash):
    """Download MP3 file from MinIO to local input directory."""
    filename = f"{songhash}.mp3"
    local_path = os.path.join(INPUT_DIR, filename)
    logging.info(f"Downloading {filename} from bucket '{MINIO_BUCKET}' to {local_path}")
    try:
        minioClient.fget_object(MINIO_BUCKET, filename, local_path)
        logging.info(f"File successfully downloaded: {local_path}")
        return filename
    except S3Error as e:
        logging.error(f"MinIO download failed: {e}")
        return None

def run_demucs(songhash, mp3_filename):
    """Run Demucs separation using Python module."""
    input_path = os.path.join(INPUT_DIR, mp3_filename)
    output_path = OUTPUT_DIR  # outputs go here

    demucs_cmd = [
        "python3", "-m", "demucs.separate",
        "-o", output_path,
        input_path
    ]

    logging.info(f"Running Demucs for {songhash}...")
    try:
        subprocess.run(demucs_cmd, check=True)
        logging.info(f"Demucs separation completed for {songhash}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Demucs failed for {songhash}: {e}")
        return False
    
def upload_results_to_minio(songhash):
    """Upload separated tracks back to MinIO output bucket."""
    result_dir = os.path.join(OUTPUT_DIR, "htdemucs", songhash)
    if not os.path.exists(result_dir):
        logging.error(f"No output directory found for {songhash}: {result_dir}")
        return

    
    for root, _, files in os.walk(result_dir):
        for file in files:
            local_file = os.path.join(root, file)
            remote_path = f"results/{songhash}/{file}"
            try:
                minioClient.fput_object("output", remote_path, local_file)
                logging.info(f"Uploaded {remote_path} to output bucket.")
            except S3Error as e:
                logging.error(f"Failed to upload {file} to MinIO: {e}")
    

# --------------------------

# Main Worker Loop

# --------------------------

if __name__ == "__main__":
    logging.info("Worker started. Listening for Redis jobs on 'toWorker'...")

    
    while True:
        try:
            _, msg = r.blpop("toWorker")
            job = json.loads(msg)
            songhash = job.get("songhash")
            logging.info(f"Job received: {job}")

            mp3_path = download_from_minio(songhash)
            if not mp3_path:
                continue

            if run_demucs(songhash, mp3_path):
                upload_results_to_minio(songhash)
                logging.info(f"Job {songhash} completed successfully.")
            else:
                logging.error(f"Job {songhash} failed during Demucs run.")

        except Exception as e:
            logging.exception(f"Unexpected error: {e}")
            time.sleep(3)
    
