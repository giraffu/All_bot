from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops/lan_artifact_nas"


def test_nas_compose_keeps_artifact_data_on_btrfs_and_direct_link_only():
    compose = (OPS / "compose.yml").read_text(encoding="utf-8")

    assert compose.startswith("name: allbot-lan-artifact-nas\n")
    assert "${NAS_DIRECT_BIND_IP:?required}:5000:5000" in compose
    assert "${NAS_DIRECT_BIND_IP:?required}:9010:9010" in compose
    assert "192.168.1.150:5000" not in compose
    assert "192.168.1.150:9010" not in compose
    assert "${REGISTRY_DATA_PATH:-/volume1/AllBotInfra/docker-registry}" in compose
    assert "${MODEL_CACHE_DATA_PATH:-/volume1/AllBotInfra/model-cache-lan}" in compose
    assert "${REGISTRY_IMAGE:?Set an immutable registry image ID}" in compose
    assert "${MODEL_CACHE_IMAGE:?Set an immutable MinIO image ID}" in compose


def test_nfs_export_is_limited_to_the_dedicated_server_address():
    exports = (OPS / "allbot-infra.exports").read_text(encoding="utf-8")

    assert exports.count("10.250.150.1") == 1
    assert "/volume1/AllBotInfra/model-registry" in exports
    assert "rw,sync,no_subtree_check,root_squash,fsid=0" in exports
    assert "192.168." not in exports
    assert "*" not in exports


def test_main_server_proxies_preserve_existing_lan_endpoints():
    registry_socket = (OPS / "allbot-lan-registry-proxy.socket").read_text(
        encoding="utf-8"
    )
    registry_service = (OPS / "allbot-lan-registry-proxy.service").read_text(
        encoding="utf-8"
    )
    cache_socket = (OPS / "allbot-lan-model-cache-proxy.socket").read_text(
        encoding="utf-8"
    )
    cache_service = (OPS / "allbot-lan-model-cache-proxy.service").read_text(
        encoding="utf-8"
    )

    assert "ListenStream=127.0.0.1:5000" in registry_socket
    assert "ListenStream=192.168.1.115:5000" in registry_socket
    assert "systemd-socket-proxyd 10.250.150.2:5000" in registry_service
    assert "ListenStream=127.0.0.1:9010" in cache_socket
    assert "ListenStream=192.168.1.115:9010" in cache_socket
    assert "systemd-socket-proxyd 10.250.150.2:9010" in cache_service


def test_main_server_proxy_sockets_do_not_create_a_boot_ordering_cycle():
    for name in (
        "allbot-lan-registry-proxy.socket",
        "allbot-lan-model-cache-proxy.socket",
    ):
        socket = (OPS / name).read_text(encoding="utf-8")

        assert "WantedBy=sockets.target" in socket
        assert "FreeBind=true" in socket
        assert "network-online.target" not in socket


def test_preflight_defaults_to_read_only_and_requires_exact_confirmation():
    script = OPS / "preflight.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)

    dry_run = subprocess.run(
        [str(script)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    assert "read-only preflight passed" in dry_run.stdout

    rejected = subprocess.run(
        [str(script), "--execute", "--confirm", "wrong"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "exact confirmation" in rejected.stderr


def test_model_registry_snapshot_policy_does_not_snapshot_rebuildable_caches():
    snapshot = (OPS / "snapshot-model-registry.sh").read_text(encoding="utf-8")

    assert "/volume1/AllBotInfra/model-registry" in snapshot
    assert "/volume1/AllBotInfra/docker-registry" not in snapshot
    assert "/volume1/AllBotInfra/model-cache-lan" not in snapshot
    assert "readonly" in snapshot
    assert "retain" in snapshot.lower()


def test_model_registry_mount_uses_hard_nfs_over_the_direct_link():
    fstab = (OPS / "model-registry.fstab").read_text(encoding="utf-8")

    assert fstab.startswith(
        "10.250.150.2:/ "
        "/srv/allbot/model-registry nfs4 "
    )
    assert "rw,hard,_netdev,noatime" in fstab
    assert "x-systemd.automount" in fstab


def test_runbook_closes_fast_local_rollback_after_store_retirement():
    readme = (OPS / "README.md").read_text(encoding="utf-8")

    assert "Retirement closes that fast rollback path" in readme
    assert "recovery is NAS-first" in readme
    assert "runtime evidence and never Git" in readme
    assert "distinguish `Exclusive` from `Set shared`" in readme
    assert "never promise an instant local rollback" in readme


def test_migration_source_proxy_is_direct_link_only_and_separate_from_cutover():
    socket = (OPS / "allbot-model-cache-migration-source.socket").read_text(
        encoding="utf-8"
    )
    service = (OPS / "allbot-model-cache-migration-source.service").read_text(
        encoding="utf-8"
    )

    assert "ListenStream=10.250.150.1:19010" in socket
    assert "127.0.0.1:19010" not in socket
    assert "192.168.1.115" not in socket
    assert "systemd-socket-proxyd 127.0.0.1:9010" in service


def test_model_cache_mirror_is_dry_run_by_default_and_fail_closed():
    script = OPS / "mirror-model-cache.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")

    assert "mc mirror" in text
    assert "--preserve" in text
    assert "--retry" in text
    assert "--max-workers" in text
    assert "--env-file" in text
    assert '-e "MC_ACCESS_KEY=' not in text
    assert '-e "MC_SECRET_KEY=' not in text
    assert "mc diff" in text
    assert "COPY_MODEL_CACHE_TO_NAS" in text
    assert "--remove" not in text
