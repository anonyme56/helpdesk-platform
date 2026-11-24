#!/usr/bin/env bash
# Scan Trivy des 4 images : nombre de vulnerabilites HIGH/CRITICAL corrigeables. Echoue s'il en reste.
# usage: scripts/scan-images.sh <tag> [registre]
set -uo pipefail
TAG="${1:?tag}"; REG="${2:-localhost:5001}"; FAIL=0
printf '%-10s %8s %10s\n' image HIGH CRITICAL
for img in backend worker frontend backup; do
  OUT=$(MSYS_NO_PATHCONV=1 docker run --rm -v //var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache \
    aquasec/trivy:latest image --quiet --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --format json \
    "${REG}/helpdesk/${img}:${TAG}" 2>/dev/null)
  read -r H C <<<"$(printf '%s' "$OUT" | python -c "
import sys, json
d = json.load(sys.stdin)
v = [x for r in d.get('Results', []) for x in (r.get('Vulnerabilities') or [])]
print(sum(1 for x in v if x['Severity']=='HIGH'), sum(1 for x in v if x['Severity']=='CRITICAL'))")"
  printf '%-10s %8s %10s\n' "$img" "$H" "$C"
  [ "$H" != "0" ] || [ "$C" != "0" ] && FAIL=1
done
exit $FAIL
