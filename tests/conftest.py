import asyncio
import contextlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


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
