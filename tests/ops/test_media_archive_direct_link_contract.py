import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


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
