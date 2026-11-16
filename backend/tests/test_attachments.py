from .conftest import auth_headers, make_user


def _setup(env):
    make_user(env, "u@x.fr")
    h = auth_headers(env, "u@x.fr")
    t = env["client"].post("/api/tickets", json={"title": "Capture d'écran"}, headers=h).json()
    return h, t["id"]


def test_upload_and_download(env):
    h, tid = _setup(env)
    r = env["client"].post(f"/api/tickets/{tid}/attachments", headers=h,
                           files={"file": ("erreur.txt", b"stacktrace...", "text/plain")})
    assert r.status_code == 201
    att = r.json()
    assert att["size"] == 13
    assert len(env["storage"].objects) == 1
    dl = env["client"].get(f"/api/attachments/{att['id']}", headers=h)
    assert dl.status_code == 200 and dl.content == b"stacktrace..."


def test_executable_refused(env):
    h, tid = _setup(env)
    r = env["client"].post(f"/api/tickets/{tid}/attachments", headers=h,
                           files={"file": ("virus.exe", b"MZ...", "application/x-msdownload")})
    assert r.status_code == 415


def test_too_big_refused(env):
    h, tid = _setup(env)
    big = b"a" * (5 * 1024 * 1024 + 10)
    r = env["client"].post(f"/api/tickets/{tid}/attachments", headers=h,
                           files={"file": ("gros.txt", big, "text/plain")})
    assert r.status_code == 413


def test_filename_is_sanitized(env):
    h, tid = _setup(env)
    r = env["client"].post(f"/api/tickets/{tid}/attachments", headers=h,
                           files={"file": ("../../etc/passwd", b"x", "text/plain")})
    assert r.status_code == 201
    assert "/" not in r.json()["filename"]


def test_other_user_cannot_download(env):
    h, tid = _setup(env)
    att = env["client"].post(f"/api/tickets/{tid}/attachments", headers=h,
                             files={"file": ("a.txt", b"x", "text/plain")}).json()
    make_user(env, "intrus@x.fr")
    r = env["client"].get(f"/api/attachments/{att['id']}", headers=auth_headers(env, "intrus@x.fr"))
    assert r.status_code == 404
