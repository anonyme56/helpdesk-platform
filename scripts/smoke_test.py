#!/usr/bin/env python3
"""Test de fumée de bout en bout (stdlib uniquement) : sert pour compose, Kubernetes et la CI.

    python scripts/smoke_test.py --base-url http://localhost:8081 --admin-password XXX
    python scripts/smoke_test.py --base-url https://helpdesk-dev.localtest.me:8443 --insecure ...
"""
import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid


class Client:
    def __init__(self, base, insecure):
        self.base = base.rstrip("/")
        self.ctx = ssl._create_unverified_context() if insecure else None
        self.token = None

    def call(self, method, path, body=None, raw=None, headers=None, expect=None):
        h = dict(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=30) as r:
                status, payload, rh = r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            status, payload, rh = e.code, e.read(), e.headers
        if expect and status != expect:
            raise AssertionError(f"{method} {path} -> {status} (attendu {expect}) : {payload[:200]!r}")
        return status, payload, rh

    def json(self, *a, **k):
        _, payload, _ = self.call(*a, **k)
        return json.loads(payload)


def multipart(filename, content, ctype):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def step(msg):
    print(f"  - {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--admin-email", default="admin@helpdesk.example.com")
    ap.add_argument("--admin-password", required=True)
    ap.add_argument("--mailpit-url", help="si fourni, vérifie aussi la réception du mail")
    ap.add_argument("--insecure", action="store_true", help="certificat auto-signé")
    a = ap.parse_args()

    c = Client(a.base_url, a.insecure)
    print(f"Smoke test sur {a.base_url}")

    st, body, hdr = c.call("GET", "/api/auth/me")
    assert st == 401, "l'API doit refuser un appel sans jeton"
    step(f"API protégée (401 sans jeton), version servie : {hdr.get('X-App-Version')}")

    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    pwd = "Smoke-Test-" + uuid.uuid4().hex[:10]
    c.call("POST", "/api/auth/register", {"email": email, "full_name": "Utilisateur Smoke", "password": pwd}, expect=201)
    c.token = c.json("POST", "/api/auth/login", {"email": email, "password": pwd})["access_token"]
    step(f"inscription + connexion OK ({email})")

    t = c.json("POST", "/api/tickets", {"title": "Imprimante du 2e étage en panne", "description": "Bourrage papier",
                                         "priority": "high"}, expect=201)
    step(f"ticket #{t['id']} créé (statut {t['status']})")

    c.call("POST", f"/api/tickets/{t['id']}/comments", {"body": "Toujours en panne ce matin"}, expect=201)
    body, h = multipart("erreur.txt", b"code erreur E-42\n", "text/plain")
    att = c.json("POST", f"/api/tickets/{t['id']}/attachments", raw=body, headers=h, expect=201)
    _, dl, _ = c.call("GET", f"/api/attachments/{att['id']}", expect=200)
    assert dl == b"code erreur E-42\n", "le fichier relu doit être identique"
    step(f"pièce jointe envoyée puis relue depuis le stockage objet ({att['size']} octets)")

    st, _, _ = c.call("GET", "/api/exports")
    assert st in (404, 405), "route inconnue attendue"
    st, _, _ = c.call("POST", "/api/exports")
    assert st == 403, "un utilisateur simple ne peut pas exporter"
    step("export refusé à un utilisateur simple (403)")

    c.token = c.json("POST", "/api/auth/login", {"email": a.admin_email, "password": a.admin_password})["access_token"]
    admin = c.json("GET", "/api/auth/me")
    c.call("PATCH", f"/api/tickets/{t['id']}", {"status": "in_progress", "assignee_id": admin["id"]}, expect=200)
    step("admin : ticket pris en charge et assigné")

    job = c.json("POST", "/api/exports", expect=202)
    for _ in range(30):
        time.sleep(1)
        job = c.json("GET", f"/api/exports/{job['id']}")
        if job["status"] in ("done", "failed"):
            break
    assert job["status"] == "done", f"export non terminé : {job}"
    _, csv_data, _ = c.call("GET", f"/api/exports/{job['id']}/download", expect=200)
    assert b"Imprimante du 2e" in csv_data
    step(f"export CSV produit par le worker et relu ({len(csv_data.splitlines())} lignes)")

    if a.mailpit_url:
        m = Client(a.mailpit_url, a.insecure)
        for _ in range(20):
            msgs = m.json("GET", "/api/v1/messages")["messages"]
            if any(email in json.dumps(x["To"]) for x in msgs):
                step("e-mail de notification reçu (envoyé par le worker via SMTP)")
                break
            time.sleep(1)
        else:
            raise AssertionError("aucun mail reçu")

    print("SMOKE TEST OK")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"ECHEC : {e}")
        sys.exit(1)
