#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path


WAN22_RIFE_PROFILES = {
    "image_to_video",
    "video_basic",
    "wan22_aio_video",
    "wan22_video_v2",
}
DEFAULT_RIFE49_SHA256 = (
    "e55fd00f3cc184e3c65961f4bb827a9da022e78eed36b055242c0ac30000d533"
)
RIFE49_SIZE_BYTES = 21_345_274


def _csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _needs_wan22_rife() -> bool:
    if os.getenv("RUNPOD_REQUIRE_WAN22_RIFE_CACHE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    runtime_values = {
        os.getenv("RUNPOD_TASK_TYPE", ""),
        os.getenv("POOL_RUNTIME_PROFILE", ""),
    }
    runtime_values |= _csv(os.getenv("SUPPORTED_TASK_TYPES", ""))
    return bool(WAN22_RIFE_PROFILES & runtime_values)


def _resolve_comfyui_dir(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.getenv("COMFYUI_DIR"):
        candidates.append(Path(os.environ["COMFYUI_DIR"]))
    marker = Path("/opt/allbot-comfyui-dir")
    if marker.exists():
        marker_value = marker.read_text(encoding="utf-8").strip()
        if marker_value:
            candidates.append(Path(marker_value))
    candidates.extend(
        [
            Path("/workspace/ComfyUI"),
            Path("/default-comfyui-bundle/ComfyUI"),
            Path("/root/ComfyUI"),
            Path("/opt/ComfyUI"),
        ]
    )
    for candidate in candidates:
        if (candidate / "main.py").is_file():
            return candidate
    raise RuntimeError("unable to resolve ComfyUI directory for Wan22 RIFE cache")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_rife_file(path: Path, expected_sha256: str) -> bool:
    if not path.is_file() or path.stat().st_size != RIFE49_SIZE_BYTES:
        return False
    if expected_sha256 and _sha256(path) != expected_sha256:
        return False
    return True


def _target_paths(comfyui_dir: Path) -> list[Path]:
    return [
        comfyui_dir
        / "custom_nodes"
        / "ComfyUI_Fill-Nodes"
        / "nodes"
        / "cache"
        / "rife_models"
        / "rife49.pth",
        comfyui_dir
        / "custom_nodes"
        / "ComfyUI-Frame-Interpolation"
        / "ckpts"
        / "rife"
        / "rife49.pth",
    ]


def _source_candidates(comfyui_dir: Path, model_target_dir: str | None) -> list[Path]:
    candidates = _target_paths(comfyui_dir)
    if os.getenv("RUNPOD_RIFE49_SOURCE_PATH"):
        candidates.append(Path(os.environ["RUNPOD_RIFE49_SOURCE_PATH"]))
    model_roots = []
    if model_target_dir:
        model_roots.append(Path(model_target_dir))
    if os.getenv("RUNPOD_MODEL_TARGET_DIR"):
        model_roots.append(Path(os.environ["RUNPOD_MODEL_TARGET_DIR"]))
    model_roots.append(comfyui_dir / "models")
    for root in model_roots:
        candidates.extend(
            [
                root / "upscale_models" / "rife49.pth",
                root / "rife" / "rife49.pth",
                root / "rife49.pth",
            ]
        )
    return candidates


def ensure_cache(
    *,
    comfyui_dir: Path,
    model_target_dir: str | None,
    expected_sha256: str,
) -> dict[str, object]:
    targets = _target_paths(comfyui_dir)
    valid_targets = [
        path for path in targets if _valid_rife_file(path, expected_sha256)
    ]
    source = next(
        (
            path
            for path in _source_candidates(comfyui_dir, model_target_dir)
            if _valid_rife_file(path, expected_sha256)
        ),
        None,
    )
    if source is None:
        raise RuntimeError(
            "Wan22 RIFE cache is required but rife49.pth was not found in "
            "ComfyUI cache paths or model fallback paths"
        )

    copied: list[str] = []
    for target in targets:
        if _valid_rife_file(target, expected_sha256):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.chmod(0o644)
        if not _valid_rife_file(target, expected_sha256):
            raise RuntimeError(f"failed to seed valid RIFE cache at {target}")
        copied.append(str(target))

    return {
        "ok": True,
        "comfyui_dir": str(comfyui_dir),
        "source": str(source),
        "target_count": len(targets),
        "valid_before": len(valid_targets),
        "copied": copied,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensure Wan22 FL_RIFE cache is present before serving tasks"
    )
    parser.add_argument("--comfyui-dir", default="")
    parser.add_argument("--model-target-dir", default="")
    parser.add_argument(
        "--sha256",
        default=os.getenv("RUNPOD_RIFE49_SHA256", DEFAULT_RIFE49_SHA256),
    )
    args = parser.parse_args()

    if not _needs_wan22_rife():
        print("[runpod-rife-cache] skipped: current profile does not require Wan22 RIFE")
        return 0

    comfyui_dir = _resolve_comfyui_dir(args.comfyui_dir or None)
    payload = ensure_cache(
        comfyui_dir=comfyui_dir,
        model_target_dir=args.model_target_dir or None,
        expected_sha256=args.sha256,
    )
    print("[runpod-rife-cache] " + repr(payload))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[runpod-rife-cache] error: {exc}", file=sys.stderr)
        raise SystemExit(75)
