from pathlib import Path

import pytest

from src.avatar_miniapp.providers import LocalFixtureModelBuildProvider


def test_fixture_provider_exposes_stable_capabilities(tmp_path: Path):
    provider = LocalFixtureModelBuildProvider(
        blender_binary="blender",
        script_path=tmp_path / "fixture.py",
    )

    assert provider.provider_name == "local_fixture"
    assert provider.animation_ids == (
        "idle",
        "turntable",
        "photo_pose",
        "dance_lite",
    )
    assert provider.view_types == (
        "model_front",
        "model_back",
        "model_left",
        "model_right",
    )


@pytest.mark.asyncio
async def test_fixture_provider_invokes_blender_with_fixed_script(
    monkeypatch, tmp_path: Path
):
    script = tmp_path / "fixture.py"
    script.write_text("# fixture", encoding="utf-8")
    provider = LocalFixtureModelBuildProvider(
        blender_binary="/usr/bin/blender",
        script_path=script,
    )
    calls: list[tuple[str, ...]] = []

    async def fake_run(*args, **kwargs):
        calls.append(tuple(str(arg) for arg in args))

        class Result:
            returncode = 0

            async def communicate(self):
                return b"", b""

        return Result()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)
    output = tmp_path / "output"

    await provider.build(output)

    assert calls == [
        (
            "/usr/bin/blender",
            "--background",
            "--python",
            str(script),
            "--",
            "--output",
            str(output),
        )
    ]
