import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "validate_release_environment_neutral.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("release_neutrality", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checked_in_release_sources_are_environment_neutral():
    _load_module().validate(ROOT)


def test_build_context_requires_recursive_env_excludes():
    module = _load_module()

    assert {"**/.env", "**/.env.*"} <= module.REQUIRED_CONTEXT_EXCLUDES


def test_dockerfile_cannot_bake_token_or_env_file(tmp_path):
    module = _load_module()
    docker = tmp_path / "deploy" / "docker"
    docker.mkdir(parents=True)
    (docker / "Dockerfile.bad").write_text(
        "FROM scratch\nARG API_TOKEN\nCOPY .env /app/.env\n", encoding="utf-8"
    )

    with pytest.raises(module.NeutralityError):
        module.validate_dockerfiles(tmp_path)


def test_public_web_dist_cannot_bake_test_or_prod_sentinel(tmp_path):
    module = _load_module()
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/allbot-runtime-config.js"></script>', encoding="utf-8"
    )
    (frontend / "runtime-config.yml").write_text(
        '{"test":{"url":"test"},"prod":{"url":"prod"}}', encoding="utf-8"
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "app.js").write_text("https://api.aivison.it.com/api", encoding="utf-8")

    with pytest.raises(module.NeutralityError, match="sentinel"):
        module.validate_public_web_sources(tmp_path, dist=dist)


def test_runtime_source_cannot_auto_load_dotenv(tmp_path):
    module = _load_module()
    for relative in module.RUNTIME_SOURCE_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SAFE = True\n", encoding="utf-8")
    (tmp_path / "config.py").write_text("load_dotenv()\n", encoding="utf-8")

    with pytest.raises(module.NeutralityError, match="dotenv"):
        module.validate_runtime_sources(tmp_path)
