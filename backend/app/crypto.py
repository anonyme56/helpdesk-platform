"""Chiffrement applicatif des objets avant envoi au stockage (Fernet = AES-128-CBC + HMAC-SHA256).

La cle vient d'un Secret Kubernetes. Meme si le stockage objet etait lu directement
(disque, sauvegarde du volume), les fichiers y sont illisibles sans cette cle.
"""
from cryptography.fernet import Fernet, InvalidToken


class ObjectCipher:
    def __init__(self, key: str):
        if not key:
            raise RuntimeError("FILE_ENCRYPTION_KEY manquante")
        self._f = Fernet(key.encode())

    def encrypt(self, data: bytes) -> bytes:
        return self._f.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        try:
            return self._f.decrypt(token)
        except InvalidToken as exc:
            raise ValueError("objet illisible : cle incorrecte ou donnee alteree") from exc
