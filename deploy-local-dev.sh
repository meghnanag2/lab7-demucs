#!/usr/bin/env bash
set -euo pipefail

REGION="${REGION:-us-central1}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
REPO="${REPO:-lab7}"
NAMESPACE="${NAMESPACE:-lab7}"
PUSH="${PUSH:-true}"

if [[ -z "${PROJECT}" ]]; then
  echo "ERROR: PROJECT not set and gcloud default project not found."
  exit 1
fi

AR="https://${REGION}-docker.pkg.dev/${PROJECT}/${REPO}"
REST_IMG="${AR}/rest:v1"
WORKER_IMG="${AR}/worker:v1"

echo "===> Quick local dev deploy"
echo "PROJECT=${PROJECT}"
echo "REGION=${REGION}"
echo "REPO=${REPO}"
echo "NAMESPACE=${NAMESPACE}"
echo "PUSH=${PUSH}"
echo

echo "===> Build images..."
docker build -t "${REST_IMG}"  ./rest
docker build -t "${WORKER_IMG}" ./worker

if [[ "${PUSH}" == "true" ]]; then
  echo "===> Push images..."
  docker push "${REST_IMG}"
  docker push "${WORKER_IMG}"
else
  echo "===> Skipping push (PUSH=false). Make sure your cluster can access local images."
fi

echo "===> Ensure namespace..."
kubectl get ns "${NAMESPACE}" >/dev/null 2>&1 || kubectl create ns "${NAMESPACE}"

echo "===> Apply/refresh components..."
kubectl -n "${NAMESPACE}" apply -f redis-deployment.yaml
kubectl -n "${NAMESPACE}" apply -f minio-deployment.yaml
sed "s|<YOUR_AR_PREFIX>|${AR}|g" rest-deployment.yaml   | kubectl -n "${NAMESPACE}" apply -f -
sed "s|<YOUR_AR_PREFIX>|${AR}|g" worker-deployment.yaml | kubectl -n "${NAMESPACE}" apply -f -

echo "===> Restart app deployments for quick pickup..."
kubectl -n "${NAMESPACE}" rollout restart deploy/rest || true
kubectl -n "${NAMESPACE}" rollout restart deploy/worker || true

echo "===> Wait for app rollouts..."
kubectl -n "${NAMESPACE}" rollout status deploy/rest   --timeout=180s
kubectl -n "${NAMESPACE}" rollout status deploy/worker --timeout=180s

echo
echo "Local dev deploy done."
echo "Port-forward helpers:"
echo "  kubectl -n ${NAMESPACE} port-forward svc/rest 8080:8080"
echo "  kubectl -n ${NAMESPACE} port-forward svc/minio 9001:9001"
echo "  kubectl -n ${NAMESPACE} port-forward svc/minio 9000:9000"
