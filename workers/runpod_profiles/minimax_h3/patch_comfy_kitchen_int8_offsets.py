#!/usr/bin/env python3
"""Patch comfy-kitchen 0.2.31 INT8 Triton GEMM output indexing.

The pinned upstream wheel computes flattened output offsets with int32 values.
MiniMax H3 15-second HD shapes cross 2**31 elements and wrap those offsets,
causing a CUDA illegal-memory-access fault.  Keep the fast Triton backend, but
promote the two affected kernel coordinate vectors to int64.
"""

from __future__ import annotations

import argparse
from pathlib import Path


OLD_AM = "offs_am = (pid_m * block_m + tl.arange(0, block_m)) % m"
OLD_BN = "offs_bn = (pid_n * block_n + tl.arange(0, block_n)) % n"
NEW_AM = "offs_am = ((pid_m * block_m + tl.arange(0, block_m)) % m).to(tl.int64)"
NEW_BN = "offs_bn = ((pid_n * block_n + tl.arange(0, block_n)) % n).to(tl.int64)"


def patch_quantization_file(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    stripped_lines = [line.strip() for line in source.splitlines()]
    old_counts = (stripped_lines.count(OLD_AM), stripped_lines.count(OLD_BN))
    new_counts = (stripped_lines.count(NEW_AM), stripped_lines.count(NEW_BN))

    if old_counts == (0, 0) and new_counts == (2, 2):
        return "already_patched"
    if old_counts != (2, 2) or new_counts != (0, 0):
        raise RuntimeError(
            "expected exactly two INT8 GEMM kernels in pinned comfy-kitchen source; "
            f"old_counts={old_counts}, new_counts={new_counts}"
        )

    patched = source.replace(OLD_AM, NEW_AM).replace(OLD_BN, NEW_BN)
    patched_lines = [line.strip() for line in patched.splitlines()]
    if patched_lines.count(NEW_AM) != 2 or patched_lines.count(NEW_BN) != 2:
        raise RuntimeError("failed to promote both INT8 GEMM kernel offsets to int64")
    path.write_text(patched, encoding="utf-8")
    return "patched"


def _default_target() -> Path:
    import comfy_kitchen

    return (
        Path(comfy_kitchen.__file__).resolve().parent
        / "backends"
        / "triton"
        / "quantization.py"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args()
    target = args.path or _default_target()
    outcome = patch_quantization_file(target)
    print(f"INT8 GEMM output offsets are int64: {outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
