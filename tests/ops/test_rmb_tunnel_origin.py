import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "manage_rmb_tunnel_origin.sh"


def test_cloud_origin_targets_the_immutable_payment_api_port():
    content = SCRIPT.read_text(encoding="utf-8")

    assert (
        'CLOUD_SERVICE_URL="${RMB_TUNNEL_CLOUD_SERVICE_URL:-'
        'http://100.107.220.127:8002}"'
    ) in content
    assert "cloud -> 100.107.220.127:8002" in content
    assert "Default: http://100.107.220.127:8002." in content


def test_execute_updates_service_and_origin_host_header(tmp_path):
    config = tmp_path / "config.yml"
    config.write_text(
        """
ingress:
  - hostname: rmb.aivison.it.com
    service: http://100.107.220.127:8021
    originRequest:
      httpHostHeader: 100.107.220.127:8021
  - service: http_status:404
""".lstrip(),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_sudo = fake_bin / "sudo"
    fake_sudo.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_sudo.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--target",
            "cloud",
            "--execute",
            "--skip-network-checks",
            "--config",
            str(config),
            "--backup-dir",
            str(tmp_path / "backups"),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    updated = config.read_text(encoding="utf-8")
    assert "service: http://100.107.220.127:8002" in updated
    assert "httpHostHeader: 100.107.220.127:8002" in updated
