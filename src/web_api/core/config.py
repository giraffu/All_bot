import os


class Settings:
    PROJECT_NAME: str = "All_bot Web BFF API"
    VERSION: str = "1.0.0"

    # JWT Auth
    SECRET_KEY: str = os.getenv("JWT_SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY is not securely set in environment variables!")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Redis
    REDIS_URL: str = os.environ["REDIS_URL"]


settings = Settings()
