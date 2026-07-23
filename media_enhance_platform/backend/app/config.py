from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CLARITY_",
        extra="ignore",
    )

    app_name: str = "Clarity AI"
    environment: str = "local"
    database_url: str = "sqlite+aiosqlite:///./clarity.db"
    jwt_secret: str = "local-development-secret-change-me"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    refresh_cookie_secure: bool = False
    admin_email: str | None = None
    admin_password: str | None = None
    agent_token: str = "local-worker-token-change-me"

    storage_backend: str = "local"
    local_storage_path: str = "./data"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "clarity"
    s3_secret_key: str = "clarity-local-change-me"
    s3_bucket: str = "clarity-media"
    s3_region: str = "us-east-1"

    max_image_bytes: int = 100 * 1024 * 1024
    max_video_bytes: int = 2 * 1024 * 1024 * 1024
    max_video_seconds: int = 30 * 60
    worker_online_seconds: int = 60
    worker_lease_seconds: int = 120
    welcome_points: int = 100
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8095"])

    @model_validator(mode="after")
    def validate_local_defaults(self) -> "Settings":
        if self.environment != "local":
            forbidden = {
                "local-development-secret-change-me",
                "local-worker-token-change-me",
                "clarity-local-change-me",
            }
            if (
                self.jwt_secret in forbidden
                or self.agent_token in forbidden
                or self.s3_secret_key in forbidden
            ):
                raise ValueError("non-local environments require explicit secrets")
        if bool(self.admin_email) != bool(self.admin_password):
            raise ValueError("admin email and password must be configured together")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
