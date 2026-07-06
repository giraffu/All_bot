import ast
from pathlib import Path


def test_submission_services_do_not_depend_on_python311_strenum() -> None:
    service_paths = (
        Path("src/services/quick_image_submission_service.py"),
        Path("src/services/quick_video_submission_service.py"),
        Path("src/services/advanced_video_submission_service.py"),
    )

    for service_path in service_paths:
        tree = ast.parse(service_path.read_text(encoding="utf-8"))
        enum_imports = [
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "enum"
            for alias in node.names
        ]

        assert "StrEnum" not in enum_imports, service_path
