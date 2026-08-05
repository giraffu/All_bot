import json
import io
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.media_archive_worker import (
    AdaptiveConcurrencyController,
    CatalogRecorder,
    SpoolBudget,
    capacity_claim_priority,
    clear_proxy_environment,
    load_secure_config,
    RateLimiter,
    restore_one_asset,
)


def test_worker_cli_bootstraps_repository_imports_from_any_working_directory(tmp_path):
    worker = Path(__file__).resolve().parents[2] / "scripts/media_archive_worker.py"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            f"import runpy; runpy.run_path({str(worker)!r}, run_name='archive_worker_test'); import src",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_catalog_run_accepts_a_string_worker_id(monkeypatch):
    class FakeConnection:
        async def execute(self, statement, *args):
            if (
                "jsonb_build_object('worker_id'" in statement
                and "$2::text" not in statement
            ):
                raise RuntimeError("could not determine data type of parameter $2")
            if "jsonb_build_object('assets'" in statement and not all(
                cast in statement for cast in ("$4::bigint", "$5::bigint")
            ):
                raise RuntimeError("could not determine data type of run statistics")

        async def close(self):
            return None

    async def connect(_database_url):
        return FakeConnection()

    monkeypatch.setattr("scripts.media_archive_worker.asyncpg.connect", connect)

    async with CatalogRecorder("postgresql://catalog", "archive-worker-1"):
        pass


def test_worker_config_requires_regular_0600_file_owned_by_current_user(tmp_path: Path):
    config = tmp_path / "worker.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    config.chmod(0o644)
    with pytest.raises(PermissionError, match="0600"):
        load_secure_config(config)

    config.chmod(0o600)
    assert load_secure_config(config)["sources"] == []


def test_spool_budget_counts_parts_reserves_and_pauses_at_high_water(tmp_path: Path):
    existing = tmp_path / "old.part"
    existing.write_bytes(b"x" * 60)
    budget = SpoolBudget(tmp_path, capacity_bytes=100, pause_bytes=90)

    assert budget.used_bytes == 60
    budget.reserve(29)
    assert budget.used_bytes == 89
    with pytest.raises(RuntimeError, match="pause threshold"):
        budget.reserve(2)
    budget.release(29)
    assert budget.used_bytes == 60


def test_adaptive_concurrency_only_increases_on_low_error_sustained_window():
    controller = AdaptiveConcurrencyController(
        bandwidth_limit_bps=100,
        window_seconds=900,
        levels=(8, 16, 32),
    )
    assert controller.observe(bytes_transferred=45_000, errors=0, elapsed=900) == 16
    assert controller.observe(bytes_transferred=90_000, errors=2, elapsed=900) == 8


def test_worker_rejects_local_7890_proxy_before_clearing(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    with pytest.raises(RuntimeError, match="7890"):
        clear_proxy_environment()


def test_nas_capacity_gates_stop_cold_then_all_claims():
    assert capacity_claim_priority(archived_bytes=74, capacity_bytes=100) == 100
    assert capacity_claim_priority(archived_bytes=80, capacity_bytes=100) == 0
    assert capacity_claim_priority(archived_bytes=90, capacity_bytes=100) is None


def test_restore_revalidates_nas_then_uploads_originals_and_rebuilt_thumbnail(tmp_path):
    payload = b"verified-archive-bytes"
    digest = __import__("hashlib").sha256(payload).hexdigest()

    class FakeNas:
        def head_object(self, **_kwargs):
            return {"ContentLength": len(payload), "Metadata": {"sha256": digest}}

        def get_object(self, **_kwargs):
            return {"Body": io.BytesIO(payload)}

    class FakeR2:
        def __init__(self):
            self.objects = {}

        def upload_file(self, path, bucket, key, ExtraArgs):
            body = Path(path).read_bytes()
            self.objects[(bucket, key)] = (body, ExtraArgs["Metadata"])

        def head_object(self, Bucket, Key):
            body, metadata = self.objects[(Bucket, Key)]
            return {"ContentLength": len(body), "Metadata": metadata}

    r2 = FakeR2()

    def client_factory(config):
        return FakeNas() if config["name"] == "nas" else r2

    def thumbnail_builder(_source, _media_type, output):
        output.write_bytes(b"thumbnail")

    budget = SpoolBudget(tmp_path, capacity_bytes=1024, pause_bytes=900)
    result = restore_one_asset(
        {
            "role": "output",
            "ordinal": 0,
            "source_ref": "outputs/result.png",
            "source_key": "outputs/result.png",
            "sha256": digest,
            "byte_size": len(payload),
            "mime_type": "image/png",
            "nas_bucket": "archive",
            "nas_key": "blobs/result.png",
        },
        "task-1",
        "image",
        {"name": "nas"},
        {"name": "r2", "bucket": "prod"},
        tmp_path,
        RateLimiter(10**9),
        budget,
        client_factory=client_factory,
        thumbnail_builder=thumbnail_builder,
    )

    assert result["r2_keys"]
    assert result["thumbnail_keys"]
    assert all(("prod", key) in r2.objects for key in result["r2_keys"])
    assert all(("prod", key) in r2.objects for key in result["thumbnail_keys"])
    assert budget.used_bytes == 0
