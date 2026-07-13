from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "deploy" / "docker-compose-cloud-base.yml"
OVERLAYS = (
    ROOT / "deploy" / "docker-compose-cloud-test.overlay.yml",
    ROOT / "deploy" / "docker-compose-cloud-prod.overlay.yml",
)
WORKER_BASE = ROOT / "deploy" / "docker-compose-worker-base.yml"


def _compose(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_immutable_cloud_compose_has_no_build_or_code_mounts():
    forbidden_mounts = ("src", "backend/app", "workflows", ".env")

    for path in (BASE, *OVERLAYS, WORKER_BASE):
        compose = _compose(path)
        for service in compose.get("services", {}).values():
            assert "build" not in service, f"{path}: build is forbidden"
            for volume in service.get("volumes", []) or []:
                source = str(volume).split(":", 1)[0]
                assert not any(item in source for item in forbidden_mounts), (
                    f"{path}: source/config bind mount is forbidden: {volume}"
                )


def test_every_runtime_image_is_supplied_by_release_env():
    services = _compose(BASE)["services"]

    for name, service in services.items():
        image = str(service["image"])
        assert image.startswith("${ALLBOT_"), f"{name} does not use release.env"
        assert "latest" not in image


def test_central_and_worker_images_contain_their_dependency_closure():
    central = (ROOT / "deploy/docker/Dockerfile.central").read_text(encoding="utf-8")
    worker = (ROOT / "deploy/docker/Dockerfile.worker").read_text(encoding="utf-8")

    assert "COPY backend/app /app/app" in central
    assert "COPY src /app/src" in central
    assert "COPY workers/comfy_agent /app/worker" in worker
    assert "COPY src /app/src" in worker


def test_release_workflow_builds_all_images_and_never_uses_latest():
    workflow = (ROOT / ".github/workflows/control-plane-release.yml").read_text(
        encoding="utf-8"
    )

    for image in (
        "allbot-app",
        "allbot-central-api",
        "allbot-dashboard-backend",
        "allbot-dashboard-frontend",
        "allbot-worker",
        "allbot-release",
    ):
        assert image in workflow
    assert ":latest" not in workflow
