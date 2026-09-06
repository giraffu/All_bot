from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


AsyncFinalizerHook = Callable[..., Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class TaskWebFinalizerDependencies:
    store_prompt_result: AsyncFinalizerHook
    store_prompt_failure_result: AsyncFinalizerHook
    finalize_character_reference: AsyncFinalizerHook
    finalize_official_asset: AsyncFinalizerHook


_configured_dependencies: TaskWebFinalizerDependencies | None = None


def configure_task_web_finalizer_dependencies(
    dependencies: TaskWebFinalizerDependencies,
) -> None:
    global _configured_dependencies
    _configured_dependencies = dependencies


def get_task_web_finalizer_dependencies() -> TaskWebFinalizerDependencies:
    if _configured_dependencies is None:
        raise RuntimeError(
            "Task web finalizer dependencies are not configured; "
            "initialize them at the process entrypoint"
        )
    return _configured_dependencies
