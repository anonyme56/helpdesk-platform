#!/usr/bin/env python3
"""Générateur de charge simple (stdlib) : sert au test d'autoscaling, aux mises à jour sans coupure et aux SLO.

    python scripts/loadtest.py --base-url https://helpdesk.localtest.me:8443 --insecure \
        --email alice.martin@example.com --password XXX --duration 120 --concurrency 12
Un résumé par tranche de 5 s est affiché (débit, erreurs, p95, versions vues).
"""
import argparse
import collections
import json
import ssl
import statistics
import threading
import time
import urllib.error
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--mode", choices=["cpu", "light"], default="cpu",
                    help="cpu : connexions (argon2, coûteux) ; light : lecture de la liste de tickets")
    ap.add_argument("--insecure", action="store_true")
    a = ap.parse_args()

    ctx = ssl._create_unverified_context() if a.insecure else None
    base = a.base_url.rstrip("/")

    def call(method, path, body=None, token=None):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(base + path, json.dumps(body).encode() if body else None, h, method=method)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
                data, code, ver = r.read(), r.status, r.headers.get("X-App-Version", "?")
        except urllib.error.HTTPError as e:
            data, code, ver = e.read(), e.code, e.headers.get("X-App-Version", "?")
        except Exception:
            data, code, ver = b"", 0, "?"
        return code, ver, time.perf_counter() - t0, data

    code, _, _, data = call("POST", "/api/auth/login", {"email": a.email, "password": a.password})
    token = json.loads(data)["access_token"] if code == 200 else None
    assert token, f"connexion impossible ({code})"

    lock = threading.Lock()
    samples = []  # (t, code, version, latence)
    stop = time.time() + a.duration

    def worker():
        while time.time() < stop:
            if a.mode == "cpu":
                c, v, d, _ = call("POST", "/api/auth/login", {"email": a.email, "password": a.password})
            else:
                c, v, d, _ = call("GET", "/api/tickets", token=token)
            with lock:
                samples.append((time.time(), c, v, d))

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(a.concurrency)]
    t_start = time.time()
    for t in threads:
        t.start()

    last = t_start
    print(f"{'t(s)':>5} {'req/s':>7} {'erreurs':>8} {'p95(ms)':>8}  versions")
    while time.time() < stop:
        time.sleep(5)
        now = time.time()
        with lock:
            win = [s for s in samples if last <= s[0] < now]
        if win:
            lat = sorted(s[3] for s in win)
            p95 = lat[int(len(lat) * 0.95) - 1] * 1000 if len(lat) > 1 else lat[0] * 1000
            errs = sum(1 for s in win if s[1] == 0 or s[1] >= 500)
            vers = collections.Counter(s[2] for s in win)
            print(f"{now - t_start:5.0f} {len(win) / (now - last):7.1f} {errs:8d} {p95:8.0f}  {dict(vers)}", flush=True)
        last = now
    for t in threads:
        t.join(timeout=20)

    total = len(samples)
    errs = sum(1 for s in samples if s[1] == 0 or s[1] >= 500)
    lat = [s[3] for s in samples]
    print(f"TOTAL {total} requêtes, {errs} erreurs ({100 * errs / max(total, 1):.2f} %), "
          f"latence médiane {statistics.median(lat) * 1000:.0f} ms")


if __name__ == "__main__":
    main()
