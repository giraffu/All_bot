import hashlib
from pathlib import Path

import pytest

from workers.runpod_profiles.minimax_h3 import download_pinned_file as module


def test_download_pinned_file_assembles_ordered_ranges(monkeypatch, tmp_path):
    payload = b"minimax-h3-pinned-wheel" * 100

    def fake_download_range(_url: str, start: int, end: int, target: Path) -> None:
        target.write_bytes(payload[start : end + 1])

    monkeypatch.setattr(module, "_download_range", fake_download_range)
    output = tmp_path / "wheel.whl"

    module.download_pinned_file(
        url="https://pypi.nvidia.com/nvidia-vfx/wheel.whl",
        output=output,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        parallelism=7,
    )

    assert output.read_bytes() == payload


def test_download_pinned_file_rejects_hash_mismatch(monkeypatch, tmp_path):
    payload = b"corrupt"

    monkeypatch.setattr(
        module,
        "_download_range",
        lambda _url, start, end, target: target.write_bytes(payload[start : end + 1]),
    )
    output = tmp_path / "wheel.whl"

    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        module.download_pinned_file(
            url="https://pypi.nvidia.com/nvidia-vfx/wheel.whl",
            output=output,
            size_bytes=len(payload),
            sha256="0" * 64,
            parallelism=3,
        )

    assert not output.exists()
