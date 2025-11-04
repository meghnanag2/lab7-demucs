from flask import Flask, request, jsonify, send_file
import redis, json, base64, os
from minio import Minio
from dotenv import load_dotenv
import sys
import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout
)
load_dotenv()



# MinIO configuration

MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "rootpass123")

QUEUE_BUCKET = "queue"
OUTPUT_BUCKET = "output"
queue_name="toWorker"
app = Flask(__name__)

REDIS_HOST = "redis"
REDIS_PORT = 6379

r = redis.Redis(
    host='redis',
    port=6379,
    decode_responses=True
)


# MinIO connection
minio_client = Minio(
    os.getenv("MINIO_ENDPOINT", "minio:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY", "rootuser"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "rootpass123"),
    secure=False
)



# Make sure buckets exist
for bucket in [QUEUE_BUCKET, OUTPUT_BUCKET]:
    if not minio_client.bucket_exists(bucket):
        minio_client.make_bucket(bucket)

@app.route("/", methods=["GET"])
def hello():
    return "<h1>Music Separation Server</h1><p>Use a valid endpoint</p>"

@app.route("/apiv1/separate", methods=["POST"])
def separate():
    try:
        data = request.get_json()
        mp3_b64 = data["mp3"]
        songhash = data.get("songhash") or os.urandom(16).hex()
        mp3_path = f"/tmp/{songhash}.mp3"

        # Save MP3 locally
        with open(mp3_path, "wb") as f:
            f.write(base64.b64decode(mp3_b64))
        logging.info(f"[rest-server] Saved MP3 {mp3_path}")

        # Upload to MinIO queue bucket
        minio_client.fput_object(QUEUE_BUCKET, f"{songhash}.mp3", mp3_path)
        logging.info(f"[rest-server] Uploaded {songhash}.mp3 to {QUEUE_BUCKET}")

        # Push job to Redis
        
        res=r.lpush(queue_name, json.dumps({
            "songhash": songhash,
            "callback": data.get("callback")
        }))
        logging.info(f"[rest-server] redis {res}")
        logging.info(f"[rest-server] redis-host {REDIS_HOST}")
        logging.info(f"[rest-server] Job enqueued for {songhash}")

        return jsonify({"hash": songhash, "reason": "Song enqueued for separation"})
    except Exception as e:
        logging.info(f"[rest-server] Error in /apiv1/separate: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/apiv1/queue", methods=["GET"])
def get_queue():
    try:
        queue = [json.loads(x) for x in r.lrange(queue_name, 0, -1)]
        return jsonify({"queue": queue})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/apiv1/track/<songhash>/<track>", methods=["GET"])
def get_track(songhash, track):
    try:
        track_name = f"{songhash}-{track}.mp3"
        local_path = f"/tmp/{track_name}"
        minio_client.fget_object(OUTPUT_BUCKET, track_name, local_path)
        return send_file(local_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/apiv1/remove/<songhash>/<track>", methods=["DELETE"])
def remove_track(songhash, track):
    try:
        track_name = f"{songhash}-{track}.mp3"
        minio_client.remove_object(OUTPUT_BUCKET, track_name)
        return jsonify({"removed": track_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
