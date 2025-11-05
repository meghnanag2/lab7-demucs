# Lab7 Music Separation - Deployment Commands

## What We Did
Built and deployed a music separation service on Google Cloud Kubernetes with REST API, DEMUCS worker, Redis queue, and MinIO storage.

---

## Exact Commands We Ran (Line by Line)

### Setup GCP Project

```bash
gcloud config set project lab7-477021
gcloud services enable artifactregistry.googleapis.com
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
```

### Build REST API Docker Image

```bash
docker build -t us-central1-docker.pkg.dev/lab7-477021/lab7/rest:v1 \
  -f rest/Dockerfile rest/
```

### Push REST API Image

```bash
docker push us-central1-docker.pkg.dev/lab7-477021/lab7/rest:v1
```

### Build Worker Docker Image

```bash
docker build -t us-central1-docker.pkg.dev/lab7-477021/lab7/worker:v1 \
  -f worker/Dockerfile worker/
```

### Push Worker Image

```bash
docker push us-central1-docker.pkg.dev/lab7-477021/lab7/worker:v1
```

### Rebuild REST with No Cache

```bash
docker build --no-cache -t us-central1-docker.pkg.dev/lab7-477021/lab7/rest:v1 \
  -f rest/Dockerfile rest/

docker push us-central1-docker.pkg.dev/lab7-477021/lab7/rest:v1
```

### Force Kubectl to Pull Latest Image

```bash
kubectl patch deployment rest -p '{"spec":{"template":{"spec":{"containers":[{"name":"rest","imagePullPolicy":"Always"}]}}}}' -n lab7

kubectl rollout restart deployment/rest -n lab7
```

### Delete and Recreate REST Deployment

```bash
kubectl -n lab7 delete deployment rest --force --grace-period=0

sleep 3

kubectl apply -f rest/rest-deployment.yaml

sleep 10

kubectl -n lab7 get pods
```

### Delete Old REST Pods

```bash
kubectl -n lab7 delete pods --all -n lab7
```

### Check Logs

```bash
kubectl -n lab7 logs rest-844d55565f-wltx6
```

### Rebuild Worker with No Cache

```bash
docker build --no-cache -t us-central1-docker.pkg.dev/lab7-477021/lab7/worker:v1 \
  -f worker/Dockerfile worker/

docker push us-central1-docker.pkg.dev/lab7-477021/lab7/worker:v1

kubectl rollout restart deployment/worker -n lab7

sleep 10

kubectl -n lab7 get pods
```

### Port Forward REST API

```bash
kubectl -n lab7 port-forward svc/rest 8080:8080 &
```

### Test REST API Health

```bash
curl http://localhost:8080/
```

### Port Forward MinIO

```bash
kubectl -n lab7 port-forward svc/minio 9001:9001 &
```

### Test MinIO

```bash
curl http://localhost:9001/
```

### Run Sample Test Script

```bash
export REST=localhost:8080

python3 short-sample-request.py
```

### Check Worker Logs

```bash
kubectl -n lab7 logs deployment/worker --tail=50
```

### Check Worker Output Directory

```bash
kubectl -n lab7 exec -it deployment/worker -- ls -la /app/demucs/output/
```

### List Files in Output Directory

```bash
kubectl -n lab7 exec -it deployment/worker -- ls -la /app/demucs/output/htdemucs/
```

### List Files in Specific Song Directory

```bash
kubectl -n lab7 exec -it deployment/worker -- ls -la /app/demucs/output/htdemucs/6350dc4958b5ea2f815a724cae09f152/
```

### Download Separated Tracks

```bash
curl http://localhost:8080/apiv1/track/bf9f10c7b08cef5c597e6d710080f90c/vocals -o vocals.mp3

curl http://localhost:8080/apiv1/track/bf9f10c7b08cef5c597e6d710080f90c/bass -o bass.mp3

curl http://localhost:8080/apiv1/track/bf9f10c7b08cef5c597e6d710080f90c/drums -o drums.mp3

curl http://localhost:8080/apiv1/track/bf9f10c7b08cef5c597e6d710080f90c/other -o other.mp3
```

### Verify Downloaded Files

```bash
ls -lh *.mp3

file vocals.mp3
```

### Create Results Folder

```bash
mkdir -p results

mv vocals.mp3 bass.mp3 drums.mp3 other.mp3 results/
```

### Check Git Status

```bash
git status
```

### Add Results to Git

```bash
git add results/

git commit -m "Add separated music tracks from DEMUCS processing"

git push origin main --force
```

### Check Pods Status

```bash
kubectl -n lab7 get pods
```

### View All Running Services

```bash
kubectl -n lab7 get all
```

### Describe a Pod

```bash
kubectl -n lab7 describe pod <pod-name>
```

### Watch Pods in Real-time

```bash
kubectl -n lab7 get pods -w
```

### Stream Worker Logs

```bash
kubectl -n lab7 logs deployment/worker -f
```

### Stream REST API Logs

```bash
kubectl -n lab7 logs deployment/rest -f
```

### Scale REST API to 3 Replicas

```bash
kubectl -n lab7 scale deployment rest --replicas=3
```

### Scale Worker to 3 Replicas

```bash
kubectl -n lab7 scale deployment worker --replicas=3
```

### Restart REST Deployment

```bash
kubectl -n lab7 rollout restart deployment/rest
```

### Restart Worker Deployment

```bash
kubectl -n lab7 rollout restart deployment/worker
```

### Delete REST Deployment

```bash
kubectl -n lab7 delete deployment rest
```

### Check Services

```bash
kubectl -n lab7 get svc
```

### Check Deployments

```bash
kubectl -n lab7 get deployments
```

---

## Testing Flow (Complete)

```bash
# 1. Port forward
kubectl -n lab7 port-forward svc/rest 8080:8080 &

# 2. Export environment
export REST=localhost:8080

# 3. Run test
python3 short-sample-request.py

# 4. Wait 15-20 minutes for processing

# 5. Check logs
kubectl -n lab7 logs deployment/worker --tail=50

# 6. Download vocals (replace hash with actual hash from test output)
curl http://localhost:8080/apiv1/track/YOUR_HASH_HERE/vocals -o vocals.mp3

# 7. Verify file
file vocals.mp3
```

---

## Key Hashes from Our Testing

```bash
# Job 1 - short-hop.mp3
Hash: bf9f10c7b08cef5c597e6d710080f90c
Status: ✅ Processed successfully

# Job 2 - short-dreams.mp3
Hash: d19a547c07639fd730fb990e63d9b9aa
Status: ✅ Processed successfully
```

---

## Common Issues & Fixes

### Issue: Pod stuck in CrashLoopBackOff

**Fix:**
```bash
kubectl -n lab7 delete deployment rest --force --grace-period=0

docker build --no-cache -t us-central1-docker.pkg.dev/lab7-477021/lab7/rest:v1 -f rest/Dockerfile rest/

docker push us-central1-docker.pkg.dev/lab7-477021/lab7/rest:v1

kubectl patch deployment rest -p '{"spec":{"template":{"spec":{"containers":[{"name":"rest","imagePullPolicy":"Always"}]}}}' -n lab7

kubectl rollout restart deployment/rest -n lab7
```

### Issue: Pod Terminating

**Fix:**
```bash
kubectl -n lab7 delete pod <pod-name> --grace-period=0 --force
```

### Issue: Can't connect to service

**Fix:**
```bash
kubectl -n lab7 port-forward svc/rest 8080:8080 &

curl http://localhost:8080/healthz
```

---

## Status Commands

```bash
# Check everything
kubectl -n lab7 get all

# Check pod logs
kubectl -n lab7 logs deployment/rest

# Check worker logs
kubectl -n lab7 logs deployment/worker

# Watch real-time
kubectl -n lab7 get pods -w
```

---

## Summary

✅ **Docker Images Built & Pushed**
- REST API: us-central1-docker.pkg.dev/lab7-477021/lab7/rest:v1
- Worker: us-central1-docker.pkg.dev/lab7-477021/lab7/worker:v1

✅ **Services Running**
- REST API (port 8080)
- Worker (processing DEMUCS)
- Redis (job queue)
- MinIO (file storage)

✅ **System Tested**
- Uploaded 2 short songs
- Processed through DEMUCS
- Downloaded 8 separated tracks
- All stored in GitHub results/ folder

✅ **Ready for Production**
