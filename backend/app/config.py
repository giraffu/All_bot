from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    redis_url: str = "redis://backend-redis-1:6379/0"
    auth_token: str = "your_secure_token_here"

    # Workflow templates directory (still used for mapping or default configs if needed by some tasks,
    # though agent uses its own)
    workflows_dir: str = "/app/workflows"

    # MinIO Configuration
    minio_endpoint: str = "192.168.1.115:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_result_bucket: str = "comfyui-temp"
    minio_secure: bool = False

    # Agent Configuration
    agent_secret_token: str = "super_secret_agent_token_2026"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
