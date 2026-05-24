from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable


@dataclass(frozen=True)
class TaskCoreServiceProviders:
    get_image_service: Callable[[], Any]
    get_storage_service: Callable[[], Any]
    get_task_registry: Callable[[], Any]
    get_permission_service: Callable[[], Any]
    get_submission_outbox: Callable[[], Any]


def _load_image_service():
    from src.services.image_service import image_service as image_service_impl

    return image_service_impl


def _load_storage():
    from src.services.storage import storage as storage_impl

    return storage_impl


def _load_task_registry():
    from src.services.task_registry import TaskRegistry as task_registry_impl

    return task_registry_impl


def _load_permission_service():
    from src.services.permission_service import permission_service as permission_service_impl

    return permission_service_impl


def _load_redis_client():
    from src.services.redis_client import redis_client as redis_client_impl

    return redis_client_impl


@lru_cache(maxsize=1)
def build_task_core_service_providers() -> TaskCoreServiceProviders:
    return TaskCoreServiceProviders(
        get_image_service=_load_image_service,
        get_storage_service=_load_storage,
        get_task_registry=_load_task_registry,
        get_permission_service=_load_permission_service,
        get_submission_outbox=_load_redis_client,
    )


def resolve_task_core_service(name: str) -> Any:
    providers = build_task_core_service_providers()
    service_getters = {
        "image_service": providers.get_image_service,
        "storage": providers.get_storage_service,
        "TaskRegistry": providers.get_task_registry,
        "permission_service": providers.get_permission_service,
        "redis_client": providers.get_submission_outbox,
    }
    try:
        return service_getters[name]()
    except KeyError as exc:
        raise AttributeError(name) from exc
