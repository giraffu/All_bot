from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    redis_url: str
    auth_token: str

    # MinIO Configuration
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_result_bucket: str
    minio_secure: bool = False

    # Agent Configuration
    agent_secret_token: str

    model_config = SettingsConfigDict(extra="ignore")


settings = Settings()
