"""Configuration lue uniquement dans l'environnement (aucun secret dans le code)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    env: str = "dev"
    app_version: str = "dev"
    log_level: str = "INFO"

    # base de donnees (le mot de passe arrive a part, depuis un Secret)
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "helpdesk"
    db_user: str = "helpdesk"
    db_password: str = ""
    database_url: str | None = None  # surcharge utilisee par les tests

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "eu-west-3"
    s3_bucket_attachments: str = "attachments"
    s3_bucket_exports: str = "exports"
    s3_bucket_backups: str = "backups"

    jwt_secret: str = ""
    file_encryption_key: str = ""
    jwt_expire_minutes: int = 60

    admin_email: str = "admin@helpdesk.example.com"
    admin_password: str = ""

    max_upload_mb: int = 5
    hash_concurrency: int = 2
    login_max_attempts: int = 5
    login_window_seconds: int = 300

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
