from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config_loader import _load_structured_file
from .types import DEFAULT_MODEL_REGISTRY_ROOT


class ModelRegistry:
    """Content-addressed model file registry with bundle manifests."""

    def __init__(self, root: Path | str = DEFAULT_MODEL_REGISTRY_ROOT):
        self.root = Path(root)
        self.blob_root = self.root / "blobs" / "sha256"
        self.bundle_root = self.root / "bundles"

    def ensure_layout(self) -> None:
        self.blob_root.mkdir(parents=True, exist_ok=True)
        self.bundle_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sha256_file(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(chunk_size), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def blob_path(self, sha256: str) -> Path:
        return self.blob_root / sha256[:2] / sha256

    def manifest_path(self, bundle: str, version: str) -> Path:
        return self.bundle_root / bundle / version / "manifest.yml"

    def import_file(
        self,
        *,
        bundle: str,
        version: str,
        source_path: Path | str,
        relative_path: str,
        source_node: str,
        profiles: list[str],
    ) -> dict[str, Any]:
        self.ensure_layout()
        source = Path(source_path)
        sha256 = self.sha256_file(source)
        size_bytes = source.stat().st_size
        blob_path = self.blob_path(sha256)
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        if not blob_path.exists():
            try:
                os.link(source, blob_path)
            except OSError:
                shutil.copy2(source, blob_path)

        manifest = self.load_manifest(bundle, version, missing_ok=True)
        manifest.setdefault("bundle", bundle)
        manifest.setdefault("version", version)
        manifest.setdefault("profiles", profiles)
        manifest.setdefault("source", {})
        manifest["source"].setdefault("imported_from", source_node)
        files = [
            item
            for item in manifest.get("files", [])
            if item.get("relative_path") != relative_path
        ]
        files.append(
            {
                "relative_path": relative_path,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "source_path": str(source),
            }
        )
        manifest["files"] = sorted(files, key=lambda item: item["relative_path"])
        self.write_manifest(bundle, version, manifest)
        return manifest

    def load_manifest(
        self,
        bundle: str,
        version: str,
        *,
        missing_ok: bool = False,
    ) -> dict[str, Any]:
        path = self.manifest_path(bundle, version)
        if not path.exists():
            if missing_ok:
                return {}
            raise FileNotFoundError(path)
        return dict(_load_structured_file(path))

    def write_manifest(self, bundle: str, version: str, manifest: dict[str, Any]) -> Path:
        path = self.manifest_path(bundle, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import yaml  # type: ignore

            content = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
        except Exception:  # pragma: no cover - fallback only
            import json

            content = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        path.write_text(content, encoding="utf-8")
        return path

    def write_bundle_manifest(
        self,
        *,
        bundle: str,
        version: str,
        profiles: list[str],
        source: dict[str, Any],
        files: list[dict[str, Any]],
    ) -> Path:
        manifest = {
            "bundle": bundle,
            "version": version,
            "profiles": profiles,
            "source": source,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "files": sorted(files, key=lambda item: item["relative_path"]),
        }
        return self.write_manifest(bundle, version, manifest)

    def render_rsync_plan(
        self,
        *,
        bundle: str,
        version: str,
        target_host: str,
        target_model_dir: str,
    ) -> list[str]:
        manifest = self.load_manifest(bundle, version)
        commands: list[str] = []
        for item in manifest.get("files", []):
            sha256 = item["sha256"]
            relative_path = item["relative_path"].lstrip("/")
            source = self.blob_path(sha256)
            target = f"{target_host}:{target_model_dir.rstrip('/')}/{relative_path}"
            commands.append(f"rsync -avh --checksum {source} {target}")
        return commands
