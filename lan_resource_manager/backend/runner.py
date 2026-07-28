from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from .operator import parse_last_json, redact_error


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
MODULE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
SLOTS = tuple("ABCDEFGH")
ENVIRONMENTS = {"test", "prod"}
ALLOWED_ACTIONS = {
    "catalog",
    "integration_status",
    "integrate_slots",
    "align_slots",
    "build_modules",
    "deploy_modules",
    "module_status",
}


class RunnerError(RuntimeError):
    pass


class ReleaseRunner:
    """Allowlisted host adapter for the existing workspace and release CLIs."""

    def __init__(self, allbot_root: Path, run_json=None):
        self.root = allbot_root
        self.run_json = run_json or self._run_json

    def _workspace_repo(self) -> Path:
        return Path(os.environ.get("WORKSPACE_REPO_ROOT", str(self.root))).resolve()

    def _release_script(self) -> Path:
        return self._workspace_repo() / "scripts/release.py"

    async def _run(self, command: list[str], timeout: int = 28800) -> str:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.root,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError as exc:
            process.terminate()
            await process.wait()
            raise RunnerError("runner_command_timed_out") from exc
        rendered = output.decode(errors="replace")
        if process.returncode:
            raise RunnerError(redact_error(rendered or "runner_command_failed"))
        return rendered

    async def _run_json(self, command: list[str], **kwargs) -> dict[str, Any]:
        return parse_last_json(await self._run(command, **kwargs))

    def _catalog(self) -> dict[str, dict[str, Any]]:
        path = self._workspace_repo() / "deploy/module-catalog.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            modules = document["modules"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RunnerError("module_catalog_invalid") from exc
        if not isinstance(modules, dict):
            raise RunnerError("module_catalog_invalid")
        return {
            str(name): {
                "kind": str(config.get("kind") or ""),
                "adapter": str(config.get("adapter") or ""),
                "environments": list(config.get("environments") or []),
                "build_only": config.get("adapter") == "build-only",
                "requires_target": config.get("adapter") == "gpu",
            }
            for name, config in modules.items()
            if isinstance(config, dict)
        }

    async def _remote_main_sha(self) -> str:
        output = await self._run(
            ["git", "ls-remote", "--exit-code", "origin", "refs/heads/main"],
            timeout=60,
        )
        sha = output.split()[0] if output.split() else ""
        if not SHA_RE.fullmatch(sha):
            raise RunnerError("main_sha_unavailable")
        return sha

    @staticmethod
    def _selected_modules(value: Any) -> list[str]:
        if (
            not isinstance(value, list)
            or not value
            or len(value) != len(set(value))
            or not all(isinstance(name, str) and MODULE_RE.fullmatch(name) for name in value)
        ):
            raise RunnerError("invalid_modules")
        return sorted(value)

    @staticmethod
    def _selected_slots(value: Any) -> list[str]:
        if (
            not isinstance(value, list)
            or not value
            or len(value) != len(set(value))
            or not all(slot in SLOTS for slot in value)
        ):
            raise RunnerError("invalid_slots")
        return sorted(value)

    def _queue_root(self) -> Path:
        return Path(
            os.environ.get(
                "INTEGRATION_QUEUE_ROOT",
                str(Path.home() / ".local/state/allbot/ai-integration-queue"),
            )
        )

    def _queue_records(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for state in ("pending", "integrating", "needs-rebase", "completed"):
            rows = []
            for path in sorted((self._queue_root() / state).glob("*.json")):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    rows.append({"id": path.stem, "status": "invalid"})
                    continue
                rows.append(
                    {
                        "id": path.stem,
                        "slot": record.get("slot"),
                        "branch": record.get("branch"),
                        "head": record.get("head"),
                        "base_sha": record.get("base_sha"),
                        "status": record.get("status") or state,
                        "main_sha": record.get("main_sha"),
                        "reason": record.get("reason"),
                        "conflict_files": record.get("conflict_files") or [],
                    }
                )
            result[state] = rows
        return result

    async def dispatch(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action not in ALLOWED_ACTIONS:
            raise RunnerError("unsupported_action")
        catalog = self._catalog()

        if action == "catalog":
            return {"modules": catalog}

        if action == "integration_status":
            raw = await self._run(
                [
                    sys.executable,
                    str(self.root / "scripts/manage_ai_workspaces.py"),
                    "--repo",
                    str(
                        self._workspace_repo()
                    ),
                    "status",
                ],
                timeout=60,
            )
            try:
                slots = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RunnerError("workspace_status_invalid") from exc
            if not isinstance(slots, list):
                raise RunnerError("workspace_status_invalid")
            return {
                "main_sha": await self._remote_main_sha(),
                "slots": slots,
                "queue": self._queue_records(),
            }

        if action in {"integrate_slots", "align_slots"}:
            slots = self._selected_slots(payload.get("slots"))
            expected = payload.get("expected_main_sha")
            if not isinstance(expected, str) or not SHA_RE.fullmatch(expected):
                raise RunnerError("invalid_sha")
            prefix = "INTEGRATE" if action == "integrate_slots" else "ALIGN"
            if payload.get("confirmation") != f"{prefix} {','.join(slots)} {expected}":
                raise RunnerError("confirmation_mismatch")
            if await self._remote_main_sha() != expected:
                raise RunnerError("main_changed")
            repo = str(
                self._workspace_repo()
            )
            if action == "integrate_slots":
                heads = payload.get("heads")
                if (
                    not isinstance(heads, dict)
                    or set(heads) != set(slots)
                    or not all(
                        isinstance(values, list)
                        and values
                        and len(values) == len(set(values))
                        and all(
                            isinstance(head, str) and SHA_RE.fullmatch(head)
                            for head in values
                        )
                        for values in heads.values()
                    )
                ):
                    raise RunnerError("invalid_handoff_heads")
                command = [
                    sys.executable,
                    str(self.root / "scripts/auto_integrate_handoffs.py"),
                    "--repo",
                    repo,
                    "--queue-root",
                    str(self._queue_root()),
                    "integrate-all",
                    "--execute",
                ]
                for slot in slots:
                    for head in heads[slot]:
                        command.extend(["--head", head])
                return parse_last_json(await self._run(command))
            command = [
                sys.executable,
                str(self.root / "scripts/manage_ai_workspaces.py"),
                "--repo",
                repo,
                "--lock-path",
                os.environ.get(
                    "WORKSPACE_LOCK_PATH",
                    str(Path.home() / ".local/state/allbot/ai-workspaces.lock"),
                ),
                "align-merged",
            ]
            for slot in slots:
                command.extend(["--slot", slot])
            return parse_last_json(await self._run(command, timeout=300))

        if action == "build_modules":
            modules = self._selected_modules(payload.get("modules"))
            sha = payload.get("sha")
            if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
                raise RunnerError("invalid_sha")
            if any(name not in catalog for name in modules):
                raise RunnerError("invalid_modules")
            if payload.get("confirmation") != f"BUILD {','.join(modules)} {sha}":
                raise RunnerError("confirmation_mismatch")
            if await self._remote_main_sha() != sha:
                raise RunnerError("main_changed")
            command = [sys.executable, str(self._release_script()), "build"]
            for name in modules:
                command.extend(["--module", name])
            command.extend(["--sha", sha])
            built = parse_last_json(await self._run(command))
            artifacts = {
                name: built[name]
                for name in modules
                if isinstance(built.get(name), str)
                and DIGEST_RE.fullmatch(str(built[name]))
            }
            if set(artifacts) != set(modules):
                raise RunnerError("module_build_result_invalid")
            return {"sha": sha, "artifacts": artifacts}

        if action == "deploy_modules":
            environment = payload.get("environment")
            if environment not in ENVIRONMENTS:
                raise RunnerError("invalid_environment")
            artifacts = payload.get("artifacts")
            if (
                not isinstance(artifacts, dict)
                or not artifacts
                or not all(
                    isinstance(name, str)
                    and MODULE_RE.fullmatch(name)
                    and isinstance(ref, str)
                    and DIGEST_RE.fullmatch(ref)
                    for name, ref in artifacts.items()
                )
            ):
                raise RunnerError("invalid_artifacts")
            modules = sorted(artifacts)
            if environment == "test" and len(modules) > 2:
                raise RunnerError("test_module_limit")
            if any(
                name not in catalog
                or catalog[name]["build_only"]
                or environment not in catalog[name]["environments"]
                for name in modules
            ):
                raise RunnerError("module_unavailable")
            if payload.get("confirmation") != (
                f"DEPLOY {environment.upper()} {','.join(modules)}"
            ):
                raise RunnerError("confirmation_mismatch")
            targets = payload.get("targets") or {}
            completed = []
            results = {}
            for name in modules:
                command = [
                    sys.executable,
                    str(self._release_script()),
                    "deploy",
                    "--env",
                    environment,
                    "--module",
                    name,
                    "--artifact",
                    artifacts[name],
                ]
                if environment == "prod":
                    command.append("--confirm-prod")
                if catalog[name]["requires_target"]:
                    target = targets.get(name) if isinstance(targets, dict) else None
                    if (
                        not isinstance(target, dict)
                        or target.get("operator") not in {"runpod", "lan"}
                        or not isinstance(target.get("slot"), str)
                        or not target["slot"]
                    ):
                        raise RunnerError("gpu_target_required")
                    command.extend(
                        ["--operator", target["operator"], "--slot", target["slot"]]
                    )
                results[name] = parse_last_json(await self._run(command))
                completed.append(name)
            return {
                "environment": environment,
                "completed_modules": completed,
                "results": results,
            }

        environment = payload.get("environment")
        module = payload.get("module")
        if (
            environment not in ENVIRONMENTS
            or not isinstance(module, str)
            or module not in catalog
        ):
            raise RunnerError("invalid_status_target")
        return await self.run_json(
            [
                sys.executable,
                str(self._release_script()),
                "status",
                "--env",
                environment,
                "--module",
                module,
            ],
            timeout=60,
        )


async def _serve(socket_path: Path, runner: ReleaseRunner) -> None:
    Path(os.environ.get("TMPDIR", "/home/app/.cache/allbot/releases")).mkdir(
        parents=True, exist_ok=True
    )
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=10)
            request = json.loads(raw)
            action = request.get("action")
            payload = request.get("payload")
            if not isinstance(action, str) or not isinstance(payload, dict):
                raise RunnerError("invalid_request")
            response = {"ok": True, "result": await runner.dispatch(action, payload)}
        except Exception as exc:
            response = {
                "ok": False,
                "error": redact_error(str(exc) or "release_runner_failed")[:500],
            }
        writer.write(json.dumps(response, ensure_ascii=False).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, path=socket_path)
    os.chmod(socket_path, 0o660)
    async with server:
        await server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--allbot-root", default="/workspace")
    args = parser.parse_args()
    asyncio.run(_serve(Path(args.socket), ReleaseRunner(Path(args.allbot_root))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
