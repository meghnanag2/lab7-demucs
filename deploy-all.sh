#!/usr/bin/env bash
set -euo pipefail

### ---- Config (override with env) ----
REGION="${REGION:-us-central1}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
REPO="${REPO:-lab7}"                   # Artifact Registry repo name
NAMESPACE="${NAMESPACE:-lab7}"
APPLY_INGRESS="${APPLY_INGRESS:-true}" # set to false to skip Ingress

if [[ -z "${PROJECT}" ]]; then
  echo "ERROR: PROJECT not set and gcloud default project not found."
  echo "Run: gcloud config set project <PROJECT_ID>  or export PROJECT=<PROJECT_ID>"
  exit 1
fi

AR="https://${REGION}-docker.pkg.dev/${PROJECT}/${REPO}"
REST_IMG="${AR}/rest:v1"
WORKER_IMG="${AR}/worker:v1"

echo "===> Using:"
echo "  PROJECT:      ${PROJECT}"
echo "  REGION:       ${REGION}"
echo "  REPO:         ${REPO}"
echo "  NAMESPACE:    ${NAMESPACE}"
echo "  REST_IMG:     ${REST_IMG}"
echo "  WORKER_IMG:   ${WORKER_IMG}"
echo

### ---- Build & push images ----
echo "===> Building images..."
docker build -t "${REST_IMG}"  ./rest
docker build -t "${WORKER_IMG}" ./worker

echo "===> Pushing images..."
docker push "${REST_IMG}"
docker push "${WORKER_IMG}"

### ---- Create namespace (idempotent) ----
echo "===> Ensuring namespace ${NAMESPACE} exists..."
kubectl get ns "${NAMESPACE}" >/dev/null 2>&1 || kubectl create ns "${NAMESPACE}"

### ---- Deploy infra: Redis + MinIO ----
echo "===> Applying Redis & MinIO..."
kubectl -n "${NAMESPACE}" apply -f redis-deployment.yaml
kubectl -n "${NAMESPACE}" apply -f minio-deployment.yaml

### ---- Deploy REST & Worker (inject image prefixes) ----
echo "===> Applying REST & Worker..."
# substitute image registry in the manifests
sed "s|<YOUR_AR_PREFIX>|${AR}|g" rest-deployment.yaml   | kubectl -n "${NAMESPACE}" apply -f -
sed "s|<YOUR_AR_PREFIX>|${AR}|g" worker-deployment.yaml | kubectl -n "${NAMESPACE}" apply -f -

### ---- (Optional) Ingress ----
if [[ "${APPLY_INGRESS}" == "true" ]]; then
  if [[ -f rest-ingress.yaml ]]; then
    echo "===> Applying REST Ingress (may take a few minutes to provision)..."
    kubectl -n "${NAMESPACE}" apply -f rest-ingress.yaml
  else
    echo "NOTE: rest-ingress.yaml not found; skipping Ingress."
  fi
fi

### ---- Wait for rollouts ----
echo "===> Waiting for rollouts..."
kubectl -n "${NAMESPACE}" rollout status deploy/redis   --timeout=120s || true
kubectl -n "${NAMESPACE}" rollout status deploy/minio   --timeout=180s || true
kubectl -n "${NAMESPACE}" rollout status deploy/rest    --timeout=180s
kubectl -n "${NAMESPACE}" rollout status deploy/worker  --timeout=180s

### ---- Tips ----
echo
echo "Deploy complete."
echo "Use these for local access (in separate terminals):"
echo "  # REST API"
echo "  kubectl -n ${NAMESPACE} port-forward svc/rest 8080:8080"
echo
echo "  # MinIO Console (login with minio-secret creds)"
echo "  kubectl -n ${NAMESPACE} port-forward svc/minio 9001:9001"
echo
echo "  # MinIO API"
echo "  kubectl -n ${NAMESPACE} port-forward svc/minio 9000:9000"
echo
echo "If you enabled Ingress, watch its external IP with:"
echo "  kubectl -n ${NAMESPACE} get ingress -w"
