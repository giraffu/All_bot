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
    test_worker_bridge_enabled: bool = False
    test_worker_bridge_platform_url: str = "http://backend:8000/api"
    test_worker_bridge_worker_id: str = "clarity-allbot-test-bridge"
    test_worker_bridge_poll_seconds: float = 3.0
    test_worker_bridge_idle_seconds: float = 3.0
    test_worker_bridge_error_seconds: float = 5.0
    test_worker_bridge_http_timeout_seconds: float = 120.0
    test_central_url: str | None = None
    test_central_api_token: str | None = None
    test_input_s3_endpoint_url: str | None = None
    test_input_s3_access_key: str | None = None
    test_input_s3_secret_key: str | None = None
    test_input_s3_bucket: str = "user-data-test"
    test_input_s3_region: str = "us-east-1"
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

    def require_test_worker_bridge(self) -> "Settings":
        if not self.test_worker_bridge_enabled:
            raise ValueError("test worker bridge is not enabled")
        required = {
            "test_central_url": self.test_central_url,
            "test_central_api_token": self.test_central_api_token,
            "test_input_s3_endpoint_url": self.test_input_s3_endpoint_url,
            "test_input_s3_access_key": self.test_input_s3_access_key,
            "test_input_s3_secret_key": self.test_input_s3_secret_key,
        }
        missing = sorted(key for key, value in required.items() if not value)
        if missing:
            raise ValueError(
                "test worker bridge configuration is incomplete: "
                + ", ".join(missing)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
