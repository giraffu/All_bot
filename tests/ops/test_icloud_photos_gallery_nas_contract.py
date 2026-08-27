from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops/icloud_photos_gallery_nas"
ONLINE_IMAGE = (
    "docker.io/bpatrik/pigallery2@"
    "sha256:d7a61b6daa410537064d4f661122545bc4d9b16cd91a3862d654c3555cb63992"
)
OFFLINE_IMAGE = "sha256:074da989a73e4e26d666c89989272b3b76c1d63a92a4e99e82fd98e8f7d36189"


def _service() -> dict:
    compose = yaml.safe_load((OPS / "compose.yml").read_text(encoding="utf-8"))
    return compose["services"]["icloud-photos-gallery"]


def test_gallery_is_lan_scoped_hardened_and_content_addressed() -> None:
    service = _service()

    assert service["image"] == f"${{PIGALLERY_IMAGE:-{ONLINE_IMAGE}}}"
    assert service["container_name"] == "allbot-icloud-photos-gallery"
    assert service["user"] == "1000:100"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["ports"] == ["${GALLERY_BIND_IP:-127.0.0.1}:8099:80"]


def test_gallery_can_only_read_originals_and_writes_private_runtime() -> None:
    service = _service()
    mounts = {mount["target"]: mount for mount in service["volumes"]}

    assert mounts["/app/data/images/iCloud原片"] == {
        "type": "bind",
        "source": "/volume1/ApplePhotos/originals",
        "target": "/app/data/images/iCloud原片",
        "read_only": True,
    }
    assert {
        target for target, mount in mounts.items() if not mount.get("read_only", False)
    } == {"/app/data/config", "/app/data/db", "/app/data/tmp"}
    assert all(
        str(mount["source"]).startswith("/volume1/ApplePhotosGalleryRuntime/")
        for target, mount in mounts.items()
        if target in {"/app/data/config", "/app/data/db", "/app/data/tmp"}
    )


def test_gallery_disables_upload_and_tracks_new_downloads() -> None:
    command = _service()["command"]

    assert "--default-Upload-enabled=false" in command
    assert "--default-Sharing-enabled=false" in command
    assert "--default-Gallery-AutoUpdate-enable=true" in command
    assert "--default-Gallery-AutoUpdate-interval=60" in command


def test_bootstrap_is_dry_run_and_requires_exact_confirmation() -> None:
    script = OPS / "bootstrap.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)

    dry_run = subprocess.run(
        [str(script)], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert dry_run.returncode == 0, dry_run.stderr
    assert "dry-run" in dry_run.stdout
    assert "/volume1/ApplePhotos/originals" in dry_run.stdout
    assert "127.0.0.1:8099" in dry_run.stdout

    rejected = subprocess.run(
        [str(script), "--execute", "--confirm", "wrong"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "exact confirmation" in rejected.stderr


def test_bootstrap_accepts_only_approved_images_and_initializes_before_lan() -> None:
    text = (OPS / "bootstrap.sh").read_text(encoding="utf-8")

    assert ONLINE_IMAGE in text
    assert OFFLINE_IMAGE in text
    assert "initialize-admin.sh" in text
    assert "write_env 127.0.0.1 http://127.0.0.1:8099" in text
    assert "write_env 192.168.1.150 http://192.168.1.150:8099" in text
    assert "--force-recreate" in text
    assert "admin-username" in text
    assert "default_gallery_user=nas-gallery" in text


def test_initializer_removes_upstream_default_before_marking_complete() -> None:
    script = OPS / "initialize-admin.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")

    assert "gallery_url=http://127.0.0.1:8099" in text
    assert '"$gallery_url/pgapi/user/login"' in text
    assert '"username":"admin","password":"admin"' in text
    assert "/pgapi/user/list" in text
    assert "-X DELETE" in text
    assert "replacement gallery administrator is not active" in text
    assert "admin-username" in text
    assert 'gallery_user=$(tr -d' in text
    assert "default_status" not in text
    assert "admin-initialized" in text


def test_operator_reads_runtime_admin_identity_without_printing_password() -> None:
    script = OPS / "operator.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")

    assert "admin-username" in text
    assert 'gallery_user=$(tr -d' in text
    assert 'echo "username: $gallery_user"' in text
    assert 'echo "username: nas-gallery"' not in text
    assert "cat /volume1/ApplePhotosGalleryRuntime/secrets/admin-password" not in text


def test_offline_loader_verifies_archive_and_exact_image_id() -> None:
    script = OPS / "load-offline-image.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")

    assert OFFLINE_IMAGE in text
    assert "LOAD_PIGALLERY_OFFLINE_IMAGE" in text
    assert "--archive-sha256" in text
    assert "docker load" in text


def test_runbook_marks_live_download_browsing_as_an_incomplete_preview() -> None:
    readme = (OPS / "README.md").read_text(encoding="utf-8")

    assert "预览" in readme
    assert "下载中的内容并不代表完整备份" in readme
    assert "/volume1/ApplePhotos/originals" in readme
    assert "read_only" in readme
