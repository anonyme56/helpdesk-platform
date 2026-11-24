#!/usr/bin/env python3
"""Génère le tableau de bord Grafana (JSON) : python monitoring/build_dashboard.py > monitoring/helpdesk-dashboard.json

Écrit en Python plutôt qu'à la main : le JSON exporté par Grafana fait 2 000 lignes illisibles en revue de code.
"""
import json
import sys

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
NS = 'namespace="$namespace"'
_id = 0


def _next():
    global _id
    _id += 1
    return _id


def stat(title, expr, x, y, w=4, h=4, unit="percentunit", thresholds=None, decimals=None, desc=""):
    steps = thresholds or [{"color": "green", "value": None}]
    fc = {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []}
    if decimals is not None:
        fc["defaults"]["decimals"] = decimals
    return {"id": _next(), "type": "stat", "title": title, "description": desc, "datasource": PROM,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [{"expr": expr, "refId": "A", "datasource": PROM}],
            "fieldConfig": fc,
            "options": {"colorMode": "value", "graphMode": "area", "reduceOptions": {"calcs": ["lastNotNull"]}}}


def ts(title, targets, x, y, w=12, h=8, unit="short", desc="", stack=False):
    fc = {"defaults": {"unit": unit, "custom": {"fillOpacity": 15, "lineWidth": 2,
                                                  "stacking": {"mode": "normal" if stack else "none"}}},
          "overrides": []}
    return {"id": _next(), "type": "timeseries", "title": title, "description": desc, "datasource": PROM,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [{"expr": e, "legendFormat": legend, "refId": chr(65 + i), "datasource": PROM}
                        for i, (e, legend) in enumerate(targets)],
            "fieldConfig": fc, "options": {"legend": {"displayMode": "list", "placement": "bottom"},
                                           "tooltip": {"mode": "multi"}}}


def logs(title, expr, x, y, w=12, h=9):
    return {"id": _next(), "type": "logs", "title": title, "datasource": LOKI,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [{"expr": expr, "refId": "A", "datasource": LOKI}],
            "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True}}


def row(title, y):
    return {"id": _next(), "type": "row", "title": title, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}}


API = f'{NS},route=~"/api.*"'
panels = [
    row("Objectifs de service (SLI / SLO)", 0),
    stat("Disponibilité API (1 h)", f'helpdesk:availability:ratio_rate1h{{{NS}}}', 0, 1, 5, 5, decimals=3,
         thresholds=[{"color": "red", "value": None}, {"color": "orange", "value": 0.99}, {"color": "green", "value": 0.995}],
         desc="SLI : part des requêtes /api qui ne finissent pas en 5xx. SLO = 99,5 %."),
    stat("Latence p95 API (5 min)", f'helpdesk:latency_p95_seconds:5m{{{NS}}}', 5, 1, 5, 5, unit="s", decimals=3,
         thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 0.25}, {"color": "red", "value": 0.5}],
         desc="Alerte au-dessus de 500 ms pendant 5 min."),
    stat("Requêtes < 250 ms (5 min)", f'helpdesk:latency_under_250ms:ratio_rate5m{{{NS}}}', 10, 1, 5, 5, decimals=3,
         thresholds=[{"color": "red", "value": None}, {"color": "orange", "value": 0.9}, {"color": "green", "value": 0.95}],
         desc="SLI latence. SLO = 95 % des requêtes servies en moins de 250 ms."),
    stat("Pods backend prêts", f'kube_deployment_status_replicas_available{{{NS},deployment="backend"}}', 15, 1, 4, 5,
         unit="none", thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}]),
    stat("Tâches en attente", f'max(worker_queue_length{{{NS}}})', 19, 1, 5, 5, unit="none",
         thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 20}, {"color": "red", "value": 50}]),

    row("Trafic et latence de l'API", 6),
    ts("Requêtes par seconde (par code HTTP)",
       [(f'sum by (status) (rate(http_requests_total{{{API}}}[1m]))', "{{status}}")], 0, 7, unit="reqps", stack=True),
    ts("Latence p50 / p95 / p99",
       [(f'histogram_quantile(0.5, sum by (le) (rate(http_request_duration_seconds_bucket{{{API}}}[2m])))', "p50"),
        (f'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{API}}}[2m])))', "p95"),
        (f'histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{{{API}}}[2m])))', "p99")],
       12, 7, unit="s"),

    row("Ressources et autoscaling", 15),
    ts("Réplicas backend (HPA)",
       [(f'kube_horizontalpodautoscaler_status_current_replicas{{{NS},horizontalpodautoscaler="backend"}}', "actuels"),
        (f'kube_horizontalpodautoscaler_status_desired_replicas{{{NS},horizontalpodautoscaler="backend"}}', "souhaités"),
        (f'kube_horizontalpodautoscaler_spec_max_replicas{{{NS},horizontalpodautoscaler="backend"}}', "maximum")],
       0, 16, 8),
    ts("CPU des pods backend (cœurs)",
       [(f'sum by (pod) (rate(container_cpu_usage_seconds_total{{{NS},container="backend"}}[1m]))', "{{pod}}")],
       8, 16, 8, unit="none"),
    ts("Mémoire des pods backend (Mo)",
       [(f'sum by (pod) (container_memory_working_set_bytes{{{NS},container="backend"}}) / 1024 / 1024', "{{pod}}"),
        (f'max(kube_pod_container_resource_limits{{{NS},container="backend",resource="memory"}}) / 1024 / 1024', "limite")],
       16, 16, 8, unit="none"),

    row("Traitements asynchrones et métier", 24),
    ts("Tâches du worker (par minute)",
       [(f'sum by (task, result) (increase(worker_jobs_total{{{NS}}}[1m]))', "{{task}} / {{result}}")], 0, 25, 8, unit="none"),
    ts("Tickets créés et échecs de connexion (par minute)",
       [(f'sum(increase(helpdesk_tickets_created_total{{{NS}}}[1m]))', "tickets créés"),
        (f'sum(increase(helpdesk_login_failures_total{{{NS}}}[1m]))', "échecs de connexion")], 8, 25, 8, unit="none"),
    ts("Redémarrages de conteneurs (1 h)",
       [(f'sum by (pod) (increase(kube_pod_container_status_restarts_total{{{NS}}}[1h]))', "{{pod}}")], 16, 25, 8, unit="none"),

    row("Journaux", 33),
    logs("Événements de sécurité (connexions, refus d'accès)",
         '{namespace="$namespace"} |= "\\"logger\\": \\"security\\""', 0, 34),
    logs("Erreurs applicatives (WARNING / ERROR)",
         '{namespace="$namespace"} |~ "\\"level\\": \\"(WARNING|ERROR)\\""', 12, 34),
]

dashboard = {
    "uid": "helpdesk-overview", "title": "Helpdesk - exploitation", "schemaVersion": 39, "version": 1,
    "tags": ["helpdesk"], "timezone": "browser", "refresh": "10s", "time": {"from": "now-30m", "to": "now"},
    "templating": {"list": [{
        "name": "namespace", "label": "Environnement", "type": "query", "datasource": PROM,
        "query": {"query": 'label_values(kube_deployment_status_replicas{namespace=~"helpdesk-.*"}, namespace)',
                  "refId": "ns"},
        "refresh": 2, "current": {"text": "helpdesk-prod", "value": "helpdesk-prod"}, "includeAll": False}]},
    "panels": panels,
}
sys.stdout.reconfigure(encoding="utf-8")
print(json.dumps(dashboard, ensure_ascii=False, indent=1))
