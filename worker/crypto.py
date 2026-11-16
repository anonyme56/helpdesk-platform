"""Même chiffrement que le backend (copie volontaire : le worker est une image indépendante)."""
from cryptography.fernet import Fernet


class ObjectCipher:
    def __init__(self, key: str):
        if not key:
            raise RuntimeError("FILE_ENCRYPTION_KEY manquante")
        self._f = Fernet(key.encode())

    def encrypt(self, data: bytes) -> bytes:
        return self._f.encrypt(data)
