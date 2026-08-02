#!/usr/bin/env python3
"""Build and replace one explicitly selected immutable AllBot module."""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterator, Mapping, NamedTuple, Sequence
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "deploy" / "module-catalog.json"
DEFAULT_STATE_ROOT = (
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    / "allbot"
    / "module-releases"
)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_REF_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
PROXY_BUILD_ARGS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "FTP_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "ftp_proxy",
    "no_proxy",
)
ENVIRONMENTS = {
    "test": {
        "host": "allbot-do-sgp1-test-control",
        "project": "allbot-test",
        "env_file": "/etc/allbot/test.env",
        "overlay": "deploy/docker-compose-cloud-test.overlay.yml",
    },
    "prod": {
        "host": "allbot-do-sgp1-control",
        "project": "allbot-prod",
        "env_file": "/etc/allbot/prod.env",
        "overlay": "deploy/docker-compose-cloud-prod.overlay.yml",
    },
}
PAGES_PROJECTS = {"test": "allbot-web-cf-test", "prod": "allbot-web-prod"}
PAGES_URLS = {
    "test": "https://web-cf-test.aivison.it.com",
    "prod": "https://web.aivison.it.com",
}
PUBLIC_WEB_RUNTIME_FIELDS = {
    "api_base_url",
    "storage_url",
    "imgproxy_url",
    "telegram_bot_username",
    "tonconnect_manifest_url",
    "tonconnect_twa_return_url",
    "enable_free_edit_v2",
    "enable_free_edit_v3",
    "enable_scail2_long_action_transfer",
    "enable_ltx_t2v",
    "enable_ltx_t2v_msr",
    "enable_ltx_video_v2",
}


class ReleaseError(RuntimeError):
    pass


def load_web_runtime_config(
    path: Path,
    environment: str,
) -> tuple[dict[str, Any], str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError("Web runtime config is unavailable or invalid") from exc
    if not isinstance(document, Mapping) or document.get("schema_version") != 1:
        raise ReleaseError("unsupported Web runtime config schema_version")
    raw_values = document.get(environment)
    if not isinstance(raw_values, Mapping):
        raise ReleaseError(f"Web runtime config has no {environment!r} mapping")
    unknown = sorted(set(raw_values) - PUBLIC_WEB_RUNTIME_FIELDS)
    if unknown:
        raise ReleaseError(
            "unsupported public Web runtime fields: " + ", ".join(unknown)
        )
    values: dict[str, Any] = {}
    for key, value in raw_values.items():
        if not isinstance(value, (str, bool)):
            raise ReleaseError(f"Web runtime field {key} must be a string or boolean")
        normalized = value.strip() if isinstance(value, str) else value
        if normalized == "":
            raise ReleaseError(f"Web runtime field {key} cannot be empty")
        values[key] = normalized
    for required in ("api_base_url", "telegram_bot_username"):
        if required not in values:
            raise ReleaseError(f"Web runtime config requires {required}")
    canonical = json.dumps(
        values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    revision = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return values, revision


def render_web_runtime_config_script(
    values: Mapping[str, Any],
    *,
    git_sha: str,
    config_revision: str,
) -> str:
    payload = {
        **values,
        "release_sha": git_sha,
        "runtime_config_revision": config_revision,
    }
    return (
        "window.__ALLBOT_CONFIG__ = Object.freeze("
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + ");\n"
    )


def _artifact_revision(artifact: str) -> str:
    result = _run(["oras", "manifest", "fetch", artifact])
    if result.returncode:
        raise ReleaseError("unable to read Public Web artifact metadata")
    try:
        manifest = json.loads(result.stdout)
        revision = manifest["annotations"]["org.opencontainers.image.revision"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ReleaseError("Public Web artifact has no source revision") from exc
    if not isinstance(revision, str) or not FULL_SHA_RE.fullmatch(revision):
        raise ReleaseError("Public Web artifact source revision is invalid")
    return revision


def _find_single_module_archive(output: Path, module_name: str) -> Path:
    archives = sorted(output.rglob("*.tgz"))
    if len(archives) != 1:
        raise ReleaseError(
            f"{module_name} artifact must contain exactly one archive"
        )
    return archives[0]


class CommandResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def _run(command: Sequence[str], **kwargs: Any) -> CommandResult:
    stream_stderr = bool(kwargs.pop("stream_stderr", False))
    if stream_stderr:
        process = subprocess.Popen(
            list(command),
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            **kwargs,
        )
        stderr_lines: list[str] = []
        assert process.stderr is not None
        for line in process.stderr:
            sys.stderr.write(line)
            sys.stderr.flush()
            stderr_lines.append(line)
        return CommandResult(process.wait(), "", "".join(stderr_lines))
    result = subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
        **kwargs,
    )
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _ssh_command(host: str, remote_command: str) -> list[str]:
    command = ["ssh", "-o", "BatchMode=yes"]
    identity = os.environ.get("ALLBOT_SSH_IDENTITY_FILE")
    known_hosts = os.environ.get("ALLBOT_SSH_KNOWN_HOSTS_FILE")
    if identity:
        command.extend(["-o", "IdentitiesOnly=yes", "-i", identity])
    if known_hosts:
        command.extend(
            [
                "-o",
                f"UserKnownHostsFile={known_hosts}",
                "-o",
                "StrictHostKeyChecking=yes",
            ]
        )
    command.extend([host, remote_command])
    return command


@contextmanager
def temporary_checkout(sha: str) -> Iterator[Path]:
    directory = Path(tempfile.mkdtemp(prefix="allbot-module-build-"))
    checkout = directory / "checkout"
    added = False
    try:
        result = _run(
            ["git", "worktree", "add", "--detach", str(checkout), sha],
            cwd=ROOT,
        )
        if result.returncode:
            raise ReleaseError("unable to create a clean build checkout")
        added = True
        yield checkout
    finally:
        if added:
            _run(["git", "worktree", "remove", "--force", str(checkout)], cwd=ROOT)
        shutil.rmtree(directory, ignore_errors=True)


@contextmanager
def null_checkout(path: Path) -> Iterator[Path]:
    yield path


class ReleaseDependencies:
    def __init__(
        self,
        *,
        run: Callable[..., CommandResult] = _run,
        temporary_checkout: Callable[[str], Any] = temporary_checkout,
    ) -> None:
        self.run = run
        self.temporary_checkout = temporary_checkout


class FunctionAdapter:
    def __init__(
        self,
        *,
        inspect: Callable[..., str | None],
        deploy: Callable[..., Any],
        rollback: Callable[..., Any],
        status: Callable[..., Mapping[str, Any]],
    ) -> None:
        self.inspect = inspect
        self.deploy = deploy
        self.rollback = rollback
        self.status = status


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"invalid module catalog: {path}") from exc
    modules = document.get("modules") if isinstance(document, Mapping) else None
    if document.get("schema_version") != 1 or not isinstance(modules, Mapping):
        raise ReleaseError("module catalog schema_version must be 1")
    result = {str(name): dict(value) for name, value in modules.items()}
    for name, module in result.items():
        base = module.get("base")
        if base and base not in result:
            raise ReleaseError(f"{name} has unknown base module {base}")
        if not module.get("kind") or not module.get("adapter"):
            raise ReleaseError(f"{name} has an incomplete module contract")
    return result


def build_closure(
    catalog: Mapping[str, Mapping[str, Any]], requested: Sequence[str]
) -> list[str]:
    if not requested:
        raise ReleaseError("build requires at least one --module")
    unknown = set(requested) - set(catalog)
    if unknown:
        raise ReleaseError("unknown modules: " + ", ".join(sorted(unknown)))
    ordered: list[str] = []
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in ordered:
            return
        if name in visiting:
            raise ReleaseError("module base graph contains a cycle")
        visiting.add(name)
        base = catalog[name].get("base")
        if base:
            visit(str(base))
        visiting.remove(name)
        ordered.append(name)

    for name in requested:
        visit(name)
    return ordered


def _digest_for_ref(
    ref: str, *, kind: str, dependencies: ReleaseDependencies, cwd: Path
) -> str:
    command = (
        ["oras", "manifest", "fetch", "--descriptor", ref]
        if kind in {"pages", "contract"}
        else [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            ref,
            "--format",
            "{{json .Manifest.Digest}}",
        ]
    )
    result = dependencies.run(command, cwd=cwd)
    if result.returncode:
        raise ReleaseError(f"registry did not return a digest for {ref}")
    output = result.stdout.strip()
    if output.startswith(("{", '"')):
        try:
            descriptor = json.loads(output)
            output = str(
                descriptor["digest"] if isinstance(descriptor, Mapping) else descriptor
            )
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ReleaseError(f"registry descriptor is invalid for {ref}") from exc
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", output):
        raise ReleaseError(f"registry digest is invalid for {ref}")
    return output


def _input_files(checkout: Path, paths: Sequence[str]) -> list[Path]:
    files: list[Path] = []
    for relative in paths:
        path = checkout / relative
        if path.is_dir():
            files.extend(item for item in sorted(path.rglob("*")) if item.is_file())
        elif path.is_file():
            files.append(path)
        else:
            raise ReleaseError(f"declared build input is missing: {relative}")
    return sorted(set(files), key=lambda item: item.relative_to(checkout).as_posix())


def build_input_identity(
    name: str,
    module: Mapping[str, Any],
    *,
    checkout: Path,
    base_artifact: str | None,
) -> str:
    """Return the canonical identity of a build-only image's real inputs."""
    declared = [str(module["dockerfile"]), *map(str, module.get("build_inputs", []))]
    entries = [
        {
            "path": path.relative_to(checkout).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in _input_files(checkout, declared)
    ]
    payload = {
        "module": name,
        "target": module.get("target"),
        "base": base_artifact,
        "inputs": entries,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_build_environment(
    *,
    image_prefix: str,
    builder: str | None,
    dependencies: ReleaseDependencies,
    cwd: Path,
) -> None:
    if not image_prefix or "/" not in image_prefix or any(
        character.isspace() for character in image_prefix
    ):
        raise ReleaseError("image prefix must name a registry namespace")
    for name in PROXY_BUILD_ARGS:
        if name.lower() == "no_proxy":
            continue
        value = os.environ.get(name)
        if not value:
            continue
        parsed = urllib.parse.urlsplit(value if "://" in value else f"http://{value}")
        if (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}:
            raise ReleaseError(
                f"{name} uses a loopback proxy; configure a container-reachable "
                "proxy address before building"
            )
    command = ["docker", "buildx", "inspect", builder] if builder else [
        "docker",
        "buildx",
        "version",
    ]
    result = dependencies.run(command, cwd=cwd)
    if result.returncode:
        raise ReleaseError("Docker Buildx preflight failed")


def _build_image(
    name: str,
    module: Mapping[str, Any],
    *,
    sha: str,
    image_prefix: str,
    checkout: Path,
    built: Mapping[str, str],
    dependencies: ReleaseDependencies,
    builder: str | None,
    registry_cache_prefix: str | None,
    build_progress: str,
) -> str:
    base = module.get("base")
    base_artifact = built.get(str(base)) if base else None
    tag_suffix = sha
    if module.get("adapter") == "build-only":
        tag_suffix = "input-" + build_input_identity(
            name,
            module,
            checkout=checkout,
            base_artifact=base_artifact,
        )
    tag = f"{image_prefix}/{module['image']}:{tag_suffix}"
    existing = dependencies.run(
        ["docker", "buildx", "imagetools", "inspect", tag],
        cwd=checkout,
    )
    if existing.returncode:
        command = [
            "docker",
            "buildx",
            "build",
        ]
        if builder:
            command.extend(["--builder", builder])
        command.extend(
            [
                "--progress",
                build_progress,
                "--push",
                "-f",
                str(module["dockerfile"]),
                "-t",
                tag,
                "--build-arg",
                f"ALLBOT_GIT_SHA={sha}",
            ]
        )
        if registry_cache_prefix:
            cache_ref = f"{registry_cache_prefix}:{name}"
            command.extend(
                [
                    "--cache-from",
                    f"type=registry,ref={cache_ref}",
                    "--cache-to",
                    f"type=registry,ref={cache_ref},mode=max",
                ]
            )
        for proxy_name in PROXY_BUILD_ARGS:
            if os.environ.get(proxy_name):
                command.extend(["--build-arg", proxy_name])
        target = module.get("target")
        if target:
            command.extend(["--target", str(target)])
        if base:
            command.extend(["--build-arg", f"RUNTIME_BASE_IMAGE={built[str(base)]}"])
        command.append(".")
        started = time.monotonic()
        print(f"[build:{name}] started", file=sys.stderr)
        result = dependencies.run(command, cwd=checkout, stream_stderr=True)
        elapsed = time.monotonic() - started
        print(f"[build:{name}] finished in {elapsed:.1f}s", file=sys.stderr)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()[-20:]
            raise ReleaseError(
                f"module build failed: {name}"
                + (f": {' | '.join(detail)}" if detail else "")
            )
    digest = _digest_for_ref(
        tag, kind=str(module["kind"]), dependencies=dependencies, cwd=checkout
    )
    return f"{image_prefix}/{module['image']}@{digest}"


def _build_pages_or_contract(
    name: str,
    module: Mapping[str, Any],
    *,
    sha: str,
    image_prefix: str,
    checkout: Path,
    dependencies: ReleaseDependencies,
) -> str:
    repository = f"{image_prefix}/{module['repository']}"
    tag = f"{repository}:{sha}"
    existing = dependencies.run(["oras", "manifest", "fetch", tag], cwd=checkout)
    if existing.returncode:
        output = checkout / ".module-output" / name
        output.mkdir(parents=True, exist_ok=True)
        if module["kind"] == "pages":
            for command in (["npm", "ci"], ["npm", "run", "build"]):
                result = dependencies.run(command, cwd=checkout / "frontend")
                if result.returncode:
                    raise ReleaseError("public-web build failed")
            archive = output / "public-web-dist.tgz"
            result = dependencies.run(
                ["tar", "-czf", str(archive), "-C", "frontend", "dist"],
                cwd=checkout,
            )
            media_type = "application/vnd.allbot.public-web.v1+gzip"
        else:
            archive = output / f"{name}.tgz"
            result = dependencies.run(
                ["tar", "-czf", str(archive), *map(str, module["files"])],
                cwd=checkout,
            )
            media_type = "application/vnd.allbot.module-contract.v1+gzip"
        if result.returncode:
            raise ReleaseError(f"failed to package module {name}")
        pushed = dependencies.run(
            [
                "oras",
                "push",
                tag,
                "--artifact-type",
                "application/vnd.allbot.module.v1",
                "--annotation",
                f"org.opencontainers.image.revision={sha}",
                "--annotation",
                f"io.allbot.release.module={name}",
                f"{archive.relative_to(checkout)}:{media_type}",
            ],
            cwd=checkout,
        )
        if pushed.returncode:
            raise ReleaseError(f"failed to publish module {name}")
    digest = _digest_for_ref(
        tag, kind=str(module["kind"]), dependencies=dependencies, cwd=checkout
    )
    return f"{repository}@{digest}"


def build_modules(
    catalog: Mapping[str, Mapping[str, Any]],
    requested: Sequence[str],
    *,
    sha: str,
    image_prefix: str,
    builder: str | None = None,
    registry_cache_prefix: str | None = None,
    build_progress: str = "plain",
    dependencies: ReleaseDependencies | None = None,
) -> dict[str, str]:
    if not FULL_SHA_RE.fullmatch(sha):
        raise ReleaseError("build SHA must be a full Git SHA")
    dependencies = dependencies or ReleaseDependencies()
    built: dict[str, str] = {}
    with dependencies.temporary_checkout(sha) as checkout:
        _validate_build_environment(
            image_prefix=image_prefix,
            builder=builder,
            dependencies=dependencies,
            cwd=checkout,
        )
        for name in build_closure(catalog, requested):
            module = catalog[name]
            kind = str(module["kind"])
            if kind == "external-image":
                source = str(module["ref"])
                digest = _digest_for_ref(
                    source, kind=kind, dependencies=dependencies, cwd=checkout
                )
                repository = source.split("@", 1)[0]
                if ":" in repository.rsplit("/", 1)[-1]:
                    repository = repository.rsplit(":", 1)[0]
                built[name] = f"{repository}@{digest}"
            elif kind in {"pages", "contract"}:
                built[name] = _build_pages_or_contract(
                    name,
                    module,
                    sha=sha,
                    image_prefix=image_prefix,
                    checkout=checkout,
                    dependencies=dependencies,
                )
            else:
                built[name] = _build_image(
                    name,
                    module,
                    sha=sha,
                    image_prefix=image_prefix,
                    checkout=checkout,
                    built=built,
                    dependencies=dependencies,
                    builder=builder,
                    registry_cache_prefix=registry_cache_prefix,
                    build_progress=build_progress,
                )
    return built


def validate_deploy_request(
    *,
    environment: str,
    module_name: str,
    artifact: str,
    confirm_prod: bool,
) -> None:
    if environment not in ENVIRONMENTS:
        raise ReleaseError("environment must be test or prod")
    if environment == "prod" and not confirm_prod:
        raise ReleaseError("production deployment requires --confirm-prod")
    if not DIGEST_REF_RE.fullmatch(artifact):
        raise ReleaseError("artifact must use an exact repository@sha256 digest")
    if not module_name:
        raise ReleaseError("deployment requires one module")


def _state_path(root: Path, environment: str, module_name: str) -> Path:
    return root / environment / module_name / "current.json"


class LocalStateBackend:
    def __init__(self, root: Path) -> None:
        self.root = root

    def read(self, environment: str, module_name: str) -> dict[str, Any]:
        return read_status(self.root, environment, module_name)

    def write(
        self,
        environment: str,
        module_name: str,
        payload: Mapping[str, Any],
    ) -> None:
        _write_state(self.root, environment, module_name, payload)


class RemoteStateBackend:
    def __init__(
        self,
        *,
        host: str,
        root: Path = Path("/var/lib/allbot/module-release-state"),
        run: Callable[..., CommandResult] = _run,
    ) -> None:
        self.host = host
        self.root = root
        self.run = run

    def _path(self, environment: str, module_name: str) -> Path:
        if environment not in ENVIRONMENTS or not re.fullmatch(
            r"[a-z0-9][a-z0-9-]*", module_name
        ):
            raise ReleaseError("invalid remote release-state target")
        return self.root / environment / module_name / "current.json"

    def read(self, environment: str, module_name: str) -> dict[str, Any]:
        path = self._path(environment, module_name)
        result = self.run(
            _ssh_command(self.host, f"cat {path}")
        )
        if result.returncode:
            return {
                "environment": environment,
                "module": module_name,
                "status": "untracked",
            }
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReleaseError("remote module release state is invalid") from exc
        if not isinstance(value, dict):
            raise ReleaseError("remote module release state is invalid")
        return value

    def write(
        self,
        environment: str,
        module_name: str,
        payload: Mapping[str, Any],
    ) -> None:
        path = self._path(environment, module_name)
        encoded = base64.b64encode(
            (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        ).decode()
        quoted_directory = shlex.quote(str(path.parent))
        quoted_path = shlex.quote(str(path))
        quoted_payload = shlex.quote(encoded)
        script = (
            "set -eu\n"
            f"directory={quoted_directory}\n"
            'mkdir -p "$directory"\n'
            'chmod 700 "$directory"\n'
            'temporary=$(mktemp "$directory/.current.json.XXXXXX")\n'
            'trap \'rm -f "$temporary"\' EXIT\n'
            f"printf '%s' {quoted_payload} | base64 -d > \"$temporary\"\n"
            'chmod 600 "$temporary"\n'
            f'mv "$temporary" {quoted_path}\n'
            "trap - EXIT\n"
        )
        result = self.run(
            _ssh_command(self.host, "bash -s"),
            input=script,
        )
        if result.returncode:
            raise ReleaseError("unable to atomically write remote release state")


StateBackend = Path | LocalStateBackend | RemoteStateBackend


def _backend(value: StateBackend) -> LocalStateBackend | RemoteStateBackend:
    return LocalStateBackend(value) if isinstance(value, Path) else value


def _write_state(
    root: Path,
    environment: str,
    module_name: str,
    payload: Mapping[str, Any],
) -> None:
    path = _state_path(root, environment, module_name)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def read_status(root: Path, environment: str, module_name: str) -> dict[str, Any]:
    path = _state_path(root, environment, module_name)
    if not path.is_file():
        return {
            "environment": environment,
            "module": module_name,
            "status": "untracked",
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReleaseError("module release state is invalid") from exc
    if not isinstance(value, dict):
        raise ReleaseError("module release state is invalid")
    return value


def deploy_module(
    catalog: Mapping[str, Mapping[str, Any]],
    *,
    environment: str,
    module_name: str,
    artifact: str,
    confirm_prod: bool,
    state_root: StateBackend,
    adapters: Mapping[str, FunctionAdapter],
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_deploy_request(
        environment=environment,
        module_name=module_name,
        artifact=artifact,
        confirm_prod=confirm_prod,
    )
    if module_name not in catalog:
        raise ReleaseError(f"unknown module: {module_name}")
    module = catalog[module_name]
    supported = set(module.get("environments", []))
    if environment not in supported:
        raise ReleaseError(f"{module_name} is unavailable in {environment}")
    adapter_name = str(module["adapter"])
    if adapter_name == "build-only":
        raise ReleaseError(f"{module_name} is build-only")
    adapter = adapters.get(adapter_name)
    if adapter is None:
        raise ReleaseError(f"deployment adapter is unavailable: {adapter_name}")
    context = dict(context or {})
    context["desired_artifact"] = artifact
    state = _backend(state_root)
    previous_state = state.read(environment, module_name)
    live = adapter.inspect(environment, module_name, module, context)
    previous = live or previous_state.get("current")
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        adapter.deploy(environment, module_name, module, artifact, context)
        observed = dict(adapter.status(environment, module_name, module, context))
    except Exception as exc:
        if adapter_name != "database-migration" and previous:
            try:
                adapter.rollback(
                    environment, module_name, module, str(previous), context
                )
            except Exception as rollback_exc:
                try:
                    current_live = adapter.inspect(
                        environment, module_name, module, context
                    )
                except Exception:
                    current_live = None
                state.write(
                    environment,
                    module_name,
                    {
                        "environment": environment,
                        "module": module_name,
                        "current": current_live,
                        "previous": previous,
                        "status": "rollback-failed",
                        "target_deployment": "failed",
                        "rollback_attempted": True,
                        "rollback_result": "failed",
                        "error": str(exc),
                        "rollback_error": str(rollback_exc),
                        "started_at": started_at,
                    },
                )
                raise ReleaseError(
                    f"deployment failed and rollback failed: {module_name}"
                ) from exc
            try:
                current_live = adapter.inspect(
                    environment, module_name, module, context
                ) or previous
            except Exception:
                current_live = previous
            state.write(
                environment,
                module_name,
                {
                    "environment": environment,
                    "module": module_name,
                    "current": current_live,
                    "previous": artifact,
                    "status": "rolled-back",
                    "target_deployment": "failed",
                    "rollback_attempted": True,
                    "rollback_result": "succeeded",
                    "error": str(exc),
                    "started_at": started_at,
                },
            )
            raise ReleaseError(f"deployment failed and rolled back: {module_name}") from exc
        try:
            current_live = adapter.inspect(
                environment, module_name, module, context
            ) or previous
        except Exception:
            current_live = previous
        state.write(
            environment,
            module_name,
            {
                "environment": environment,
                "module": module_name,
                "current": current_live,
                "previous": None,
                "status": "failed",
                "target_deployment": "failed",
                "rollback_attempted": False,
                "error": str(exc),
                "started_at": started_at,
            },
        )
        raise ReleaseError(str(exc)) from exc
    result = {
        "environment": environment,
        "module": module_name,
        "current": artifact,
        "previous": previous,
        "status": "deployed",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "observed": observed,
    }
    state.write(environment, module_name, result)
    return result


def rollback_module(
    catalog: Mapping[str, Mapping[str, Any]],
    *,
    environment: str,
    module_name: str,
    confirm_prod: bool,
    state_root: StateBackend,
    adapters: Mapping[str, FunctionAdapter],
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state_backend = _backend(state_root)
    state = state_backend.read(environment, module_name)
    previous = state.get("previous")
    if environment == "prod" and not confirm_prod:
        raise ReleaseError("production rollback requires --confirm-prod")
    if not isinstance(previous, str):
        raise ReleaseError("module has no previous identity")
    module = catalog.get(module_name)
    if module is None:
        raise ReleaseError(f"unknown module: {module_name}")
    adapter = adapters.get(str(module["adapter"]))
    if adapter is None:
        raise ReleaseError("module rollback adapter is unavailable")
    rollback_context = dict(context or {})
    rollback_context["desired_artifact"] = previous
    adapter.rollback(
        environment,
        module_name,
        module,
        previous,
        rollback_context,
    )
    observed = dict(adapter.status(
        environment, module_name, module, rollback_context
    ))
    result = {
        "environment": environment,
        "module": module_name,
        "current": previous,
        "previous": state.get("current"),
        "status": "rolled-back",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "observed": observed,
    }
    state_backend.write(environment, module_name, result)
    return result


def _remote_shell(host: str, script: str) -> CommandResult:
    return _run(
        _ssh_command(host, "bash -s"),
        input=script,
    )


def _cloudflare_request(
    url: str, token: str, *, method: str = "GET"
) -> Mapping[str, Any]:
    request = urllib.request.Request(
        url,
        data=b"{}" if method == "POST" else None,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ReleaseError("Cloudflare Pages API request failed") from exc
    if not isinstance(value, Mapping) or value.get("success") is not True:
        raise ReleaseError("Cloudflare Pages API request failed")
    return value


def _exact_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, str) and DIGEST_REF_RE.fullmatch(value):
        refs.append(value)
    elif isinstance(value, Mapping):
        for nested in value.values():
            refs.extend(_exact_refs(nested))
    elif isinstance(value, list):
        for nested in value:
            refs.extend(_exact_refs(nested))
    return refs


class SystemAdapters:
    def __init__(self, catalog: Mapping[str, Mapping[str, Any]]) -> None:
        self.catalog = catalog

    def mapping(self) -> dict[str, FunctionAdapter]:
        shared = FunctionAdapter(
            inspect=self.inspect,
            deploy=self.deploy,
            rollback=self.rollback,
            status=self.status,
        )
        return {
            name: shared
            for name in (
                "compose-image",
                "pages",
                "gpu",
                "config-contract",
                "compose-contract",
                "database-migration",
            )
        }

    def inspect(
        self,
        environment: str,
        _name: str,
        module: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> str | None:
        adapter = module["adapter"]
        if adapter in {"config-contract", "compose-contract"}:
            host = str(context.get("remote_host") or ENVIRONMENTS[environment]["host"])
            root = f"/var/lib/allbot/module-contracts/{environment}/{_name}"
            result = _run(
                _ssh_command(host, f"readlink -f {root}/current")
            )
            identity = Path(result.stdout.strip()).name
            match = re.fullmatch(r"sha256-([0-9a-f]{64})", identity)
            if result.returncode or not match:
                return None
            repository = str(module["repository"])
            return f"ghcr.io/giraffu/{repository}@sha256:{match.group(1)}"
        if adapter == "pages":
            account_id, token = self._pages_credentials(context)
            if not account_id or not token:
                return None
            project = PAGES_PROJECTS[environment]
            value = _cloudflare_request(
                (
                    "https://api.cloudflare.com/client/v4/accounts/"
                    f"{account_id}/pages/projects/{project}/deployments"
                    + (
                        "?env=production&per_page=1"
                        if environment == "prod"
                        else "?env=preview&per_page=1"
                    )
                ),
                token,
            )
            try:
                deployment_id = value["result"][0]["id"]
            except (IndexError, KeyError, TypeError):
                return None
            return f"pages://{project}/{deployment_id}"
        if adapter == "gpu":
            operator = str(context.get("operator") or "")
            slot = str(context.get("slot") or "")
            if operator not in {"runpod", "lan"} or not slot:
                return None
            command = (
                [
                    "bash",
                    str(ROOT / "scripts" / "runpod_prod_ops.sh"),
                    "status",
                    "--profile",
                    _name,
                    "--slot",
                    slot,
                ]
                if operator == "runpod"
                else [
                    "python",
                    str(ROOT / "scripts" / "lan_aio_fleet_prod_ops.py"),
                    "status",
                    "--slot",
                    slot,
                ]
            )
            result = _run(command, cwd=ROOT)
            if result.returncode:
                return None
            try:
                refs = _exact_refs(json.loads(result.stdout))
            except json.JSONDecodeError:
                return None
            repository = str(module.get("image") or "")
            return next(
                (ref for ref in refs if repository and repository in ref),
                refs[0] if refs else None,
            )
        if adapter != "compose-image":
            return None
        host = str(context.get("remote_host") or ENVIRONMENTS[environment]["host"])
        project = ENVIRONMENTS[environment]["project"]
        service = str(module["service"])
        command = (
            "id=$(docker ps -aq "
            f"--filter label=com.docker.compose.project={project} "
            f"--filter label=com.docker.compose.service={service} | head -n1); "
            "[ -n \"$id\" ] || exit 1; "
            "image_id=$(docker inspect --format '{{.Image}}' \"$id\"); "
            "docker image inspect --format '{{index .RepoDigests 0}}' \"$image_id\""
        )
        result = _run(_ssh_command(host, command))
        return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None

    def deploy(
        self,
        environment: str,
        name: str,
        module: Mapping[str, Any],
        artifact: str,
        context: Mapping[str, Any],
    ) -> None:
        adapter = str(module["adapter"])
        if adapter == "compose-image":
            self._deploy_compose(environment, module, artifact, context)
        elif adapter in {"config-contract", "compose-contract"}:
            self._deploy_contract(environment, name, artifact, context)
        elif adapter == "database-migration":
            self._deploy_migration(environment, artifact, context)
        elif adapter == "gpu":
            self._deploy_gpu(environment, name, artifact, context)
        elif adapter == "pages":
            self._deploy_pages(environment, artifact, context)
        else:
            raise ReleaseError(f"unsupported deployment adapter: {adapter}")

    def rollback(
        self,
        environment: str,
        name: str,
        module: Mapping[str, Any],
        previous: str,
        context: Mapping[str, Any],
    ) -> None:
        if module["adapter"] == "pages" and previous.startswith("pages://"):
            self._rollback_pages(environment, previous, context)
            return
        self.deploy(environment, name, module, previous, context)

    def status(
        self,
        environment: str,
        _name: str,
        module: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if module["adapter"] == "pages":
            url = (
                "https://web.aivison.it.com"
                if environment == "prod"
                else "https://web-cf-test.aivison.it.com"
            )
            result = _run(["curl", "-fsS", "--max-time", "20", url])
            if result.returncode:
                raise ReleaseError("Pages target is not accessible")
            return {"url": url, "accessible": True}
        if module["adapter"] in {"config-contract", "compose-contract"}:
            active = self.inspect(environment, _name, module, context)
            desired = context.get("desired_artifact")
            if desired and active != desired:
                raise ReleaseError("contract active identity did not switch")
            return {"active_identity": active}
        if module["adapter"] != "compose-image":
            return {"result": "adapter-completed"}
        host = str(context.get("remote_host") or ENVIRONMENTS[environment]["host"])
        project = ENVIRONMENTS[environment]["project"]
        service = str(module["service"])
        command = (
            "id=$(docker ps -q "
            f"--filter label=com.docker.compose.project={project} "
            f"--filter label=com.docker.compose.service={service} | head -n1); "
            "[ -n \"$id\" ] || exit 1; "
            "docker inspect --format "
            "'{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \"$id\""
        )
        result = _run(_ssh_command(host, command))
        health = result.stdout.strip()
        if result.returncode or health not in {"healthy", "running"}:
            raise ReleaseError(f"target service is unhealthy: {service}")
        return {"health": health}

    def _deploy_compose(
        self,
        environment: str,
        module: Mapping[str, Any],
        artifact: str,
        context: Mapping[str, Any],
    ) -> None:
        target = ENVIRONMENTS[environment]
        host = str(context.get("remote_host") or target["host"])
        root = str(context.get("remote_root") or "/home/deploy/APP/All_bot-release/repo")
        service = str(module["service"])
        image_env = str(module["image_env"])
        profile = str(module.get("profile", ""))
        runtime_root = f"/var/lib/allbot/module-releases/{environment}"
        script = f"""set -euo pipefail
docker pull {artifact}
install -d -m 700 {runtime_root}
runtime={runtime_root}/runtime.env
if [ ! -f "$runtime" ]; then
  sha=$(python3 -c 'import json; print(json.load(open("/var/lib/allbot/deployments/{environment}/control-plane/current.json"))["git_sha"])' 2>/dev/null || true)
  old=/var/lib/allbot/releases/control-plane/$sha/release.env
  [ -f "$old" ] && cp "$old" "$runtime" || touch "$runtime"
  chmod 600 "$runtime"
fi
candidate="$runtime.new"
grep -v '^{image_env}=' "$runtime" > "$candidate" || true
printf '%s=%s\\n' {image_env} {artifact} >> "$candidate"
grep -q '^ALLBOT_RELEASE_SHA=' "$candidate" || printf 'ALLBOT_RELEASE_SHA=module-release\\n' >> "$candidate"
grep -q '^ALLBOT_SERVICE_ENV_ROOT=' "$candidate" || printf 'ALLBOT_SERVICE_ENV_ROOT=/var/lib/allbot/config/{environment}/current\\n' >> "$candidate"
compose=(docker compose --env-file {target["env_file"]} --env-file "$candidate" -p {target["project"]} -f {root}/deploy/docker-compose-cloud-base.yml -f {root}/{target["overlay"]})
{f'compose+=(--profile {profile})' if profile else ':'}
"${{compose[@]}}" up -d --no-deps --wait --wait-timeout 120 {service}
mv "$candidate" "$runtime"
"""
        result = _remote_shell(host, script)
        if result.returncode:
            raise ReleaseError(f"target service replacement failed: {service}")

    def _deploy_contract(
        self,
        environment: str,
        name: str,
        artifact: str,
        context: Mapping[str, Any],
    ) -> None:
        host = str(context.get("remote_host") or ENVIRONMENTS[environment]["host"])
        with tempfile.TemporaryDirectory(prefix="allbot-contract-") as directory:
            output = Path(directory)
            result = _run(["oras", "pull", artifact, "-o", str(output)])
            if result.returncode:
                raise ReleaseError(f"unable to pull {name}")
            archive = _find_single_module_archive(output, name)
            encoded = base64.b64encode(archive.read_bytes()).decode("ascii")
            digest = artifact.rsplit("@", 1)[1].replace(":", "-")
            root = f"/var/lib/allbot/module-contracts/{environment}/{name}"
            script = f"""set -euo pipefail
install -d -m 700 {root}/{digest}
printf %s {encoded} | base64 -d | tar -xzf - -C {root}/{digest}
ln -sfn {root}/{digest} {root}/current.new
mv -Tf {root}/current.new {root}/current
"""
            result = _remote_shell(host, script)
            if result.returncode:
                raise ReleaseError(f"failed to activate {name}")

    def _deploy_migration(
        self,
        environment: str,
        artifact: str,
        context: Mapping[str, Any],
    ) -> None:
        target = ENVIRONMENTS[environment]
        host = str(context.get("remote_host") or target["host"])
        network = (
            f"--network {target['project']}_default "
            if environment == "test"
            else ""
        )
        command = (
            f"docker pull {artifact} && "
            f"docker run --rm {network}--env-file {target['env_file']} "
            f"{artifact} upgrade head"
        )
        result = _run(_ssh_command(host, command))
        if result.returncode:
            raise ReleaseError("database migration failed")

    def _deploy_gpu(
        self,
        environment: str,
        name: str,
        artifact: str,
        context: Mapping[str, Any],
    ) -> None:
        operator = str(context.get("operator") or "")
        slot = str(context.get("slot") or "")
        if operator not in {"runpod", "lan"} or not slot:
            raise ReleaseError("GPU deployment requires --operator and --slot")
        command = [
            str(ROOT / "scripts" / "gpu_release_rollout.py"),
            "--profile",
            name,
            "--artifact",
            artifact,
            "--operator",
            operator,
            "--slot",
            slot,
            "--execute",
        ]
        result = _run(command, cwd=ROOT)
        if result.returncode:
            raise ReleaseError("GPU single-slot rollout failed")

    def _deploy_pages(
        self,
        environment: str,
        artifact: str,
        context: Mapping[str, Any],
    ) -> None:
        release_sha = _artifact_revision(artifact)
        runtime_values, runtime_revision = load_web_runtime_config(
            Path(
                str(
                    context.get("web_runtime_config")
                    or ROOT / "frontend" / "runtime-config.yml"
                )
            ),
            environment,
        )
        runtime_script = render_web_runtime_config_script(
            runtime_values,
            git_sha=release_sha,
            config_revision=runtime_revision,
        )
        token_file = Path(
            str(
                context.get("cloudflare_token_file")
                or Path.home() / ".config" / "allbot" / "cloudflare-pages.token"
            )
        )
        if not token_file.is_file():
            raise ReleaseError("Cloudflare Pages token file is unavailable")
        if token_file.stat().st_mode & 0o077:
            raise ReleaseError("Cloudflare Pages token file permissions must be 600")
        with tempfile.TemporaryDirectory(prefix="allbot-pages-") as directory:
            output = Path(directory)
            if _run(["oras", "pull", artifact, "-o", str(output)]).returncode:
                raise ReleaseError("unable to pull Public Web artifact")
            archive = _find_single_module_archive(output, "Public Web")
            dist_root = output / "dist-root"
            dist_root.mkdir()
            if _run(["tar", "-xzf", str(archive), "-C", str(dist_root)]).returncode:
                raise ReleaseError("unable to extract Public Web artifact")
            dist = dist_root / "dist"
            if not (dist / "index.html").is_file():
                raise ReleaseError("Public Web artifact has no dist/index.html")
            (dist / "allbot-runtime-config.js").write_text(
                runtime_script,
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["CLOUDFLARE_API_TOKEN"] = token_file.read_text(
                encoding="utf-8"
            ).strip()
            if not env["CLOUDFLARE_API_TOKEN"]:
                raise ReleaseError("Cloudflare Pages token file is empty")
            installed = _run(["npm", "ci"], cwd=ROOT / "frontend")
            if installed.returncode:
                raise ReleaseError("unable to install pinned Wrangler")
            result = subprocess.run(
                [
                    "npx",
                    "--no-install",
                    "wrangler",
                    "pages",
                    "deploy",
                    str(dist),
                    "--project-name",
                    PAGES_PROJECTS[environment],
                    "--branch",
                    "main" if environment == "prod" else "test",
                    "--commit-hash",
                    release_sha,
                ],
                text=True,
                capture_output=True,
                check=False,
                env=env,
                cwd=ROOT / "frontend",
            )
            if result.returncode:
                raise ReleaseError("Cloudflare Pages deployment failed")
            canonical_url = (
                f"{PAGES_URLS[environment]}/allbot-runtime-config.js"
                f"?release_sha={release_sha}"
            )
            runtime_switched = False
            for _attempt in range(12):
                observed = _run(
                    ["curl", "-fsS", "--max-time", "15", canonical_url]
                )
                if (
                    observed.returncode == 0
                    and observed.stdout.strip() == runtime_script.strip()
                ):
                    runtime_switched = True
                    break
                time.sleep(5)
            if not runtime_switched:
                raise ReleaseError(
                    "Pages canonical runtime configuration did not switch"
                )

    @staticmethod
    def _pages_credentials(
        context: Mapping[str, Any],
    ) -> tuple[str, str]:
        token_file = Path(
            str(
                context.get("cloudflare_token_file")
                or Path.home() / ".config" / "allbot" / "cloudflare-pages.token"
            )
        )
        account_id = str(
            context.get("cloudflare_account_id")
            or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        )
        if not token_file.is_file():
            return account_id, ""
        return account_id, token_file.read_text(encoding="utf-8").strip()

    def _rollback_pages(
        self,
        environment: str,
        identity: str,
        context: Mapping[str, Any],
    ) -> None:
        match = re.fullmatch(r"pages://([^/]+)/([A-Za-z0-9-]+)", identity)
        if not match or match.group(1) != PAGES_PROJECTS[environment]:
            raise ReleaseError("invalid Pages rollback identity")
        account_id, token = self._pages_credentials(context)
        if not account_id or not token:
            raise ReleaseError("Cloudflare Pages rollback credentials are unavailable")
        project, deployment_id = match.groups()
        _cloudflare_request(
            (
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{account_id}/pages/projects/{project}/deployments/"
                f"{deployment_id}/rollback"
            ),
            token,
            method="POST",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--module", action="append", required=True)
    build.add_argument("--sha", required=True)
    build.add_argument("--image-prefix", default="ghcr.io/giraffu")
    build.add_argument("--builder")
    build.add_argument("--registry-cache-prefix")
    build.add_argument(
        "--build-progress",
        choices=("auto", "plain", "tty", "rawjson"),
        default="plain",
    )
    for command in ("deploy", "rollback", "status"):
        child = subparsers.add_parser(command)
        child.add_argument("--env", choices=("test", "prod"), required=True)
        child.add_argument("--module", required=True)
        child.add_argument("--confirm-prod", action="store_true")
        child.add_argument("--remote-host")
        child.add_argument("--remote-root")
        child.add_argument(
            "--state-backend", choices=("local", "remote"), default="local"
        )
        child.add_argument(
            "--remote-state-root",
            type=Path,
            default=Path("/var/lib/allbot/module-release-state"),
        )
        child.add_argument("--operator", choices=("runpod", "lan"))
        child.add_argument("--slot")
        child.add_argument("--cloudflare-token-file")
        child.add_argument("--cloudflare-account-id")
        if command == "deploy":
            child.add_argument("--artifact", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        if args.command == "build":
            result = build_modules(
                catalog,
                args.module,
                sha=args.sha,
                image_prefix=args.image_prefix,
                builder=args.builder,
                registry_cache_prefix=args.registry_cache_prefix,
                build_progress=args.build_progress,
            )
        else:
            context = {
                key: getattr(args, key)
                for key in (
                    "remote_host",
                    "remote_root",
                    "operator",
                    "slot",
                    "cloudflare_token_file",
                    "cloudflare_account_id",
                )
                if getattr(args, key, None)
            }
            if args.state_backend == "remote":
                if not args.remote_host:
                    raise ReleaseError("--state-backend remote requires --remote-host")
                state_backend: StateBackend = RemoteStateBackend(
                    host=args.remote_host,
                    root=args.remote_state_root,
                )
            else:
                state_backend = args.state_root
            if args.command == "status":
                result = _backend(state_backend).read(args.env, args.module)
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            adapters = SystemAdapters(catalog).mapping()
            if args.command == "deploy":
                result = deploy_module(
                    catalog,
                    environment=args.env,
                    module_name=args.module,
                    artifact=args.artifact,
                    confirm_prod=args.confirm_prod,
                    state_root=state_backend,
                    adapters=adapters,
                    context=context,
                )
            else:
                result = rollback_module(
                    catalog,
                    environment=args.env,
                    module_name=args.module,
                    confirm_prod=args.confirm_prod,
                    state_root=state_backend,
                    adapters=adapters,
                    context=context,
                )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
