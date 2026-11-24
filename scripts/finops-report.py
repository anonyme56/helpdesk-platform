#!/usr/bin/env python3
"""Rapport FinOps d'un namespace : requêtes demandées vs consommation mesurée (Prometheus) et coût équivalent cloud.

    python scripts/finops-report.py --namespace helpdesk-prod [--window 3h]

Modèle de coût (hypothèses explicites, modifiables) : on valorise ce que le namespace RÉSERVE (les requests),
comme le ferait une facturation à la ressource demandée (GKE Autopilot, Fargate...). Prix publics indicatifs :
0,045 $ par vCPU-heure et 0,005 $ par Gio-heure ; 730 h par mois.
"""
import argparse
import json
import ssl
import urllib.parse
import urllib.request

CPU_PRICE, MEM_PRICE, HOURS = 0.045, 0.005, 730


def q(base, expr):
    url = f"{base}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    with urllib.request.urlopen(url, context=ssl._create_unverified_context(), timeout=60) as r:
        return {tuple(sorted(x["metric"].items())): float(x["value"][1]) for x in json.load(r)["data"]["result"]}


def by_container(res):
    return {dict(k).get("container", "?"): v for k, v in res.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--window", default="3h")
    ap.add_argument("--prometheus", default="https://prometheus.localtest.me:8443")
    a = ap.parse_args()
    ns, w = a.namespace, a.window
    sel = f'namespace="{ns}",container!="",container!="POD"'

    req_cpu = by_container(q(a.prometheus, f'max by (container) (kube_pod_container_resource_requests{{namespace="{ns}",resource="cpu"}})'))
    req_mem = by_container(q(a.prometheus, f'max by (container) (kube_pod_container_resource_requests{{namespace="{ns}",resource="memory"}})'))
    use_mem = by_container(q(a.prometheus, f"max by (container) (max_over_time(container_memory_working_set_bytes{{{sel}}}[{w}]))"))
    use_cpu = by_container(q(a.prometheus, f"max by (container) (quantile_over_time(0.95, rate(container_cpu_usage_seconds_total{{{sel}}}[5m])[{w}:1m]))"))
    pods = by_container(q(a.prometheus, f'count by (container) (kube_pod_container_info{{namespace="{ns}"}})'))

    print(f"Namespace {ns} - fenêtre de mesure {w}")
    print(f"{'conteneur':<14}{'pods':>5}{'req CPU':>9}{'p95 CPU':>9}{'req Mém':>10}{'max Mém':>10}")
    tot_cpu = tot_mem = 0.0
    for c in sorted(req_cpu):
        n = pods.get(c, 1)
        tot_cpu += req_cpu[c] * n
        tot_mem += req_mem.get(c, 0) * n
        print(f"{c:<14}{n:>5.0f}{req_cpu[c] * 1000:>8.0f}m{use_cpu.get(c, 0) * 1000:>8.0f}m"
              f"{req_mem.get(c, 0) / 2**20:>8.0f}Mi{use_mem.get(c, 0) / 2**20:>8.0f}Mi")
    monthly = (tot_cpu * CPU_PRICE + tot_mem / 2**30 * MEM_PRICE) * HOURS
    print(f"\nRéservé : {tot_cpu:.2f} vCPU, {tot_mem / 2**30:.2f} Gio  ->  coût équivalent {monthly:.1f} $/mois "
          f"(24 h/24, 7 j/7)")


if __name__ == "__main__":
    main()
