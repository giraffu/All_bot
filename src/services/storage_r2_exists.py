import asyncio
import threading
import time

from botocore.exceptions import ClientError


def init_r2_runtime_state(service, *, positive_ttl: int, negative_ttl: int, max_entries: int, semaphore_limit: int):
    service._r2_exists_cache = {}
    service._r2_exists_cache_lock = threading.Lock()
    service._r2_exists_positive_ttl = max(1, positive_ttl)
    service._r2_exists_negative_ttl = max(1, negative_ttl)
    service._r2_exists_cache_max_entries = max(100, max_entries)
    service._r2_head_semaphore_limit = max(1, semaphore_limit)
    service._r2_head_semaphore = None
    service._r2_exists_inflight_lock = None
    service._r2_exists_inflight = {}
    service._r2_async_primitives_loop = None


def ensure_r2_async_primitives(service):
    loop = asyncio.get_running_loop()
    if service._r2_async_primitives_loop is loop:
        return

    service._r2_async_primitives_loop = loop
    service._r2_head_semaphore = asyncio.Semaphore(service._r2_head_semaphore_limit)
    service._r2_exists_inflight_lock = asyncio.Lock()
    service._r2_exists_inflight = {}


def trim_r2_exists_cache_locked(service):
    if len(service._r2_exists_cache) <= service._r2_exists_cache_max_entries:
        return

    now = time.monotonic()
    expired_keys = [
        key
        for key, (_, expires_at, _) in service._r2_exists_cache.items()
        if expires_at <= now
    ]
    for key in expired_keys:
        service._r2_exists_cache.pop(key, None)

    while len(service._r2_exists_cache) > service._r2_exists_cache_max_entries:
        oldest_key = next(iter(service._r2_exists_cache))
        service._r2_exists_cache.pop(oldest_key, None)


def get_r2_exists_cache_entry_locked(service, object_name: str, now: float):
    entry = service._r2_exists_cache.get(object_name)
    if not entry:
        return None

    exists, expires_at, updated_at = entry
    if expires_at <= now:
        service._r2_exists_cache.pop(object_name, None)
        return None

    return exists, expires_at, updated_at


def get_r2_exists_cache(service, object_name: str):
    if not object_name:
        return None

    now = time.monotonic()
    with service._r2_exists_cache_lock:
        entry = get_r2_exists_cache_entry_locked(service, object_name, now)
        if not entry:
            return None
        return entry[0]


def set_r2_exists_cache(service, object_name: str, exists: bool):
    if not object_name:
        return

    ttl = (
        service._r2_exists_positive_ttl
        if exists
        else service._r2_exists_negative_ttl
    )
    updated_at = time.monotonic()
    expires_at = updated_at + ttl
    with service._r2_exists_cache_lock:
        service._r2_exists_cache[object_name] = (exists, expires_at, updated_at)
        trim_r2_exists_cache_locked(service)


def has_newer_positive_r2_exists_cache(service, object_name: str, probe_started_at: float) -> bool:
    now = time.monotonic()
    with service._r2_exists_cache_lock:
        entry = get_r2_exists_cache_entry_locked(service, object_name, now)
        if not entry:
            return False

        exists, _, updated_at = entry
        return exists is True and updated_at > probe_started_at


def invalidate_r2_exists_cache(service, object_name: str):
    if not object_name:
        return
    with service._r2_exists_cache_lock:
        service._r2_exists_cache.pop(object_name, None)


def mark_r2_object_exists(service, object_name: str):
    set_r2_exists_cache(service, object_name, True)


def get_r2_head_client(service):
    return getattr(service, "r2_head_client", None) or service.r2_client


async def remove_r2_inflight_task(service, object_name: str, task: asyncio.Task):
    if service._r2_exists_inflight_lock is None:
        return

    async with service._r2_exists_inflight_lock:
        if service._r2_exists_inflight.get(object_name) is task:
            service._r2_exists_inflight.pop(object_name, None)


def attach_r2_inflight_cleanup(service, object_name: str, task: asyncio.Task):
    def _cleanup(done_task: asyncio.Task):
        loop = done_task.get_loop()
        if loop.is_closed():
            return
        loop.create_task(remove_r2_inflight_task(service, object_name, done_task))

    task.add_done_callback(_cleanup)


def r2_object_exists_with_cache_hint(service, object_name: str, *, logger):
    head_client = get_r2_head_client(service)
    if not head_client or not service.r2_bucket:
        return False, False
    try:
        head_client.head_object(Bucket=service.r2_bucket, Key=object_name)
        return True, True
    except ClientError as exc:
        error = exc.response.get("Error", {}) if exc.response else {}
        code = str(error.get("Code", ""))
        status_code = (
            exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if exc.response
            else None
        )
        if code in {"404", "NoSuchKey", "NotFound"} or status_code == 404:
            return False, True

        logger.warning(
            "R2 head_object failed for %s with cache skipped: code=%s status=%s",
            object_name,
            code or "unknown",
            status_code,
        )
        return False, False
    except Exception as exc:
        logger.warning(
            "R2 head_object raised transient error for %s, skip negative cache: %s",
            object_name,
            exc,
        )
        return False, False


async def async_r2_object_exists_uncached(service, object_name: str, *, logger):
    probe_started_at = time.monotonic()
    async with service._r2_head_semaphore:
        exists, cacheable = await asyncio.to_thread(
            service._r2_object_exists_with_cache_hint, object_name
        )
    if cacheable:
        if not exists and has_newer_positive_r2_exists_cache(
            service, object_name, probe_started_at
        ):
            return True
        set_r2_exists_cache(service, object_name, exists)
    return exists


async def async_r2_object_exists(service, object_name: str, *, logger):
    if not object_name:
        return False

    cached = get_r2_exists_cache(service, object_name)
    if cached is not None:
        return cached

    if not get_r2_head_client(service) or not service.r2_bucket:
        return False

    ensure_r2_async_primitives(service)

    async with service._r2_exists_inflight_lock:
        cached = get_r2_exists_cache(service, object_name)
        if cached is not None:
            return cached

        inflight_task = service._r2_exists_inflight.get(object_name)
        if inflight_task is None:
            inflight_task = asyncio.create_task(
                async_r2_object_exists_uncached(service, object_name, logger=logger)
            )
            service._r2_exists_inflight[object_name] = inflight_task
            attach_r2_inflight_cleanup(service, object_name, inflight_task)
    return await asyncio.shield(inflight_task)
