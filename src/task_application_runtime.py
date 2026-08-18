from __future__ import annotations

from src.core.task_application import TaskApplication
from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.task_core_process_defaults import (
    build_runtime_default_task_core_process_dependencies,
)


_configured_task_application: TaskApplication | None = None


def configure_task_application(
    *,
    application: TaskApplication | None = None,
    dependencies: TaskCoreProcessDependencies | None = None,
) -> TaskApplication:
    """Install the process-wide application service from an explicit entrypoint."""
    global _configured_task_application

    if application is not None and dependencies is not None:
        raise ValueError("Provide application or dependencies, not both")
    if application is None and dependencies is None and _configured_task_application:
        return _configured_task_application
    if application is None:
        dependencies = (
            dependencies or build_runtime_default_task_core_process_dependencies()
        )
        application = TaskApplication(dependencies=dependencies)
    _configured_task_application = application
    return application


def get_task_application() -> TaskApplication:
    application = _configured_task_application
    if application is None:
        raise RuntimeError(
            "TaskApplication is not configured; initialize it at the process entrypoint"
        )
    return application
