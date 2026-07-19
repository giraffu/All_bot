import asyncio
import contextlib
import os
import sys
from pathlib import Path

import pytest
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Application imports are intentionally strict and never auto-load a repository
# .env. Tests may opt into a developer env through the explicit loader, then fill
# only missing keys with synthetic values.
_DEV_ENV_PATH = os.getenv("ALLBOT_DEV_ENV_FILE", "").strip()
_DEV_ENV_FILE = Path(_DEV_ENV_PATH) if _DEV_ENV_PATH else None
if _DEV_ENV_FILE is not None and _DEV_ENV_FILE.is_file():
    for _key, _value in dotenv_values(_DEV_ENV_FILE).items():
        if _key and _value is not None:
            os.environ.setdefault(_key, _value)
_TEST_RUNTIME_ENV = {
    "ALLBOT_ENV": "test",
    "BOT_TYPE": "TEST",
    "TELEGRAM_API_BASE_URL": "https://api.telegram.org",
    "TELEGRAM_FILE_BASE_URL": "https://api.telegram.org/file/bot",
    "BOT_TOKEN": "123456:test-bot-token",
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost/bot_db",
    "REDIS_URL": "redis://:redispassword@127.0.0.1:6379/0",
    "MINIO_ENDPOINT": "127.0.0.1:9000",
    "MINIO_ACCESS_KEY": "test-access",
    "MINIO_SECRET_KEY": "test-secret",
    "MINIO_BUCKET": "bot-data",
    "API_BASE": "http://127.0.0.1:8003",
    "API_TOKEN": "test-api-token",
    "AUTH_TOKEN": "test-auth-token",
    "AGENT_SECRET_TOKEN": "test-agent-token",
    "MINIO_RESULT_BUCKET": "comfyui-temp",
    "MINIO_TEMPLATE_BUCKET": "bot-template",
    "MINIO_PUBLIC_URL": "http://127.0.0.1:9000",
    "IMGPROXY_URL": "http://127.0.0.1:8084",
    "JWT_SECRET_KEY": "test-jwt-secret",
    "DASHBOARD_SECRET_KEY": "test-dashboard-secret",
    "DASHBOARD_ADMIN_USERNAME": "admin",
    "DASHBOARD_ADMIN_PASSWORD_HASH": "$2b$12$Kk9WvI6qO8uA5j0M7Nf8q.nB2sA1qQ.xZ1HjD3wUoYv2yQ1.hX1bC",
    "QQCC_CONFIG_SECRET_KEY": "test-qqcc-secret",
    "QQCC_CONFIG_ADMIN_USERNAME": "qqcc_admin",
    "QQCC_CONFIG_ADMIN_PASSWORD_HASH": "$2b$12$Kk9WvI6qO8uA5j0M7Nf8q.nB2sA1qQ.xZ1HjD3wUoYv2yQ1.hX1bC",
    "DB_POOL_SIZE": "5",
    "DB_MAX_OVERFLOW": "10",
    "R2_MAX_POOL_CONNECTIONS": "100",
    "R2_EXISTS_POSITIVE_TTL_SECONDS": "60",
    "R2_EXISTS_NEGATIVE_TTL_SECONDS": "5",
    "R2_EXISTS_CACHE_MAX_ENTRIES": "5000",
    "R2_HEAD_SEMAPHORE_LIMIT": "32",
    "R2_HEAD_CONNECT_TIMEOUT_SECONDS": "2",
    "R2_HEAD_READ_TIMEOUT_SECONDS": "3",
    "R2_HEAD_MAX_ATTEMPTS": "1",
    "POLL_INTERVAL": "2",
    "POLL_TIMEOUT": "180",
    "ENABLE_PUBLIC_SHARE": "false",
    "ENABLE_FREE_EDIT_V2": "false",
    "ENABLE_SCAIL2_LONG_ACTION_TRANSFER": "false",
    "DAILY_LIMIT": "10",
}
for _key, _value in _TEST_RUNTIME_ENV.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture(scope="session", autouse=True)
def cleanup_async_resources():
    yield

    async def _cleanup():
        from src.database.core import engine
        from src.services.redis_client import redis_client

        with contextlib.suppress(Exception):
            await engine.dispose()
        with contextlib.suppress(Exception):
            await redis_client.close()

    asyncio.run(_cleanup())
