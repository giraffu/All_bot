from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from .config import Settings


class ReleaseOperatorError(RuntimeError):
    pass


class ReleaseOperatorPort(Protocol):
    async def catalog(self) -> dict[str, Any]: ...
    async def integration_status(self) -> dict[str, Any]: ...
    async def integrate_slots(self, **kwargs: Any) -> dict[str, Any]: ...
    async def align_slots(self, **kwargs: Any) -> dict[str, Any]: ...
    async def build_modules(self, **kwargs: Any) -> dict[str, Any]: ...
    async def deploy_modules(self, **kwargs: Any) -> dict[str, Any]: ...
    async def module_status(self, **kwargs: Any) -> dict[str, Any]: ...


class UnixReleaseOperator:
    """Narrow JSON-RPC adapter; the LAN web process receives no release secrets."""

    def __init__(self, settings: Settings):
        self.socket_path = settings.release_runner_socket

    async def _call(
        self, action: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        timeout = 30000 if action in {
            "integrate_slots",
            "build_modules",
            "deploy_modules",
        } else 300
        try:
            reader, writer = await asyncio.open_unix_connection(self.socket_path)
            writer.write(
                json.dumps({"action": action, "payload": payload or {}}).encode()
                + b"\n"
            )
            await writer.drain()
            raw = await asyncio.wait_for(reader.readline(), timeout=timeout)
            writer.close()
            await writer.wait_closed()
        except (OSError, TimeoutError) as exc:
            raise ReleaseOperatorError("release_runner_unavailable") from exc
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReleaseOperatorError("release_runner_invalid_response") from exc
        if not response.get("ok"):
            raise ReleaseOperatorError(
                str(response.get("error", "release_runner_failed"))
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise ReleaseOperatorError("release_runner_invalid_response")
        return result

    async def catalog(self):
        return await self._call("catalog")

    async def integration_status(self):
        return await self._call("integration_status")

    async def integrate_slots(self, **kwargs):
        return await self._call("integrate_slots", kwargs)

    async def align_slots(self, **kwargs):
        return await self._call("align_slots", kwargs)

    async def build_modules(self, **kwargs):
        return await self._call("build_modules", kwargs)

    async def deploy_modules(self, **kwargs):
        return await self._call("deploy_modules", kwargs)

    async def module_status(self, **kwargs):
        return await self._call("module_status", kwargs)
