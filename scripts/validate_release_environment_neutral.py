#!/usr/bin/env python3
"""Fail closed when release artifacts bake test/prod configuration or secrets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
from typing import Iterable, Mapping, Sequence


REQUIRED_CONTEXT_EXCLUDES = {
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "*.key",
    ".ssh/",
}
ENV_SPECIFIC_KEY = re.compile(
    r"(?:^ALLBOT_ENV$|DATABASE_URL|REDIS_URL|TOKEN|SECRET|PASSWORD|BUCKET|"
    r"MINIO_|API_BASE|PUBLIC_URL|EXTERNAL_DOMAIN|BOT_USERNAME|VITE_)",
    re.IGNORECASE,
)
DOCKER_COPY_ENV = re.compile(
    r"^\s*(?:COPY|ADD)\s+(?:--\S+\s+)*[^#\n]*\.env(?:\s|$)", re.IGNORECASE
)
DOCKER_VARIABLE = re.compile(
    r"^\s*(?:ARG|ENV)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE
)
DOCKER_ASSIGNMENT = re.compile(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=")
PUBLIC_SENTINELS = (
    "api-cf-test.aivison.it.com",
    "api.aivison.it.com",
    "r2-test.aivison.it.com",
    "assets.aivison.it.com",
    "testAIvison_bot",
    "AIVision1111_bot",
)
NON_RUNNABLE_IDENTITY_ARTIFACTS = {
    "dashboard-frontend",
    "python-media-runtime-base",
    "python-runtime-base",
    "python-worker-base",
    "qqcc-config-frontend",
}
RUNTIME_SOURCE_FILES = (
    "config.py",
    "backend/app/config.py",
    "src/bot_main.py",
    "src/runtime_environment.py",
    "src/core/auth_core.py",
    "src/core/auth_core_telegram_validation.py",
    "src/core/auth_core_telegram_verify.py",
    "src/web_api/core/config.py",
    "dashboard/backend/auth.py",
    "dashboard/backend/qqcc_config_auth.py",
    "paid_group_guard_bot/config.py",
    "src/services/order_v2_service.py",
    "src/services/affiliate_redeem_rules.py",
)
FORBIDDEN_RUNTIME_SOURCE = {
    "automatic dotenv loading": re.compile(r"\bload_dotenv\s*\("),
    "dotenv fallback": re.compile(r"\bdotenv_values\s*\("),
    "test-key fallback": re.compile(r"os\.(?:getenv|environ\.get)\([^\n]*_TEST"),
    "known placeholder secret": re.compile(
        r"your-super-secret|change-in-production|your_secure_token_here|"
        r"qqcc-config-dev-secret",
        re.IGNORECASE,
    ),
}


class NeutralityError(RuntimeError):
    """A build or artifact contains environment-owned configuration."""


def _read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NeutralityError(f"{label} is invalid") from exc
    if not isinstance(value, dict):
        raise NeutralityError(f"{label} must be an object")
    return value


def validate_build_context(repo: Path) -> None:
    dockerignore = repo / ".dockerignore"
    try:
        rules = {
            line.strip()
            for line in dockerignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    except OSError as exc:
        raise NeutralityError(".dockerignore is unavailable") from exc
    missing = sorted(REQUIRED_CONTEXT_EXCLUDES - rules)
    if missing:
        raise NeutralityError(
            "build context does not exclude environment material: " + ", ".join(missing)
        )


def validate_dockerfiles(repo: Path) -> None:
    for path in sorted((repo / "deploy" / "docker").glob("Dockerfile*")):
        text = path.read_text(encoding="utf-8")
        if DOCKER_COPY_ENV.search(text):
            raise NeutralityError(f"{path.name} copies an environment file")
        for line in text.replace("\\\n", " ").splitlines():
            match = DOCKER_VARIABLE.match(line)
            keys = [match.group(1)] if match else []
            if line.lstrip().upper().startswith("ENV "):
                keys.extend(DOCKER_ASSIGNMENT.findall(line))
            for key in dict.fromkeys(keys):
                if ENV_SPECIFIC_KEY.search(key):
                    raise NeutralityError(
                        f"{path.name} declares environment-owned build key {key}"
                    )


def validate_runtime_sources(repo: Path) -> None:
    for relative in RUNTIME_SOURCE_FILES:
        path = repo / relative
        if not path.is_file():
            raise NeutralityError(f"runtime source is unavailable: {relative}")
        text = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN_RUNTIME_SOURCE.items():
            if pattern.search(text):
                raise NeutralityError(f"{relative} contains {label}")


def validate_public_web_sources(repo: Path, *, dist: Path | None = None) -> None:
    frontend = repo / "frontend"
    index = (frontend / "index.html").read_text(encoding="utf-8")
    if "/allbot-runtime-config.js" not in index:
        raise NeutralityError("public Web does not load runtime configuration")
    for path in sorted((frontend / "src").rglob("*")):
        if path.is_file() and path.suffix in {".ts", ".tsx", ".js", ".vue"}:
            text = path.read_text(encoding="utf-8")
            if "import.meta.env.VITE_" in text:
                raise NeutralityError(
                    f"{path.relative_to(repo)} uses Vite build-time config"
                )
    runtime = _read_json(frontend / "runtime-config.yml", "Web runtime config")
    test = runtime.get("test")
    prod = runtime.get("prod")
    if not isinstance(test, Mapping) or not isinstance(prod, Mapping) or test == prod:
        raise NeutralityError(
            "Web test/prod runtime configurations are not independent"
        )
    if set(test) != set(prod):
        raise NeutralityError("Web test/prod runtime configuration keys differ")
    if dist is not None:
        if not dist.is_dir():
            raise NeutralityError("public Web dist is unavailable")
        for path in dist.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if any(value in text for value in PUBLIC_SENTINELS):
                raise NeutralityError(
                    f"public Web dist bakes an environment-specific sentinel: {path.name}"
                )


def _release_images(
    index_path: Path,
    *,
    only_source_sha: str | None = None,
) -> Iterable[tuple[str, str]]:
    index = _read_json(index_path, "release index")
    for relative in index.get("manifests", {}).values():
        manifest = _read_json(index_path.parent / str(relative), "release manifest")
        for name, artifact in manifest.get("artifacts", {}).items():
            if isinstance(artifact, Mapping) and artifact.get("kind") == "image":
                if (
                    only_source_sha is not None
                    and artifact.get("source_sha") != only_source_sha
                ):
                    continue
                ref = artifact.get("ref")
                if isinstance(ref, str):
                    yield str(name), ref


def _release_image_artifacts(
    index_path: Path,
    *,
    only_source_sha: str | None = None,
) -> Iterable[tuple[str, str, str]]:
    index = _read_json(index_path, "release index")
    for relative in index.get("manifests", {}).values():
        manifest = _read_json(index_path.parent / str(relative), "release manifest")
        track = str(manifest.get("track", ""))
        for name, artifact in manifest.get("artifacts", {}).items():
            if not isinstance(artifact, Mapping) or artifact.get("kind") != "image":
                continue
            if only_source_sha is not None and artifact.get("source_sha") != only_source_sha:
                continue
            ref = artifact.get("ref")
            if isinstance(ref, str):
                yield str(name), ref, track


def _release_image_refs(index_path: Path) -> Iterable[str]:
    for _, ref in _release_images(index_path):
        yield ref


def _requires_runtime_identity(artifact_name: str, *, track: str = "") -> bool:
    return (
        track != "gpu-execution"
        and artifact_name not in NON_RUNNABLE_IDENTITY_ARTIFACTS
    )


def validate_image_config(
    index_path: Path,
    *,
    only_source_sha: str | None = None,
) -> None:
    if only_source_sha is not None:
        index = _read_json(index_path, "release index")
        if index.get("source_sha") != only_source_sha or not re.fullmatch(
            r"[0-9a-f]{40}", only_source_sha
        ):
            raise NeutralityError(
                "image scan source SHA does not match the release index"
            )
    for artifact_name, ref, track in sorted(
        set(_release_image_artifacts(index_path, only_source_sha=only_source_sha))
    ):
        pulled = subprocess.run(
            ["docker", "pull", ref],
            text=True,
            capture_output=True,
            check=False,
        )
        if pulled.returncode:
            raise NeutralityError(
                "release image is unavailable for neutrality inspection"
            )
        result = subprocess.run(
            ["docker", "image", "inspect", ref],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise NeutralityError(
                "release image is unavailable for neutrality inspection"
            )
        try:
            document = json.loads(result.stdout)
            env = document[0]["Config"].get("Env") or []
        except (json.JSONDecodeError, IndexError, KeyError, TypeError) as exc:
            raise NeutralityError("release image config is invalid") from exc
        for entry in env:
            key = str(entry).partition("=")[0]
            if ENV_SPECIFIC_KEY.search(key):
                raise NeutralityError(
                    f"release image Config.Env contains environment-owned key {key}"
                )
        _validate_image_filesystem(ref)
        if _requires_runtime_identity(artifact_name, track=track):
            _validate_image_runtime_identity(ref)


def _validate_image_filesystem(ref: str) -> None:
    created = subprocess.run(
        ["docker", "create", ref], text=True, capture_output=True, check=False
    )
    if created.returncode or not created.stdout.strip():
        raise NeutralityError("release image filesystem is unavailable for inspection")
    container_id = created.stdout.strip()
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
            exported = subprocess.run(
                ["docker", "export", "-o", archive.name, container_id],
                text=True,
                capture_output=True,
                check=False,
            )
            if exported.returncode:
                raise NeutralityError(
                    "release image filesystem is unavailable for inspection"
                )
            with tarfile.open(archive.name) as files:
                forbidden = [
                    member.name
                    for member in files.getmembers()
                    if member.isfile()
                    and member.name.lstrip("/").startswith(
                        ("app/", "opt/allbot/", "usr/src/app/")
                    )
                    and (
                        Path(member.name).name.startswith(".env")
                        or Path(member.name).suffix.lower() in {".pem", ".key"}
                    )
                ]
            if forbidden:
                raise NeutralityError(
                    "release image filesystem contains environment material"
                )
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container_id],
            text=True,
            capture_output=True,
            check=False,
        )


def _validate_image_runtime_identity(ref: str) -> None:
    script = (
        "from src.runtime_environment import resolve_runtime_environment; "
        "print(':'.join(resolve_runtime_environment()))"
    )
    for environment, bot_type in (("test", "TEST"), ("prod", "PROD")):
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "python",
                "-e",
                f"ALLBOT_ENV={environment}",
                "-e",
                f"BOT_TYPE={bot_type}",
                ref,
                "-c",
                script,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode or result.stdout.strip() != f"{environment}:{bot_type}":
            raise NeutralityError(
                "the same release image cannot resolve both runtime environments"
            )


def validate(
    repo: Path,
    *,
    release_index: Path | None = None,
    web_dist: Path | None = None,
    only_source_sha: str | None = None,
) -> None:
    validate_build_context(repo)
    validate_dockerfiles(repo)
    validate_runtime_sources(repo)
    validate_public_web_sources(repo, dist=web_dist)
    if release_index is not None:
        validate_image_config(release_index, only_source_sha=only_source_sha)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--release-index", type=Path)
    parser.add_argument("--web-dist", type=Path)
    parser.add_argument(
        "--only-source-sha",
        help="Inspect only images first built for this exact immutable Git SHA.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validate(
            args.repo.resolve(),
            release_index=args.release_index,
            web_dist=args.web_dist,
            only_source_sha=args.only_source_sha,
        )
        print("release environment-neutrality gate passed")
        return 0
    except NeutralityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
