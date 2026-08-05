import json
import os
from pathlib import Path
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[2]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content))
    path.chmod(0o755)


def _run_route_installer(
    tmp_path: Path,
    *,
    scenario: str = "safe",
    args: tuple[str, ...] = (),
    ssh_connection: str = "192.168.1.3 55163 192.168.1.115 22",
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    log = tmp_path / "network.log"
    fake_nmcli = tmp_path / "nmcli"
    fake_ip = tmp_path / "ip"
    _write_executable(
        fake_nmcli,
        r"""
        #!/usr/bin/env bash
        set -eu
        printf 'nmcli %s\n' "$*" >> "$FAKE_NETWORK_LOG"
        case "$*" in
          "-t -f NAME,DEVICE connection show --active")
            case "$FAKE_NETWORK_SCENARIO" in
              foreign-profile) printf 'netplan-eno1:eno1\n' ;;
              *) printf 'allbot-archive-direct:eno1\n有线连接 1:enx00e04c682086\n' ;;
            esac
            ;;
          "-t -f NAME connection show")
            printf 'allbot-archive-direct\nnetplan-eno1\n有线连接 1\n'
            ;;
          "-g connection.interface-name connection show allbot-archive-direct")
            printf 'eno1\n'
            ;;
          "-g connection.autoconnect connection show allbot-archive-direct")
            printf 'no\n'
            ;;
          "-g ipv4.method connection show allbot-archive-direct")
            printf 'manual\n'
            ;;
          "-g ipv4.addresses connection show allbot-archive-direct")
            printf '10.250.150.9/30\n'
            ;;
          "-g ipv4.gateway connection show allbot-archive-direct" | \
          "-g ipv4.routes connection show allbot-archive-direct")
            printf '\n'
            ;;
          "-g ipv4.never-default connection show allbot-archive-direct")
            printf 'yes\n'
            ;;
          "-g ipv6.method connection show allbot-archive-direct")
            printf 'disabled\n'
            ;;
        esac
        """,
    )
    _write_executable(
        fake_ip,
        r"""
        #!/usr/bin/env bash
        set -eu
        printf 'ip %s\n' "$*" >> "$FAKE_NETWORK_LOG"
        case "$*" in
          "-o -4 address show dev eno1")
            case "$FAKE_NETWORK_SCENARIO" in
              management-ip) printf '2: eno1 inet 192.168.1.115/24 scope global eno1\n' ;;
              ssh-on-target) printf '2: eno1 inet 10.250.150.1/30 scope global eno1\n' ;;
              *) printf '2: eno1 inet 10.250.150.1/30 scope global eno1\n' ;;
            esac
            ;;
          "-4 route show default")
            case "$FAKE_NETWORK_SCENARIO" in
              default-on-target) printf 'default via 192.168.1.1 dev eno1 metric 100\n' ;;
              *) printf 'default via 192.168.1.1 dev enx00e04c682086 metric 101\n' ;;
            esac
            ;;
          "-4 route get 10.250.150.2")
            case "$FAKE_NETWORK_SCENARIO" in
              bad-post-route) printf '10.250.150.2 dev enx00e04c682086 src 192.168.1.105\n' ;;
              *) printf '10.250.150.2 dev eno1 src 10.250.150.1\n' ;;
            esac
            ;;
        esac
        """,
    )
    env = dict(
        os.environ,
        ALLBOT_NMCLI_BIN=str(fake_nmcli),
        ALLBOT_IP_BIN=str(fake_ip),
        FAKE_NETWORK_LOG=str(log),
        FAKE_NETWORK_SCENARIO=scenario,
        SSH_CONNECTION=ssh_connection,
    )
    result = subprocess.run(
        [str(ROOT / "ops/media_archive_worker/install_nas_route.sh"), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    return result, log.read_text().splitlines() if log.exists() else []


def _mutations(log: list[str]) -> list[str]:
    return [
        line
        for line in log
        if any(
            action in line
            for action in (
                " connection add ",
                " connection modify ",
                " connection up ",
                " connection down ",
                " connection delete ",
            )
        )
    ]


def test_minio_compose_exposes_only_s3_on_the_direct_link():
    compose = (ROOT / "ops/media_archive_nas/compose.yml").read_text()

    assert '"${MINIO_DIRECT_BIND_IP:?Set the NAS direct-link IP}:9000:9000"' in compose
    assert "MINIO_DIRECT_BIND_IP" not in next(
        line for line in compose.splitlines() if "9001:9001" in line
    )


def test_tls_certificate_covers_management_and_direct_link_ips(tmp_path):
    env = dict(os.environ, MINIO_DIRECT_BIND_IP="10.250.150.2")
    subprocess.run(
        [str(ROOT / "ops/media_archive_nas/generate_tls.sh"), str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    result = subprocess.run(
        [
            "openssl",
            "x509",
            "-in",
            str(tmp_path / "certs/public.crt"),
            "-noout",
            "-ext",
            "subjectAltName",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "IP Address:192.168.1.150" in result.stdout
    assert "IP Address:10.250.150.2" in result.stdout


def test_tls_certificate_can_reuse_the_existing_ca(tmp_path):
    original = tmp_path / "original"
    renewed = tmp_path / "renewed"
    subprocess.run(
        [str(ROOT / "ops/media_archive_nas/generate_tls.sh"), str(original)],
        check=True,
        capture_output=True,
        text=True,
    )
    env = dict(
        os.environ,
        MINIO_DIRECT_BIND_IP="10.250.150.2",
        ALLBOT_ARCHIVE_EXISTING_CA_DIR=str(original / "ca"),
    )
    subprocess.run(
        [str(ROOT / "ops/media_archive_nas/generate_tls.sh"), str(renewed)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert (original / "ca/allbot-archive-ca.crt").read_bytes() == (
        renewed / "ca/allbot-archive-ca.crt"
    ).read_bytes()


def test_worker_example_uses_the_dedicated_physical_link():
    config = json.loads(
        (ROOT / "ops/media_archive_worker/worker.example.json").read_text()
    )

    assert config["nas"]["endpoint"] == "https://10.250.150.2:9000"
    assert config["nas"]["allowed_interfaces"] == ["eno1"]
    assert config["nas"]["allowed_source_ips"] == ["10.250.150.1"]


def test_route_installer_is_read_only_without_explicit_apply(tmp_path):
    result, log = _run_route_installer(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "read-only preflight passed" in result.stdout
    assert _mutations(log) == []


def test_route_installer_refuses_a_foreign_active_profile_on_eno1(tmp_path):
    result, log = _run_route_installer(
        tmp_path, scenario="foreign-profile", args=("--apply",)
    )

    assert result.returncode != 0
    assert "non-archive connection" in result.stderr
    assert _mutations(log) == []


def test_route_installer_refuses_default_route_or_management_ip_on_eno1(tmp_path):
    for scenario, expected in (
        ("default-on-target", "default route"),
        ("management-ip", "management address"),
    ):
        case_dir = tmp_path / scenario
        case_dir.mkdir()
        result, log = _run_route_installer(
            case_dir, scenario=scenario, args=("--apply",)
        )

        assert result.returncode != 0
        assert expected in result.stderr
        assert _mutations(log) == []


def test_route_installer_refuses_current_ssh_server_address_on_eno1(tmp_path):
    result, log = _run_route_installer(
        tmp_path,
        scenario="ssh-on-target",
        args=("--apply",),
        ssh_connection="192.168.1.3 55163 10.250.150.1 22",
    )

    assert result.returncode != 0
    assert "current SSH server address" in result.stderr
    assert _mutations(log) == []


def test_route_installer_never_mutates_management_or_legacy_profiles(tmp_path):
    result, log = _run_route_installer(tmp_path, args=("--apply",))

    assert result.returncode == 0, result.stderr
    assert _mutations(log)
    assert all("allbot-archive-direct" in line for line in _mutations(log))
    assert all("netplan-eno1" not in line for line in _mutations(log))
    assert all("有线连接 1" not in line for line in _mutations(log))


def test_route_installer_rolls_back_only_the_archive_profile_on_failure(tmp_path):
    result, log = _run_route_installer(
        tmp_path, scenario="bad-post-route", args=("--apply",)
    )

    assert result.returncode != 0
    mutations = _mutations(log)
    assert any("ipv4.addresses 10.250.150.9/30" in line for line in mutations)
    assert all("allbot-archive-direct" in line for line in mutations)
