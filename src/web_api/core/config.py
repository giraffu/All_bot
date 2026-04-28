import os

from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "All_bot Web BFF API"
    VERSION: str = "1.0.0"
    
    # JWT Auth
    SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "super-secret-jwt-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://:redispassword@127.0.0.1:6379/1")

settings = Settings()
