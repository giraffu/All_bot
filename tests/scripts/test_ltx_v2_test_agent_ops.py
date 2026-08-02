import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ltx_v2_test_agent_ops.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ltx_v2_test_agent_ops", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_image_rejects_mutable_tags():
    module = _load_module()

    with pytest.raises(SystemExit, match="exact sha256 digest"):
        module._exact_image("ghcr.io/giraffu/allbot-worker-agent:latest")


def test_exact_image_accepts_a_digest():
    module = _load_module()
    image = "ghcr.io/giraffu/allbot-worker-agent@sha256:" + "a" * 64

    assert module._exact_image(image) == image
