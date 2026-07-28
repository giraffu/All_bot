#!/usr/bin/env python3
"""Switch selected character subviews to the PornMaster BF16 checkpoint."""

from __future__ import annotations

from pathlib import Path
import sys


ANCHOR = """\
        workflow[selected_prefix + "185"]["inputs"]["text"] = prompt
"""

REPLACEMENT = """\
        workflow[selected_prefix + "185"]["inputs"]["text"] = prompt
        workflow[selected_prefix + "100"]["inputs"]["unet_name"] = (
            PORNMASTER_FLUX2_BF16_UNET_NAME
        )
"""


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit(
            "usage: install_character_runtime_overlay.py <runtime-comfy-agent-dir>"
        )
    path = Path(argv[1]) / "workflow_task_patchers.py"
    source = path.read_text(encoding="utf-8")
    if source.count(ANCHOR) != 1:
        raise RuntimeError("character BF16 patch anchor count must be exactly one")
    source = source.replace(ANCHOR, REPLACEMENT, 1)
    compile(source, str(path), "exec")
    path.write_text(source, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
