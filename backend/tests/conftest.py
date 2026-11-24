import os
import secrets

# valeur aleatoire a chaque session de test : rien de "secret" n'est ecrit dans le depot
os.environ.setdefault("JWT_SECRET", secrets.token_hex(32))
os.environ.setdefault("ADMIN_PASSWORD", "")

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import main as app_main  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import get_queue, get_redis, get_storage  # noqa: E402


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put(self, bucket, key, data, content_type):
        self.objects[(bucket, key)] = (data, content_type)

    def get(self, bucket, key):
        return self.objects[(bucket, key)]


class FakeQueue:
    def __init__(self):
        self.jobs = []

    def enqueue(self, task, *args, **kwargs):
        self.jobs.append((task, args))


@pytest.fixture()
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    storage, queue = FakeStorage(), FakeQueue()
    redis = fakeredis.FakeRedis()

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = app_main.app
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_queue] = lambda: queue
    app.dependency_overrides[get_redis] = lambda: redis
    app_main.get_engine = lambda: engine
    yield {"client": TestClient(app), "Session": Session, "storage": storage, "queue": queue, "redis": redis}
    app.dependency_overrides.clear()


def make_user(env, email, role="user", password="MotDePasse-Solide-1", name="Test"):
    with env["Session"]() as db:
        db.add(User(email=email, full_name=name, role=role, password_hash=hash_password(password)))
        db.commit()


def auth_headers(env, email, password="MotDePasse-Solide-1"):
    r = env["client"].post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
