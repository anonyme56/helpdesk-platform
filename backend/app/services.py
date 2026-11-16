"""Acces aux services externes : stockage objet (S3) et file de messages (Redis/RQ)."""
import io
from functools import lru_cache

import boto3
import redis
from botocore.client import Config
from botocore.exceptions import ClientError
from rq import Queue, Retry

from .config import get_settings
from .crypto import ObjectCipher


class S3Storage:
    """Stockage objet S3-compatible ; le contenu est chiffre cote application."""

    def __init__(self, client=None, cipher: ObjectCipher | None = None):
        s = get_settings()
        self.client = client or boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            region_name=s.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self.cipher = cipher or ObjectCipher(s.file_encryption_key)

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=bucket, Key=key, Body=io.BytesIO(self.cipher.encrypt(data)),
                               ContentType=content_type)

    def get(self, bucket: str, key: str) -> tuple[bytes, str]:
        obj = self.client.get_object(Bucket=bucket, Key=key)
        return self.cipher.decrypt(obj["Body"].read()), obj.get("ContentType", "application/octet-stream")

    def ping(self) -> bool:
        try:
            self.client.list_buckets()
            return True
        except ClientError:
            return False


@lru_cache
def get_storage() -> S3Storage:
    return S3Storage()


@lru_cache
def get_redis() -> redis.Redis:
    s = get_settings()
    return redis.Redis(host=s.redis_host, port=s.redis_port, password=s.redis_password or None,
                       decode_responses=False, socket_connect_timeout=2, socket_timeout=2)


def get_queue() -> Queue:
    return Queue("default", connection=get_redis())


def enqueue(queue: Queue, task: str, *args) -> None:
    """On enfile par nom ("tasks.xxx") : le back n'a pas besoin du code du worker."""
    queue.enqueue(task, *args, job_timeout=120, result_ttl=3600, failure_ttl=86400,
                  retry=Retry(max=3, interval=[5, 15, 30]))
