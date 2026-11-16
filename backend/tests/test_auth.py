from .conftest import auth_headers, make_user


def test_register_and_login(env):
    c = env["client"]
    r = c.post("/api/auth/register", json={"email": "a@x.fr", "full_name": "Alice", "password": "MotDePasse-Solide-1"})
    assert r.status_code == 201
    assert r.json()["role"] == "user"
    h = auth_headers(env, "a@x.fr")
    assert c.get("/api/auth/me", headers=h).json()["email"] == "a@x.fr"


def test_password_too_short_rejected(env):
    r = env["client"].post("/api/auth/register", json={"email": "a@x.fr", "full_name": "Alice", "password": "court"})
    assert r.status_code == 422


def test_duplicate_email(env):
    body = {"email": "a@x.fr", "full_name": "Alice", "password": "MotDePasse-Solide-1"}
    env["client"].post("/api/auth/register", json=body)
    assert env["client"].post("/api/auth/register", json=body).status_code == 409


def test_wrong_password_then_lockout(env):
    make_user(env, "b@x.fr")
    c = env["client"]
    for _ in range(5):
        assert c.post("/api/auth/login", json={"email": "b@x.fr", "password": "mauvais-mot-de-passe"}).status_code == 401
    # le 6e essai est bloqué, même avec le bon mot de passe
    r = c.post("/api/auth/login", json={"email": "b@x.fr", "password": "MotDePasse-Solide-1"})
    assert r.status_code == 429


def test_no_token_is_401(env):
    assert env["client"].get("/api/tickets").status_code == 401


def test_forged_token_is_401(env):
    h = {"Authorization": "Bearer abc.def.ghi"}
    assert env["client"].get("/api/tickets", headers=h).status_code == 401


def test_only_admin_changes_roles(env):
    make_user(env, "u@x.fr")
    make_user(env, "root@x.fr", role="admin")
    c = env["client"]
    hu, ha = auth_headers(env, "u@x.fr"), auth_headers(env, "root@x.fr")
    assert c.patch("/api/users/1/role", json={"role": "admin"}, headers=hu).status_code == 403
    assert c.patch("/api/users/1/role", json={"role": "agent"}, headers=ha).json()["role"] == "agent"


def test_password_hashing_is_bounded():
    """Garde-fou mémoire : au plus HASH_CONCURRENCY calculs argon2 simultanés (voir incident OOM)."""
    from app.security import _hash_slots
    assert _hash_slots._value == 2
