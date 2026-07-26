from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .config import Settings

ProgressCallback = Callable[[str], Awaitable[None]]


class OperatorError(RuntimeError):
    pass


class OperatorPort(Protocol):
    async def list_slots(self) -> dict[str, Any]: ...

    async def read_ledger(self) -> dict[str, Any]: ...

    async def status(self, slot_id: str | None = None) -> dict[str, Any]: ...

    async def execute_switch(
        self,
        *,
        physical_slot: str,
        target_slot_id: str,
        current_slot_id: str | None,
        operation_id: str,
        progress: ProgressCallback,
    ) -> dict[str, Any]: ...


_STAGE_RE = re.compile(
    r"\[lan-aio-takeover\]\s+(preflight|pull-image|warm-cache|drain-legacy|"
    r"wait-idle|stop-old|start-disabled|enable-aio|auto rollback|failure)"
)
_SENSITIVE_RE = re.compile(
    r"(?i)(token|secret|password|authorization|access[_-]?key)\s*[:=]\s*[^\s,]+"
)


def redact_error(value: str) -> str:
    return _SENSITIVE_RE.sub(r"\1=[redacted]", value)[:2000]


def parse_last_json(value: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(value):
        if char != "{":
            continue
        try:
            candidate, end = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and not value[index + end :].strip():
            return candidate
    raise OperatorError("operator did not return a JSON payload")


class CliLanAioOperator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.script = settings.allbot_root / "scripts/lan_aio_fleet_prod_ops.py"

    def _base_command(self) -> list[str]:
        return [
            sys.executable,
            str(self.script),
        ]

    def _common_args(self) -> list[str]:
        return [
            "--state-dir",
            str(self.settings.state_dir),
            "--prod-env-file",
            str(self.settings.prod_env_file),
            "--aio-env-file",
            str(self.settings.aio_env_file),
            "--model-env-file",
            str(self.settings.model_env_file),
        ]

    async def _run(
        self,
        action_args: list[str],
        *,
        timeout: float,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        command = [*self._base_command(), *action_args, *self._common_args()]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.settings.allbot_root,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output: list[str] = []

        async def collect() -> None:
            assert process.stdout is not None
            while line := await process.stdout.readline():
                text = line.decode("utf-8", errors="replace").rstrip()
                output.append(text)
                if progress:
                    match = _STAGE_RE.search(text)
                    if match:
                        await progress(match.group(1).replace(" ", "-"))

        try:
            await asyncio.wait_for(collect(), timeout=timeout)
            return_code = await process.wait()
        except TimeoutError as exc:
            process.terminate()
            await process.wait()
            raise OperatorError("operator timed out") from exc
        rendered = "\n".join(output)
        if return_code != 0:
            raise OperatorError(redact_error(rendered or f"operator exit {return_code}"))
        return parse_last_json(rendered)

    async def list_slots(self) -> dict[str, Any]:
        return await self._run(["list", "--include-disabled"], timeout=20)

    async def read_ledger(self) -> dict[str, Any]:
        import yaml

        path = self.settings.state_dir / "current.yml"
        if not path.exists():
            return {}
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return payload if isinstance(payload, dict) else {}

    async def status(self, slot_id: str | None = None) -> dict[str, Any]:
        args = ["status", "--include-disabled"]
        if slot_id:
            args.extend(["--slot", slot_id])
        return await self._run(args, timeout=180)

    async def execute_switch(
        self,
        *,
        physical_slot: str,
        target_slot_id: str,
        current_slot_id: str | None,
        operation_id: str,
        progress: ProgressCallback,
    ) -> dict[str, Any]:
        if current_slot_id:
            args = [
                "takeover",
                "--slot",
                target_slot_id,
                "--replace-slot",
                current_slot_id,
                "--include-disabled",
                "--failure-policy",
                "auto_rollback",
                "--operation-id",
                operation_id,
                "--execute",
            ]
        else:
            args = [
                "recover",
                "--physical-slot",
                physical_slot,
                "--slot",
                target_slot_id,
                "--prefer",
                "candidate",
                "--operation-id",
                operation_id,
                "--execute",
            ]
        return await self._run(args, timeout=7200, progress=progress)
