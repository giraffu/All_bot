from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def test_public_web_uses_typed_submission_composable_without_sse_client():
    production_sources = [
        path
        for path in FRONTEND_SRC.rglob("*")
        if path.suffix in {".ts", ".vue"} and not path.name.endswith(".test.ts")
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in production_sources)

    assert (FRONTEND_SRC / "composables" / "useTaskSubmission.ts").exists()
    assert not (FRONTEND_SRC / "composables" / "useTaskStream.ts").exists()
    assert not (FRONTEND_SRC / "stores" / "taskStreamTransport.ts").exists()
    assert "useTaskStream" not in source
    assert "text/event-stream" not in source
    assert "startTaskStreamListening" not in source
    assert "task.submission_queued" in source


def test_backend_sse_route_remains_as_compatibility_surface():
    router = (ROOT / "src" / "web_api" / "routers" / "tasks.py").read_text(
        encoding="utf-8"
    )

    assert '@router.get("/{task_id}/stream")' in router
