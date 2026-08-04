import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _default_port(compose_path: Path, variable: str) -> int:
    compose = compose_path.read_text(encoding="utf-8")
    match = re.search(rf"\$\{{{variable}:-([0-9]+)\}}", compose)
    assert match is not None, f"missing default for {variable}"
    return int(match.group(1))


def test_local_analytics_and_clarity_have_distinct_default_lan_ports() -> None:
    analytics_port = _default_port(
        REPOSITORY_ROOT / "local_analytics_platform/docker-compose.yml",
        "LOCAL_ANALYTICS_PORT",
    )
    clarity_port = _default_port(
        REPOSITORY_ROOT / "media_enhance_platform/docker-compose.yml",
        "CLARITY_WEB_PORT",
    )

    assert analytics_port == 8098
    assert clarity_port == 8095
    assert analytics_port != clarity_port
