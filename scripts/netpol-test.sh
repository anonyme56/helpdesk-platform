#!/usr/bin/env bash
# Verifie que les NetworkPolicies sont reellement appliquees (et pas juste declarees).
NS="${1:-helpdesk-prod}"
probe() { # probe <label> <pod|deploy> <host> <port>
  if kubectl -n "$NS" exec "$2" -c "${5:-backend}" -- python -c "import socket,sys; s=socket.socket(); s.settimeout(3); s.connect(('$3',$4))" 2>/dev/null; then
    echo "OUVERT  : $1 ($3:$4)"
  else
    echo "BLOQUE  : $1 ($3:$4)"
  fi
}
echo "--- depuis un pod backend (flux attendus : postgres, redis, s3)"
probe "backend -> postgres"  deploy/backend postgres 5432
probe "backend -> redis"     deploy/backend redis 6379
probe "backend -> s3"        deploy/backend s3 8333
probe "backend -> mailpit (interdit)" deploy/backend mailpit 1025
probe "backend -> internet (interdit)" deploy/backend 1.1.1.1 443
echo "--- depuis un pod worker (flux attendus : postgres, redis, s3, mailpit)"
probe "worker -> mailpit"    deploy/worker mailpit 1025 worker
probe "worker -> internet (interdit)" deploy/worker 1.1.1.1 443 worker
echo "--- depuis un pod quelconque du namespace (sans label applicatif)"
kubectl -n "$NS" run nettest --image=busybox:1.37 --restart=Never --rm -i --quiet --command -- sh -c \
  'nc -z -w 3 postgres 5432 && echo "OUVERT  : pod anonyme -> postgres" || echo "BLOQUE  : pod anonyme -> postgres (5432)"' 2>&1 | grep -E "OUVERT|BLOQUE"
