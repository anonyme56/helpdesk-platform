#!/usr/bin/env python3
"""Jeu de données de démonstration (utilisateurs, agents, tickets) injecté via l'API."""
import argparse
import json
import ssl
import urllib.error
import urllib.request

TICKETS = [
    ("Impossible de se connecter au VPN", "Erreur 809 depuis ce matin, télétravail bloqué.", "urgent"),
    ("Écran qui clignote sur le poste 214", "Le moniteur s'éteint par intermittence.", "normal"),
    ("Demande d'accès au dossier partagé Compta", "Besoin d'un accès lecture pour la clôture.", "low"),
    ("Imprimante du 2e étage en panne", "Bourrage papier, voyant rouge.", "high"),
    ("Messagerie : boîte pleine", "Quota atteint, plus de réception.", "high"),
    ("Installation de Python 3.12 sur mon poste", "Nécessaire pour le projet data.", "low"),
    ("Mot de passe expiré", "Impossible de le changer depuis l'extranet.", "normal"),
    ("Wi-Fi instable en salle de réunion B", "Coupures toutes les 10 minutes.", "normal"),
]


class C:
    def __init__(self, base, insecure):
        self.base = base.rstrip("/")
        self.ctx = ssl._create_unverified_context() if insecure else None
        self.token = None

    def call(self, method, path, body=None):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base + path, json.dumps(body).encode() if body is not None else None,
                                     h, method=method)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=30) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--admin-email", default="admin@helpdesk.example.com")
    ap.add_argument("--admin-password", required=True)
    ap.add_argument("--demo-password", required=True, help="mot de passe des comptes de démo")
    ap.add_argument("--insecure", action="store_true")
    a = ap.parse_args()

    c = C(a.base_url, a.insecure)
    _, tok = c.call("POST", "/api/auth/login", {"email": a.admin_email, "password": a.admin_password})
    admin_token = tok["access_token"]

    def login(email):
        _, t = c.call("POST", "/api/auth/login", {"email": email, "password": a.demo_password})
        return t["access_token"]

    people = [("alice.martin@example.com", "Alice Martin"), ("karim.benali@example.com", "Karim Benali"),
              ("sophie.durand@example.com", "Sophie Durand")]
    for email, name in people:
        c.call("POST", "/api/auth/register", {"email": email, "full_name": name, "password": a.demo_password})
    c.token = admin_token
    _, users = c.call("GET", "/api/users")
    by_email = {u["email"]: u for u in users}
    c.call("PATCH", f"/api/users/{by_email['sophie.durand@example.com']['id']}/role", {"role": "agent"})

    ids = []
    for i, (title, desc, prio) in enumerate(TICKETS):
        c.token = login(people[i % 2][0])
        _, t = c.call("POST", "/api/tickets", {"title": title, "description": desc, "priority": prio})
        ids.append(t["id"])
    c.token = login("sophie.durand@example.com")
    agent_id = by_email["sophie.durand@example.com"]["id"]
    states = ["in_progress", "in_progress", "resolved", "open", "closed"]
    for tid, st in zip(ids, states):
        c.call("PATCH", f"/api/tickets/{tid}", {"status": st, "assignee_id": agent_id})
    c.call("POST", f"/api/tickets/{ids[0]}/comments", {"body": "Je regarde la configuration du client VPN à distance."})
    print(f"{len(ids)} tickets de démonstration créés")


if __name__ == "__main__":
    main()
