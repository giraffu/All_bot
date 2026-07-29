from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol


class ModelBuildProvider(Protocol):
    provider_name: str
    animation_ids: tuple[str, ...]
    view_types: tuple[str, ...]

    async def build(self, output_dir: Path) -> None: ...


class LocalFixtureModelBuildProvider:
    provider_name = "local_fixture"
    animation_ids = ("idle", "turntable", "photo_pose", "dance_lite")
    view_types = (
        "model_front",
        "model_back",
        "model_left",
        "model_right",
    )

    def __init__(self, *, blender_binary: str, script_path: Path):
        self.blender_binary = blender_binary
        self.script_path = script_path

    async def build(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            self.blender_binary,
            "--background",
            "--python",
            str(self.script_path),
            "--",
            "--output",
            str(output_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode:
            detail = (stderr or stdout).decode("utf-8", errors="replace")[-4000:]
            raise RuntimeError(f"FIXTURE_BUILD_FAILED: {detail}")
