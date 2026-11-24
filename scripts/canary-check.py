#!/usr/bin/env python3
"""Compte les versions qui répondent derrière l'Ingress (en-tête X-App-Version) : vérifie la répartition du canary."""
import collections
import ssl
import sys
import urllib.error
import urllib.request

url = sys.argv[1] if len(sys.argv) > 1 else "https://helpdesk.localtest.me:8443/api/auth/me"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
ctx = ssl._create_unverified_context()
seen = collections.Counter()
for _ in range(n):
    try:
        urllib.request.urlopen(url, context=ctx)
    except urllib.error.HTTPError as e:  # 401 attendu (pas de jeton) : seul l'en-tete nous interesse
        seen[e.headers.get("X-App-Version", "?")] += 1
for version, count in seen.most_common():
    print(f"{version:<16} {count:>4} requetes  ({100 * count / n:.0f} %)")
