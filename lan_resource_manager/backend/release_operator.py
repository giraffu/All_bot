from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from .config import Settings


class ReleaseOperatorError(RuntimeError):
    pass


class ReleaseOperatorPort(Protocol):
    async def catalog(self) -> dict[str, Any]: ...
    async def candidate(self) -> dict[str, Any]: ...
    async def build_status(self, sha: str) -> dict[str, Any]: ...
    async def environment_status(self, environment: str) -> dict[str, Any]: ...
    async def start_build(self, expected_main_sha: str) -> dict[str, Any]: ...
    async def plan(
        self, environment: str, module: str, sha: str, maintenance: str
    ) -> dict[str, Any]: ...
    async def deploy(self, **kwargs: Any) -> dict[str, Any]: ...
    async def set_maintenance(self, **kwargs: Any) -> dict[str, Any]: ...


class UnixReleaseOperator:
    """Narrow JSON-RPC adapter. The web process never receives runner credentials."""

    def __init__(self, settings: Settings):
        self.socket_path = settings.release_runner_socket

    async def _call(self, action: str, payload: dict[str, Any] | None = None) -> dict:
        try:
            reader, writer = await asyncio.open_unix_connection(self.socket_path)
            writer.write(
                json.dumps({"action": action, "payload": payload or {}}).encode()
                + b"\n"
            )
            await writer.drain()
            raw = await asyncio.wait_for(reader.readline(), timeout=7500)
            writer.close()
            await writer.wait_closed()
        except (OSError, TimeoutError) as exc:
            raise ReleaseOperatorError("release_runner_unavailable") from exc
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReleaseOperatorError("release_runner_invalid_response") from exc
        if not response.get("ok"):
            raise ReleaseOperatorError(str(response.get("error", "release_runner_failed")))
        result = response.get("result")
        if not isinstance(result, dict):
            raise ReleaseOperatorError("release_runner_invalid_response")
        return result

    async def catalog(self):
        return await self._call("catalog")

    async def candidate(self):
        return await self._call("candidate")

    async def build_status(self, sha):
        return await self._call("build_status", {"sha": sha})

    async def environment_status(self, environment):
        return await self._call("environment_status", {"environment": environment})

    async def start_build(self, expected_main_sha):
        return await self._call("start_build", {"expected_main_sha": expected_main_sha})

    async def plan(self, environment, module, sha, maintenance):
        return await self._call(
            "plan",
            {
                "environment": environment,
                "module": module,
                "sha": sha,
                "maintenance": maintenance,
            },
        )

    async def deploy(self, **kwargs):
        return await self._call("deploy", kwargs)

    async def set_maintenance(self, **kwargs):
        return await self._call("set_maintenance", kwargs)
