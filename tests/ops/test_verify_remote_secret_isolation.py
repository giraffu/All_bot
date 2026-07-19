import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    path = ROOT / "scripts" / "verify_remote_secret_isolation.py"
    spec = importlib.util.spec_from_file_location("verify_secret_isolation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reused_keys_reports_names_only():
    module = _load_module()
    assert module.reused_keys(
        {"API_TOKEN": "same-hmac", "AUTH_TOKEN": "test-hmac"},
        {"API_TOKEN": "same-hmac", "AUTH_TOKEN": "prod-hmac"},
    ) == ["API_TOKEN"]


def test_reused_keys_rejects_incomplete_challenge():
    module = _load_module()
    with pytest.raises(module.IsolationError, match="key sets"):
        module.reused_keys({"API_TOKEN": "a"}, {"AUTH_TOKEN": "b"})
