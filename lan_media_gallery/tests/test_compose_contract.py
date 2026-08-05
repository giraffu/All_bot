from pathlib import Path

import yaml


MODULE_ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = "/home/hfy/Backups/NAS_WD500G_2026-08-04"


def _service() -> dict:
    compose = yaml.safe_load((MODULE_ROOT / "compose.yml").read_text())
    return compose["services"]["lan-media-gallery"]


def test_gallery_is_lan_bound_and_uses_an_immutable_image() -> None:
    service = _service()

    assert service["image"] == (
        "docker.io/bpatrik/pigallery2@"
        "sha256:d7a61b6daa410537064d4f661122545bc4d9b16cd91a3862d654c3555cb63992"
    )
    assert service["ports"] == ["192.168.1.115:8099:80"]
    assert service["user"] == "1000:1000"
    assert service["command"] == [
        "--default-Server-applicationTitle=AllBot 备份图库",
        "--default-Server-publicUrl=http://192.168.1.115:8099",
        "--default-Upload-enabled=false",
    ]


def test_gallery_can_only_read_curated_media_directories() -> None:
    service = _service()
    media_mounts = {
        mount["source"]: mount
        for mount in service["volumes"]
        if str(mount["source"]).startswith(BACKUP_ROOT)
    }

    assert set(media_mounts) == {
        f"{BACKUP_ROOT}/personal_sdb6",
        f"{BACKUP_ROOT}/windows/Pictures",
        f"{BACKUP_ROOT}/windows/WeChat Files/ljd007_007/Video",
        f"{BACKUP_ROOT}/windows/WeChat Files/ljd007_007/Attachment",
        f"{BACKUP_ROOT}/windows/Tencent Files/2191456046/Image",
        f"{BACKUP_ROOT}/windows/Tencent Files/2191456046/MyCollection/Image",
        f"{BACKUP_ROOT}/windows/Tencent Files/All Users/QQ/Misc/LNNCustomFace/PicFile",
    }
    assert all(mount["read_only"] is True for mount in media_mounts.values())
    assert BACKUP_ROOT not in media_mounts


def test_gallery_runtime_state_is_separate_from_the_verified_backup() -> None:
    service = _service()
    writable_targets = {
        mount["target"]
        for mount in service["volumes"]
        if not mount.get("read_only", False)
    }

    assert writable_targets == {
        "/app/data/config",
        "/app/data/db",
        "/app/data/tmp",
    }
    writable_sources = {
        mount["source"]
        for mount in service["volumes"]
        if not mount.get("read_only", False)
    }
    assert writable_sources == {
        "/home/hfy/.local/share/allbot/lan-media-gallery/config",
        "/home/hfy/.local/share/allbot/lan-media-gallery/db",
        "/home/hfy/.local/share/allbot/lan-media-gallery/tmp",
    }
    assert service["read_only"] is True
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["cap_drop"] == ["ALL"]
