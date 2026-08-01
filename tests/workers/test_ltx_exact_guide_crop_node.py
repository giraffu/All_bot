from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


NODE_PATH = Path(
    "workers/runpod_profiles/ltx_unified/allbot_ltx_min_nodes/__init__.py"
)


def _load_node_module():
    spec = importlib.util.spec_from_file_location("allbot_ltx_min_nodes_test", NODE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeTensor:
    def __init__(self, shape: tuple[int, ...]):
        self.shape = shape

    def __getitem__(self, key):
        temporal = key[2]
        stop = temporal.stop
        assert stop is not None
        return _FakeTensor((*self.shape[:2], stop, *self.shape[3:]))


@pytest.mark.parametrize(
    ("output_frames", "target_latents"),
    [(121, 16), (241, 31), (361, 46), (481, 61)],
)
def test_exact_crop_keeps_only_requested_output_latents(
    output_frames: int, target_latents: int
):
    module = _load_node_module()
    source = _FakeTensor((1, 128, target_latents * 2, 14, 24))
    noise_mask = _FakeTensor((1, 1, target_latents * 2, 14, 24))

    (cropped,) = module.AllBotLTXCropGuideLatentsExact().crop(
        {"samples": source, "noise_mask": noise_mask, "batch_index": [0]},
        output_frames,
    )

    assert cropped["samples"].shape[2] == target_latents
    assert cropped["noise_mask"].shape[2] == target_latents
    assert cropped["batch_index"] == [0]


def test_exact_crop_rejects_latent_shorter_than_requested_output():
    module = _load_node_module()

    with pytest.raises(ValueError, match="shorter"):
        module.AllBotLTXCropGuideLatentsExact().crop(
            {"samples": _FakeTensor((1, 128, 15, 14, 24))},
            121,
        )
