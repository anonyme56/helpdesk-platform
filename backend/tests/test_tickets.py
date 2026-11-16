from .conftest import auth_headers, make_user


def _ticket(env, headers, title="Imprimante HS"):
    r = env["client"].post("/api/tickets", json={"title": title, "description": "ne démarre plus"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_ticket_enqueues_notification(env):
    make_user(env, "u@x.fr")
    t = _ticket(env, auth_headers(env, "u@x.fr"))
    assert t["status"] == "open"
    assert ("tasks.notify_ticket_created", (t["id"],)) in env["queue"].jobs


def test_user_cannot_see_other_users_tickets(env):
    make_user(env, "u1@x.fr")
    make_user(env, "u2@x.fr")
    h1, h2 = auth_headers(env, "u1@x.fr"), auth_headers(env, "u2@x.fr")
    t = _ticket(env, h1)
    assert env["client"].get(f"/api/tickets/{t['id']}", headers=h2).status_code == 404
    assert env["client"].get("/api/tickets", headers=h2).json() == []
    assert len(env["client"].get("/api/tickets", headers=h1).json()) == 1


def test_agent_sees_everything_and_assigns(env):
    make_user(env, "u@x.fr")
    make_user(env, "agent@x.fr", role="agent")
    hu, ha = auth_headers(env, "u@x.fr"), auth_headers(env, "agent@x.fr")
    t = _ticket(env, hu)
    assert len(env["client"].get("/api/tickets", headers=ha).json()) == 1
    r = env["client"].patch(f"/api/tickets/{t['id']}", json={"assignee_id": 2, "status": "in_progress"}, headers=ha)
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    assert ("tasks.notify_ticket_assigned", (t["id"],)) in env["queue"].jobs


def test_simple_user_cannot_patch(env):
    make_user(env, "u@x.fr")
    h = auth_headers(env, "u@x.fr")
    t = _ticket(env, h)
    assert env["client"].patch(f"/api/tickets/{t['id']}", json={"status": "closed"}, headers=h).status_code == 403


def test_cannot_assign_to_simple_user(env):
    make_user(env, "u@x.fr")
    make_user(env, "agent@x.fr", role="agent")
    t = _ticket(env, auth_headers(env, "u@x.fr"))
    r = env["client"].patch(f"/api/tickets/{t['id']}", json={"assignee_id": 1}, headers=auth_headers(env, "agent@x.fr"))
    assert r.status_code == 422


def test_comment_flow(env):
    make_user(env, "u@x.fr")
    h = auth_headers(env, "u@x.fr")
    t = _ticket(env, h)
    assert env["client"].post(f"/api/tickets/{t['id']}/comments", json={"body": "Toujours HS"}, headers=h).status_code == 201
    detail = env["client"].get(f"/api/tickets/{t['id']}", headers=h).json()
    assert detail["comments"][0]["body"] == "Toujours HS"


def test_invalid_title_rejected(env):
    make_user(env, "u@x.fr")
    r = env["client"].post("/api/tickets", json={"title": "x"}, headers=auth_headers(env, "u@x.fr"))
    assert r.status_code == 422
