#!/usr/bin/env bash
# Regles d'alerte et SLO (communes a tous les environnements).
set -euo pipefail
kubectl apply -f "$(dirname "$0")/../monitoring/helpdesk-rules.yaml"
