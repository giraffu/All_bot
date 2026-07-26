from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_is_lan_bound_and_has_no_docker_socket():
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert "${RESOURCE_MANAGER_BIND_IP:-192.168.1.115}" in compose
    assert "network_mode: host" in compose
    assert "ports:" not in compose
    assert "/var/run/docker.sock" not in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose


def test_container_mounts_only_lan_gpu_identity():
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert "allbot_lan_gpu_ops_20260608_ed25519" in compose
    assert "allbot_do_sgp1" not in compose
