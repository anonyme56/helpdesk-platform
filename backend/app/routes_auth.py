from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import metrics
from .config import get_settings
from .db import get_db
from .logging_conf import security_event
from .models import User
from .schemas import LoginIn, RegisterIn, RoleIn, TokenOut, UserOut
from .security import create_token, current_user, hash_password, require_admin, require_staff, verify_password
from .services import get_redis

router = APIRouter(prefix="/api", tags=["auth"])


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _attempts_key(email: str) -> str:
    return f"login_attempts:{email.lower()}"


@router.post("/auth/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet e-mail est déjà utilisé")
    user = User(email=data.email.lower(), full_name=data.full_name, password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    security_event("user_registered", user_id=user.id, ip=_client_ip(request))
    return user


@router.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db), r=Depends(get_redis)):
    s = get_settings()
    key = _attempts_key(data.email)
    # protection brute force : N échecs par fenêtre, comptés par e-mail dans Redis
    attempts = int(r.get(key) or 0)
    if attempts >= s.login_max_attempts:
        security_event("login_blocked", email=data.email.lower(), ip=_client_ip(request))
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Trop de tentatives, réessayez plus tard")

    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, s.login_window_seconds)
        pipe.execute()
        metrics.LOGIN_FAILURES.inc()
        security_event("login_failed", email=data.email.lower(), ip=_client_ip(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides")

    r.delete(key)
    security_event("login_success", user_id=user.id, ip=_client_ip(request))
    return TokenOut(access_token=create_token(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_staff)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.patch("/users/{user_id}/role", response_model=UserOut)
def set_role(user_id: int, data: RoleIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Utilisateur introuvable")
    user.role = data.role
    db.commit()
    security_event("role_changed", target=user_id, role=data.role, by=admin.id)
    return user
