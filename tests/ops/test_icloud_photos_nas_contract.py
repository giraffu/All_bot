from pathlib import Path
import os
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops/icloud_photos_nas"
IMAGE = (
    "docker.io/icloudpd/icloudpd@"
    "sha256:af2bf40cb2c1d42051793b4c3c04c825950697d7fedcd12bd8455d6952395801"
)
OFFLINE_IMAGE = "sha256:6fe2cb61721e21f16a1a6506e623b0ae584495ff81d2e1faad72b55043443122"


def test_sync_container_is_immutable_non_root_and_has_no_listener() -> None:
    compose = yaml.safe_load((OPS / "compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["icloud-photo-backup"]

    assert compose["name"] == "allbot-icloud-photos-nas"
    assert service["image"] == f"${{ICLOUDPD_IMAGE:-{IMAGE}}}"
    assert service["user"] == "1000:100"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["tmpfs"] == [
        "/tmp:rw,exec,nosuid,nodev,size=256m,uid=1000,gid=100"
    ]
    assert "ports" not in service
    assert service["entrypoint"] == ["/opt/allbot/run.sh"]
    assert service["command"] == ["watch"]


def test_sync_container_only_writes_originals_and_private_runtime_state() -> None:
    compose = yaml.safe_load((OPS / "compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["icloud-photo-backup"]
    mounts = {item["target"]: item for item in service["volumes"]}

    assert mounts["/photos"] == {
        "type": "bind",
        "source": "/volume1/ApplePhotos/originals",
        "target": "/photos",
    }
    assert mounts["/state"] == {
        "type": "bind",
        "source": "/volume1/ApplePhotosRuntime/state",
        "target": "/state",
    }
    assert mounts["/run/secrets/apple_id"]["read_only"] is True
    assert mounts["/opt/allbot/run.sh"]["read_only"] is True
    assert mounts["/opt/allbot/auth.sh"]["read_only"] is True
    assert mounts["/opt/allbot/notify-reauth.sh"]["read_only"] is True
    assert service["healthcheck"]["test"] == [
        "CMD-SHELL",
        "test ! -e /state/reauth-required",
    ]


def test_sync_scripts_never_enable_icloud_or_local_deletion() -> None:
    scripts = "\n".join(
        (OPS / name).read_text(encoding="utf-8")
        for name in ("run.sh", "auth.sh", "notify-reauth.sh")
    )

    assert "--size original" in scripts
    assert "--live-photo-size original" in scripts
    assert "--xmp-sidecar" in scripts
    assert "--file-match-policy name-id7" in scripts
    assert "--delete-after-download" not in scripts
    assert "--keep-icloud-recent-days" not in scripts
    assert "--auto-delete" not in scripts


def test_canary_uses_original_assets_xmp_and_a_bounded_recent_set(tmp_path: Path) -> None:
    photos = tmp_path / "photos"
    state = tmp_path / "state"
    photos.mkdir()
    state.mkdir()
    apple_id = tmp_path / "apple-id"
    apple_id.write_text("person@example.test\n", encoding="utf-8")
    argv = tmp_path / "argv"
    fake = tmp_path / "icloudpd"
    fake.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {argv}\n", encoding="utf-8")
    fake.chmod(0o755)

    env = {
        **os.environ,
        "PHOTOS_PATH": str(photos),
        "STATE_PATH": str(state),
        "APPLE_ID_FILE": str(apple_id),
        "ICLOUDPD_BIN": str(fake),
        "ICLOUD_DOMAIN": "com",
        "CANARY_RECENT": "3",
        "MAX_USED_PERCENT": "99",
    }
    result = subprocess.run(
        [str(OPS / "run.sh"), "canary"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    args = argv.read_text(encoding="utf-8").splitlines()
    assert args[args.index("--size") + 1] == "original"
    assert args[args.index("--live-photo-size") + 1] == "original"
    assert "--xmp-sidecar" in args
    assert args[args.index("--file-match-policy") + 1] == "name-id7"
    assert args[args.index("--recent") + 1] == "3"


def test_authentication_is_interactive_and_never_accepts_a_password_argument(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    marker = state / "reauth-required"
    marker.write_text("expired\n", encoding="utf-8")
    apple_id = tmp_path / "apple-id"
    apple_id.write_text("person@example.test\n", encoding="utf-8")
    argv = tmp_path / "argv"
    fake = tmp_path / "icloudpd"
    fake.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {argv}\n", encoding="utf-8")
    fake.chmod(0o755)

    result = subprocess.run(
        [str(OPS / "auth.sh")],
        env={
            **os.environ,
            "STATE_PATH": str(state),
            "APPLE_ID_FILE": str(apple_id),
            "ICLOUDPD_BIN": str(fake),
            "ICLOUD_DOMAIN": "com",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    args = argv.read_text(encoding="utf-8").splitlines()
    assert "--auth-only" in args
    assert args.count("--password-provider") == 2
    assert "keyring" in args
    assert "console" in args
    assert "--password" not in args
    assert not marker.exists()


def test_bootstrap_is_dry_run_by_default_and_requires_exact_confirmation() -> None:
    script = OPS / "bootstrap.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)

    dry_run = subprocess.run(
        [str(script)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    assert "dry-run" in dry_run.stdout
    assert "/volume1/ApplePhotos/originals" in dry_run.stdout

    rejected = subprocess.run(
        [str(script), "--execute", "--confirm", "wrong"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "exact confirmation" in rejected.stderr


def test_offline_image_loader_requires_frozen_archive_and_image_id() -> None:
    script = OPS / "load-offline-image.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")

    assert OFFLINE_IMAGE in text
    assert "--archive-sha256" in text
    assert "LOAD_ICLOUDPD_OFFLINE_IMAGE" in text
    assert "docker load" in text
    assert "docker image inspect" in text

    dry_run = subprocess.run(
        [str(script), "--archive", "/tmp/not-used.tar.gz", "--archive-sha256", "0" * 64],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    assert "dry-run" in dry_run.stdout

    rejected = subprocess.run(
        [
            str(script),
            "--archive",
            "/tmp/not-used.tar.gz",
            "--archive-sha256",
            "0" * 64,
            "--execute",
            "--confirm",
            "wrong",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "exact confirmation" in rejected.stderr


def test_bootstrap_persists_only_approved_content_addressed_images() -> None:
    text = (OPS / "bootstrap.sh").read_text(encoding="utf-8")

    assert IMAGE in text
    assert OFFLINE_IMAGE in text
    assert 'ICLOUDPD_IMAGE=' in text
    assert "docker image inspect --format" in text
    assert '"$icloudpd_image"' in text
    assert 'pull icloud-photo-backup' in text


def test_root_operator_owns_compose_workdir_and_rejects_unknown_actions() -> None:
    script = OPS / "operator.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")

    assert "/volume1/ApplePhotosRuntime/deploy" in text
    assert "docker compose run --rm --entrypoint /opt/allbot/auth.sh" in text
    assert "docker compose run --rm icloud-photo-backup canary" in text
    assert "docker compose up -d icloud-photo-backup" in text
    assert "docker compose stop icloud-photo-backup" in text

    rejected = subprocess.run(
        [str(script), "unknown"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "must run as root" in rejected.stderr


def test_snapshots_cover_originals_but_never_credentials() -> None:
    script = OPS / "snapshot.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")

    assert "/volume1/ApplePhotos/originals" in text
    assert "snapshot -r" in text
    assert "/volume1/ApplePhotosRuntime" not in text
    assert "retain" in text


def test_runbook_keeps_icloud_ingest_separate_from_gallery_and_credentials() -> None:
    readme = (OPS / "README.md").read_text(encoding="utf-8")
    domain_doc = (
        ROOT / "docs/子模块_局域网备份图库_lan_media_gallery.md"
    ).read_text(encoding="utf-8")

    assert "不上传文件" in readme
    assert "keyring/session" in domain_doc
    assert "首轮全量验收前默认不把 iCloud 原片接入 PiGallery2" in domain_doc
