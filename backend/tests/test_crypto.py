import io

import pytest
from cryptography.fernet import Fernet

from app.crypto import ObjectCipher
from app.services import S3Storage


class StubS3Client:
    """Imite juste ce qu'utilise S3Storage ; on garde les octets tels qu'ils seraient stockés."""

    def __init__(self):
        self.stored = {}

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803
        self.stored[(Bucket, Key)] = (Body.read(), ContentType)

    def get_object(self, Bucket, Key):  # noqa: N803
        data, ctype = self.stored[(Bucket, Key)]
        return {"Body": io.BytesIO(data), "ContentType": ctype}


def _cipher():
    return ObjectCipher(Fernet.generate_key().decode())


def test_roundtrip_and_ciphertext_differs_from_plaintext():
    client = StubS3Client()
    st = S3Storage(client=client, cipher=_cipher())
    st.put("attachments", "k", b"contenu confidentiel", "text/plain")
    raw, _ = client.stored[("attachments", "k")]
    assert b"confidentiel" not in raw
    data, ctype = st.get("attachments", "k")
    assert data == b"contenu confidentiel" and ctype == "text/plain"


def test_wrong_key_is_rejected():
    client = StubS3Client()
    S3Storage(client=client, cipher=_cipher()).put("b", "k", b"secret", "text/plain")
    other = S3Storage(client=client, cipher=_cipher())
    with pytest.raises(ValueError):
        other.get("b", "k")


def test_missing_key_refuses_to_start():
    with pytest.raises(RuntimeError):
        ObjectCipher("")
