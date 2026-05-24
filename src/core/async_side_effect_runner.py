import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class AsyncSideEffectRunner:
    create_task_func: Callable[[Awaitable[Any]], Any]
    logger: logging.Logger

    def schedule(
        self,
        awaitable: Awaitable[Any],
        *,
        name: str = "async-side-effect",
    ) -> Any:
        async def _guard():
            try:
                return await awaitable
            except asyncio.CancelledError:
                self.logger.warning("Detached async side effect cancelled: %s", name)
                raise
            except Exception:
                self.logger.exception("Detached async side effect failed: %s", name)

        try:
            return self.create_task_func(_guard())
        except Exception:
            self.logger.exception("Failed to schedule async side effect: %s", name)
            raise


def build_async_side_effect_runner(
    *,
    create_task_func: Callable[[Awaitable[Any]], Any] = asyncio.create_task,
    logger: logging.Logger,
) -> AsyncSideEffectRunner:
    return AsyncSideEffectRunner(
        create_task_func=create_task_func,
        logger=logger,
    )


@lru_cache(maxsize=1)
def get_default_async_side_effect_runner() -> AsyncSideEffectRunner:
    return build_async_side_effect_runner(logger=logging.getLogger(__name__))
