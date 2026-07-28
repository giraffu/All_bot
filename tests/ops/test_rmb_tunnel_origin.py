from pathlib import Path


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
