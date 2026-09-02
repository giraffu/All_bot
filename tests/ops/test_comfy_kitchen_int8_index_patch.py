from pathlib import Path

import pytest

from workers.runpod_profiles.minimax_h3.patch_comfy_kitchen_int8_offsets import (
    NEW_AM,
    NEW_BN,
    OLD_AM,
    OLD_BN,
    patch_quantization_file,
)


BUGGY_KERNEL_PAIR = """\
    offs_am = (pid_m * block_m + tl.arange(0, block_m)) % m
    offs_bn = (pid_n * block_n + tl.arange(0, block_n)) % n
"""


def test_patch_promotes_both_int8_gemm_output_offsets_to_int64(tmp_path: Path):
    quantization = tmp_path / "quantization.py"
    quantization.write_text(
        f"first:\n{BUGGY_KERNEL_PAIR}\nsecond:\n{BUGGY_KERNEL_PAIR}",
        encoding="utf-8",
    )

    result = patch_quantization_file(quantization)

    patched = quantization.read_text(encoding="utf-8")
    assert result == "patched"
    assert patched.count(".to(tl.int64)") == 4
    assert OLD_AM not in [line.strip() for line in patched.splitlines()]
    assert OLD_BN not in [line.strip() for line in patched.splitlines()]


def test_patch_is_idempotent_after_the_pinned_wheel_is_fixed(tmp_path: Path):
    quantization = tmp_path / "quantization.py"
    quantization.write_text(
        f"    {NEW_AM}\n    {NEW_BN}\n" * 2,
        encoding="utf-8",
    )

    assert patch_quantization_file(quantization) == "already_patched"


def test_patch_rejects_unexpected_comfy_kitchen_source(tmp_path: Path):
    quantization = tmp_path / "quantization.py"
    quantization.write_text(BUGGY_KERNEL_PAIR, encoding="utf-8")

    with pytest.raises(RuntimeError, match="expected exactly two INT8 GEMM kernels"):
        patch_quantization_file(quantization)
