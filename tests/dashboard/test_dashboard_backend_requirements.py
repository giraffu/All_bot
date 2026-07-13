from pathlib import Path


def test_dashboard_backend_image_includes_yaml_runtime_dependency():
    requirements_path = (
        Path(__file__).resolve().parents[2]
        / "dashboard"
        / "backend"
        / "requirements.txt"
    )
    requirements = {
        line.strip().split("==", 1)[0].split("[", 1)[0].lower()
        for line in requirements_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert "pyyaml" in requirements
