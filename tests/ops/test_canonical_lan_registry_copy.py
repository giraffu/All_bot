from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/copy_canonical_image_to_lan_registry.sh"


def test_canonical_copy_helper_is_fail_closed_and_never_builds():
    text = SCRIPT.read_text(encoding="utf-8")
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    assert "@sha256:" in text
    assert 'crane copy "$source_ref" "$destination_ref"' in text
    assert 'crane digest "$destination_ref"' in text
    assert "docker build" not in text
    assert "--execute" in text


def test_canonical_copy_rejects_mutable_source_before_tool_lookup():
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--source",
            "ghcr.io/giraffu/example:latest",
            "--destination",
            "192.168.1.115:5000/example:test",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "digest-pinned" in result.stderr
