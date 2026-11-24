#!/usr/bin/env bash
# Deploiement d'un environnement : build + push des images (optionnel) puis kubectl apply -k.
# La CI executerait les memes commandes (voir .github/workflows/ci.yml, job "deploy").
#
#   scripts/deploy.sh <dev|test|prod> <tag> [--build]
set -euo pipefail
ENVIRONMENT="${1:?usage: deploy.sh <dev|test|prod> <tag> [--build]}"
TAG="${2:?tag image manquant}"
BUILD="${3:-}"
REGISTRY="${REGISTRY:-localhost:5001}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NS="helpdesk-${ENVIRONMENT}"

if [ "$BUILD" = "--build" ]; then
  for img in backend worker frontend backup; do
    echo ">> build ${img}:${TAG}"
    docker build -q --build-arg APP_VERSION="$TAG" -t "${REGISTRY}/helpdesk/${img}:${TAG}" "$ROOT/${img}" >/dev/null
    docker push -q "${REGISTRY}/helpdesk/${img}:${TAG}" >/dev/null
  done
fi

# on travaille sur une copie pour fixer les tags sans modifier le depot
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp -r "$ROOT/k8s" "$WORK/k8s"
sed -i "s|newTag: .*|newTag: \"${TAG}\" }|" "$WORK/k8s/overlays/${ENVIRONMENT}/kustomization.yaml"
sed -i "s|localhost:5001|${REGISTRY}|" "$WORK/k8s/overlays/${ENVIRONMENT}/kustomization.yaml"

kubectl apply -k "$WORK/k8s/overlays/${ENVIRONMENT}"
for d in backend worker frontend; do
  kubectl -n "$NS" rollout status "deploy/$d" --timeout=300s
done
echo "== ${NS} deploye en version ${TAG}"
