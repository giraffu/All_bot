from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path("remote_workers/scripts/ensure_wan22_rife_cache.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("ensure_wan22_rife_cache", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ensure_wan22_rife_cache_seeds_both_custom_node_paths(tmp_path):
    module = _load_module()
    payload = b"fake-rife49"
    module.RIFE49_SIZE_BYTES = len(payload)

    comfyui_dir = tmp_path / "ComfyUI"
    (comfyui_dir / "custom_nodes").mkdir(parents=True)
    (comfyui_dir / "main.py").write_text("", encoding="utf-8")
    model_dir = comfyui_dir / "models"
    source = model_dir / "upscale_models" / "rife49.pth"
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)

    result = module.ensure_cache(
        comfyui_dir=comfyui_dir,
        model_target_dir=str(model_dir),
        expected_sha256="",
    )

    assert result["ok"] is True
    fill_nodes_target = (
        comfyui_dir
        / "custom_nodes"
        / "ComfyUI_Fill-Nodes"
        / "nodes"
        / "cache"
        / "rife_models"
        / "rife49.pth"
    )
    frame_interpolation_target = (
        comfyui_dir
        / "custom_nodes"
        / "ComfyUI-Frame-Interpolation"
        / "ckpts"
        / "rife"
        / "rife49.pth"
    )
    assert fill_nodes_target.read_bytes() == payload
    assert frame_interpolation_target.read_bytes() == payload


def test_ensure_wan22_rife_cache_is_noop_for_non_wan22_env(monkeypatch):
    module = _load_module()

    monkeypatch.delenv("RUNPOD_REQUIRE_WAN22_RIFE_CACHE", raising=False)
    monkeypatch.setenv("RUNPOD_TASK_TYPE", "ltx_video")
    monkeypatch.setenv("POOL_RUNTIME_PROFILE", "ltx_video")
    monkeypatch.setenv("SUPPORTED_TASK_TYPES", "ltx_video")

    assert module._needs_wan22_rife() is False
