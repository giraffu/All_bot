from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Callable

import httpx


_PUBLIC_HIT_STATUSES = {200, 204, 206, 301, 302, 304}


@dataclass(frozen=True)
class _CacheEntry:
    exists: bool
    expires_at: float


class R2PublicProbeService:
    def __init__(
        self,
        *,
        client: object | None = None,
        positive_ttl_seconds: float | None = None,
        negative_ttl_seconds: float | None = None,
        max_entries: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._positive_ttl_seconds = float(
            positive_ttl_seconds
            if positive_ttl_seconds is not None
            else os.getenv("R2_EXISTS_POSITIVE_TTL_SECONDS", "60")
        )
        self._negative_ttl_seconds = float(
            negative_ttl_seconds
            if negative_ttl_seconds is not None
            else os.getenv("R2_EXISTS_NEGATIVE_TTL_SECONDS", "5")
        )
        self._max_entries = max(
            1,
            int(
                max_entries
                if max_entries is not None
                else os.getenv("R2_EXISTS_CACHE_MAX_ENTRIES", "5000")
            ),
        )
        self._clock = clock
        self._lock = asyncio.Lock()
        self._cache: dict[str, _CacheEntry] = {}
        self._inflight: dict[str, asyncio.Task[bool]] = {}

    @staticmethod
    def normalize_object_key(object_key: str) -> str:
        normalized = str(object_key or "").strip().lstrip("/")
        while "//" in normalized:
            normalized = normalized.replace("//", "/")
        return normalized

    async def start(self) -> None:
        await self._get_client()

    async def close(self) -> None:
        async with self._lock:
            client = self._client
            self._client = None
            self._cache.clear()
        if client is not None:
            close = getattr(client, "aclose", None)
            if callable(close):
                await close()

    async def _get_client(self):
        async with self._lock:
            if self._client is None:
                max_connections = max(
                    1,
                    int(os.getenv("R2_MAX_POOL_CONNECTIONS", "100")),
                )
                self._client = httpx.AsyncClient(
                    trust_env=False,
                    timeout=None,
                    limits=httpx.Limits(
                        max_connections=max_connections,
                        max_keepalive_connections=max_connections,
                    ),
                )
            return self._client

    async def probe(
        self,
        object_key: str,
        public_url: str,
        *,
        timeout_seconds: float,
    ) -> bool:
        normalized_key = self.normalize_object_key(object_key)
        if not normalized_key or not public_url:
            return False

        now = self._clock()
        async with self._lock:
            cached = self._cache.get(normalized_key)
            if cached is not None and cached.expires_at > now:
                return cached.exists
            if cached is not None:
                self._cache.pop(normalized_key, None)
            task = self._inflight.get(normalized_key)
            if task is None:
                task = asyncio.create_task(
                    self._probe_and_cache(
                        normalized_key,
                        public_url,
                        timeout_seconds=timeout_seconds,
                    )
                )
                self._inflight[normalized_key] = task
        return await asyncio.shield(task)

    async def _probe_and_cache(
        self,
        normalized_key: str,
        public_url: str,
        *,
        timeout_seconds: float,
    ) -> bool:
        cache_ttl: float | None = None
        result = False
        try:
            client = await self._get_client()
            timeout = httpx.Timeout(
                timeout_seconds,
                connect=min(timeout_seconds, 1.0),
            )
            response = await client.head(
                public_url,
                follow_redirects=True,
                timeout=timeout,
            )
            if response.status_code == 405:
                response = await client.get(
                    public_url,
                    headers={"Range": "bytes=0-0"},
                    follow_redirects=True,
                    timeout=timeout,
                )
            if response.status_code in _PUBLIC_HIT_STATUSES:
                result = True
                cache_ttl = self._positive_ttl_seconds
            elif response.status_code == 404:
                cache_ttl = self._negative_ttl_seconds
        except httpx.HTTPError:
            result = False
        finally:
            async with self._lock:
                if cache_ttl is not None:
                    if len(self._cache) >= self._max_entries:
                        self._cache.pop(next(iter(self._cache)), None)
                    self._cache[normalized_key] = _CacheEntry(
                        exists=result,
                        expires_at=self._clock() + cache_ttl,
                    )
                current_task = asyncio.current_task()
                if self._inflight.get(normalized_key) is current_task:
                    self._inflight.pop(normalized_key, None)
        return result


r2_public_probe_service = R2PublicProbeService()
