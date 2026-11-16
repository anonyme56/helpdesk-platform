from .conftest import auth_headers, make_user


def test_health(env):
    r = env["client"].get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ready_checks_db(env):
    assert env["client"].get("/ready").status_code == 200


def test_metrics_exposed_and_labelled_by_route_template(env):
    make_user(env, "u@x.fr")
    h = auth_headers(env, "u@x.fr")
    t = env["client"].post("/api/tickets", json={"title": "Métrique"}, headers=h).json()
    env["client"].get(f"/api/tickets/{t['id']}", headers=h)
    body = env["client"].get("/metrics").text
    assert 'http_requests_total{method="GET",route="/api/tickets/{ticket_id}",status="200"}' in body
    assert "helpdesk_tickets_created_total" in body


def test_response_headers(env):
    r = env["client"].get("/health")
    assert r.headers["X-Request-ID"] and r.headers["X-Content-Type-Options"] == "nosniff"


def test_export_requires_staff(env):
    make_user(env, "u@x.fr")
    make_user(env, "agent@x.fr", role="agent")
    assert env["client"].post("/api/exports", headers=auth_headers(env, "u@x.fr")).status_code == 403
    r = env["client"].post("/api/exports", headers=auth_headers(env, "agent@x.fr"))
    assert r.status_code == 202
    assert ("tasks.generate_export", (r.json()["id"],)) in env["queue"].jobs
