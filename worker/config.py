import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "helpdesk")
    db_user: str = os.getenv("DB_USER", "helpdesk")
    db_password: str = os.getenv("DB_PASSWORD", "")
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "")
    s3_endpoint: str = os.getenv("S3_ENDPOINT", "http://localhost:9000")
    s3_access_key: str = os.getenv("S3_ACCESS_KEY", "")
    s3_secret_key: str = os.getenv("S3_SECRET_KEY", "")
    s3_region: str = os.getenv("S3_REGION", "eu-west-3")
    file_encryption_key: str = os.getenv("FILE_ENCRYPTION_KEY", "")
    s3_bucket_exports: str = os.getenv("S3_BUCKET_EXPORTS", "exports")
    smtp_host: str = os.getenv("SMTP_HOST", "localhost")
    smtp_port: int = int(os.getenv("SMTP_PORT", "1025"))
    mail_from: str = os.getenv("MAIL_FROM", "helpdesk@helpdesk.local")


settings = Settings()
