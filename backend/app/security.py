"""Hachage des mots de passe (argon2id), JWT, controle de role."""
import threading
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .logging_conf import security_event
from .models import User

_ph = PasswordHasher()
# argon2id consomme 64 Mio par calcul : sans borne, N connexions simultanees = N x 64 Mio et le pod est OOMKilled
# (incident constate en test de charge, voir rapport). On limite donc les calculs de hash en parallele.
_hash_slots = threading.BoundedSemaphore(get_settings().hash_concurrency)
_bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"


def hash_password(pw: str) -> str:
    with _hash_slots:
        return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        with _hash_slots:
            return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False


def create_token(user: User) -> str:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(minutes=s.jwt_expire_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, s.jwt_secret, algorithm=ALGO)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise")
    try:
        data = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=[ALGO])
    except jwt.PyJWTError:
        security_event("invalid_token")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide ou expiré") from None
    user = db.get(User, int(data["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Utilisateur inconnu")
    return user


def require_staff(user: User = Depends(current_user)) -> User:
    if user.role not in ("agent", "admin"):
        security_event("access_denied", user_id=user.id, required="agent")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reserve aux agents")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        security_event("access_denied", user_id=user.id, required="admin")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reserve aux administrateurs")
    return user
