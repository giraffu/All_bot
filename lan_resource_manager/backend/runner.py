from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml

from .operator import parse_last_json, redact_error
from scripts.classify_ci_change import classify_change_scope

RunJson = Callable[..., Awaitable[dict[str, Any]]]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._~-]{3,240}$")
ENVIRONMENTS = {"test", "prod"}
TEST_SERVICES = {
    "central-api",
    "web-api",
    "main-bot",
    "qqcc-bot",
    "qqcc-config-backend",
    "qqcc-config-frontend",
    "private-bot-worker",
    "imgproxy",
    "public-web",
}
ARTIFACT_SERVICE = {
    "dashboard-backend": "dashboard",
    "dashboard-frontend": "dashboard",
    "payment-api": "payment-api",
    "paid-group-bot": "paid-group-bot",
    "support-bot": "support-platform",
}
ALLOWED_ACTIONS = {
    "catalog",
    "candidate",
    "build_status",
    "environment_status",
    "start_build",
    "plan",
    "deploy",
    "set_maintenance",
}


class RunnerError(RuntimeError):
    pass


class ReleaseRunner:
    def __init__(self, allbot_root: Path, run_json: RunJson | None = None):
        self.root = allbot_root
        self.release = self.root / "scripts/release.py"
        self.maintenance = self.root / "scripts/release_maintenance.py"
        self.run_json = run_json or self._run_json

    async def _run(self, command: list[str], timeout: int = 7200) -> str:
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        token_file = os.environ.get("GITHUB_ACTIONS_TOKEN_FILE")
        if token_file:
            try:
                env["GH_TOKEN"] = Path(token_file).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise RunnerError("github_token_unavailable") from exc
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.root,
            env=env,
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

    def _policy_modules(self) -> dict[str, dict[str, Any]]:
        path = self.root / "deploy/release-policy.yml"
        try:
            policy = yaml.safe_load(path.read_text(encoding="utf-8"))
            modules = policy["independent_modules"]
        except (OSError, KeyError, TypeError, yaml.YAMLError) as exc:
            raise RunnerError("release_policy_invalid") from exc
        if not isinstance(modules, dict):
            raise RunnerError("release_policy_invalid")
        return {
            str(name): {"artifacts": list(config.get("artifacts") or [])}
            for name, config in modules.items()
            if isinstance(config, dict)
        }

    def _validate_common(self, payload: dict[str, Any]):
        environment = payload.get("environment")
        module = payload.get("module")
        sha = payload.get("sha")
        if environment not in ENVIRONMENTS:
            raise RunnerError("invalid_environment")
        if not isinstance(module, str) or not re.fullmatch(r"[a-z0-9-]{1,80}", module):
            raise RunnerError("invalid_module")
        if module not in self._policy_modules():
            raise RunnerError("invalid_module")
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            raise RunnerError("invalid_sha")
        maintenance = payload.get("maintenance")
        if maintenance not in {"planner", "rolling"}:
            raise RunnerError("invalid_maintenance_mode")
        if maintenance == "rolling" and environment != "prod":
            raise RunnerError("rolling_only_for_prod")
        return environment, module, sha, maintenance

    async def dispatch(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action not in ALLOWED_ACTIONS:
            raise RunnerError("unsupported_action")
        if action == "catalog":
            modules = self._policy_modules()
            test_modules = []
            for name, config in modules.items():
                services = {
                    ARTIFACT_SERVICE.get(artifact, artifact)
                    for artifact in config["artifacts"]
                }
                if services <= TEST_SERVICES:
                    test_modules.append(name)
            return {
                "modules": modules,
                "environments": {
                    "test": {
                        "label": "测试环境",
                        "modules": sorted(test_modules),
                        "maintenance_supported": True,
                    },
                    "prod": {
                        "label": "正式环境",
                        "modules": sorted(modules),
                        "maintenance_supported": True,
                    },
                },
            }
        if action == "candidate":
            return await self._candidate()
        if action == "build_status":
            sha = payload.get("sha")
            if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
                raise RunnerError("invalid_sha")
            ci_runs, modular_runs, bundle_ready = await asyncio.gather(
                self._gh_runs("control-plane-release.yml", sha),
                self._gh_runs("modular-release-v2.yml", sha),
                self._bundle_ready(sha),
            )
            return {
                "sha": sha,
                "ci": ci_runs[0] if ci_runs else None,
                "build": modular_runs[0] if modular_runs else None,
                "bundle": {"status": "ready" if bundle_ready else "missing"},
            }
        if action == "environment_status":
            environment = payload.get("environment")
            if environment not in ENVIRONMENTS:
                raise RunnerError("invalid_environment")
            return await self.run_json(
                [
                    sys.executable,
                    str(self.maintenance),
                    "status",
                    "--env",
                    environment,
                ],
                timeout=15,
            )
        if action == "start_build":
            sha = payload.get("expected_main_sha")
            if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
                raise RunnerError("invalid_sha")
            candidate = await self._candidate()
            if candidate.get("main_sha") != sha:
                raise RunnerError("main_changed")
            return await self._start_build(sha, candidate)
        if action == "plan":
            environment, module, sha, _ = self._validate_common(payload)
            return await self.run_json(
                [
                    sys.executable,
                    str(self.release),
                    "plan",
                    "--env",
                    environment,
                    "--track",
                    "control-plane",
                    "--modules",
                    module,
                    "--sha",
                    sha,
                ],
                timeout=900,
            )
        if action == "deploy":
            environment, module, sha, maintenance = self._validate_common(payload)
            token = payload.get("plan_token")
            if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
                raise RunnerError("invalid_plan_token")
            command = [
                sys.executable,
                str(self.release),
                "deploy",
                "--env",
                environment,
                "--track",
                "control-plane",
                "--modules",
                module,
                "--sha",
                sha,
                "--plan-token",
                token,
                "--execute",
            ]
            if maintenance == "rolling":
                command.append("--no-maintenance")
            if environment == "prod":
                if payload.get("confirm_prod") is not True:
                    raise RunnerError("production_confirmation_required")
                command.append("--confirm-prod")
            return await self.run_json(command, timeout=7500)
        environment = payload.get("environment")
        if environment not in ENVIRONMENTS:
            raise RunnerError("invalid_environment")
        enabled = payload.get("enabled")
        expected = payload.get("expected_enabled")
        if not isinstance(enabled, bool) or not isinstance(expected, bool):
            raise RunnerError("invalid_maintenance_state")
        reason = str(payload.get("reason", ""))
        operation_id = str(payload.get("operation_id", ""))
        if not (3 <= len(reason) <= 240) or not re.fullmatch(
            r"[a-zA-Z0-9._:-]{3,100}", operation_id
        ):
            raise RunnerError("invalid_maintenance_request")
        command = [
            sys.executable,
            str(self.maintenance),
            "enable" if enabled else "disable",
            "--env",
            environment,
            "--expected-enabled",
            "true" if expected else "false",
            "--reason",
            reason,
            "--operation-id",
            operation_id,
            "--execute",
        ]
        if environment == "prod":
            command.append("--confirm-prod")
        return await self.run_json(command, timeout=120)

    async def _gh_runs(self, workflow: str, sha: str) -> list[dict[str, Any]]:
        output = await self._run(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                workflow,
                "--branch",
                "main",
                "--limit",
                "50",
                "--json",
                "databaseId,status,conclusion,headSha,url,event",
            ],
            timeout=60,
        )
        try:
            value = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RunnerError("github_response_invalid") from exc
        return (
            [item for item in value if item.get("headSha") == sha]
            if isinstance(value, list)
            else []
        )

    async def _bundle_ready(self, sha: str) -> bool:
        process = await asyncio.create_subprocess_exec(
            "oras",
            "manifest",
            "fetch",
            f"ghcr.io/giraffu/allbot-release-v2:{sha}",
            cwd=self.root,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await process.wait() == 0

    async def _change_scope(self, sha: str) -> str:
        output = await self._run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/giraffu/All_bot/commits/{sha}",
                "--jq",
                ".files[].filename",
            ],
            timeout=60,
        )
        return classify_change_scope(output.splitlines()).scope

    async def _latest_deployable_sha(self, main_sha: str) -> str | None:
        tags_output, history_output = await asyncio.gather(
            self._run(
                [
                    "oras",
                    "repo",
                    "tags",
                    "ghcr.io/giraffu/allbot-release-v2",
                ],
                timeout=60,
            ),
            self._run(
                [
                    "gh",
                    "api",
                    "--method",
                    "GET",
                    "--paginate",
                    "repos/giraffu/All_bot/commits",
                    "-f",
                    f"sha={main_sha}",
                    "-f",
                    "per_page=100",
                    "--jq",
                    ".[].sha",
                ],
                timeout=120,
            ),
        )
        tags = {
            value.strip()
            for value in tags_output.splitlines()
            if SHA_RE.fullmatch(value.strip())
        }
        return next(
            (
                value.strip()
                for value in history_output.splitlines()
                if value.strip() in tags
            ),
            None,
        )

    async def _candidate(self) -> dict[str, Any]:
        output = await self._run(
            [
                "gh",
                "api",
                "repos/giraffu/All_bot/git/ref/heads/main",
                "--jq",
                ".object.sha",
            ],
            timeout=60,
        )
        main_sha = output.strip()
        if not SHA_RE.fullmatch(main_sha):
            raise RunnerError("main_sha_unavailable")
        ci_runs, modular_runs, bundle_ready, scope = await asyncio.gather(
            self._gh_runs("control-plane-release.yml", main_sha),
            self._gh_runs("modular-release-v2.yml", main_sha),
            self._bundle_ready(main_sha),
            self._change_scope(main_sha),
        )
        deployable_sha = (
            main_sha
            if bundle_ready
            else await self._latest_deployable_sha(main_sha)
        )
        ci = ci_runs[0] if ci_runs else None
        build = modular_runs[0] if modular_runs else None
        blockers = []
        if scope in {"operator", "runtime"} and not bundle_ready:
            blockers.append("bundle_missing")
        if not ci or ci.get("conclusion") != "success":
            blockers.append("trusted_ci_missing")
        return {
            "main_sha": main_sha,
            "deployable_sha": deployable_sha,
            "scope": scope,
            "ci": ci,
            "bundle": {"status": "ready" if bundle_ready else "missing"},
            "build": build,
            "blockers": blockers,
        }

    async def _start_build(self, sha: str, candidate: dict[str, Any]) -> dict:
        build = candidate.get("build")
        if isinstance(build, dict) and build.get("status") in {
            "queued",
            "in_progress",
            "completed",
        } and build.get("conclusion") in {None, "success"}:
            return {
                "run_id": build.get("databaseId"),
                "status": build.get("status"),
                "reused": True,
            }
        ci = candidate.get("ci")
        if isinstance(ci, dict) and ci.get("conclusion") == "success":
            command = [
                "gh",
                "workflow",
                "run",
                "modular-release-v2.yml",
                "--ref",
                "main",
                "-f",
                f"source_sha={sha}",
                "-f",
                "release_channel=main",
                "-f",
                "validation_mode=full",
                "-f",
                f"upstream_run_id={ci['databaseId']}",
            ]
            run_id = None
        else:
            command = [
                "gh",
                "workflow",
                "run",
                "control-plane-release.yml",
                "--ref",
                "main",
            ]
            run_id = None
        await self._run(command, timeout=60)
        return {"run_id": run_id, "status": "queued", "reused": False}


async def _serve(socket_path: Path, runner: ReleaseRunner) -> None:
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
            result = await runner.dispatch(action, payload)
            response = {"ok": True, "result": result}
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
