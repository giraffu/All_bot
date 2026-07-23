import importlib.util
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "validate_upstream_ci_run.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_upstream_ci_run", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_successful_main_workflow_dispatch_with_every_test_job_is_trusted():
    module = _load_module()
    source_sha = "a" * 40
    run = {
        "id": 123,
        "name": "Immutable control-plane release",
        "path": ".github/workflows/control-plane-release.yml",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": source_sha,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "giraffu/All_bot"},
    }
    jobs = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in (
            "web-tests",
            "dashboard-tests",
            "postgres-integration-tests",
            *(
                f"python-tests ({shard}, synthetic paths)"
                for shard in module.EXPECTED_PYTHON_SHARDS
            ),
        )
    ]

    result = module.validate_upstream_run(
        run,
        jobs,
        expected_repository="giraffu/All_bot",
        expected_sha=source_sha,
        expected_main_sha=source_sha,
    )

    assert result["event"] == "workflow_dispatch"
    assert result["head_sha"] == source_sha
    assert result["run_id"] == 123


def _trusted_evidence(module, *, event="workflow_dispatch"):
    source_sha = "a" * 40
    run = {
        "id": 123,
        "name": "Immutable control-plane release",
        "path": ".github/workflows/control-plane-release.yml",
        "event": event,
        "head_branch": "main",
        "head_sha": source_sha,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "giraffu/All_bot"},
    }
    jobs = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in (
            *module.EXPECTED_TEST_JOBS,
            *(
                f"python-tests ({shard}, synthetic paths)"
                for shard in module.EXPECTED_PYTHON_SHARDS
            ),
        )
    ]
    return source_sha, run, jobs


def test_successful_main_push_remains_trusted():
    module = _load_module()
    source_sha, run, jobs = _trusted_evidence(module, event="push")

    result = module.validate_upstream_run(
        run,
        jobs,
        expected_repository="giraffu/All_bot",
        expected_sha=source_sha,
        expected_main_sha=source_sha,
    )

    assert result["event"] == "push"


def test_successful_operator_scope_requires_only_the_focused_operator_job():
    module = _load_module()
    source_sha, run, _jobs = _trusted_evidence(module, event="push")
    jobs = [{"name": "operator-tests", "status": "completed", "conclusion": "success"}]

    result = module.validate_upstream_run(
        run,
        jobs,
        expected_repository="giraffu/All_bot",
        expected_sha=source_sha,
        expected_main_sha=source_sha,
        expected_scope="operator",
    )

    assert result["scope"] == "operator"
    assert result["successful_test_jobs"] == ["operator-tests"]


def test_operator_scope_fails_closed_without_the_operator_job():
    module = _load_module()
    source_sha, run, jobs = _trusted_evidence(module, event="push")

    with pytest.raises(module.CITrustError, match="operator-tests"):
        module.validate_upstream_run(
            run,
            jobs,
            expected_repository="giraffu/All_bot",
            expected_sha=source_sha,
            expected_main_sha=source_sha,
            expected_scope="operator",
        )


def test_unknown_upstream_scope_fails_closed():
    module = _load_module()
    source_sha, run, jobs = _trusted_evidence(module, event="push")

    with pytest.raises(module.CITrustError, match="scope"):
        module.validate_upstream_run(
            run,
            jobs,
            expected_repository="giraffu/All_bot",
            expected_sha=source_sha,
            expected_main_sha=source_sha,
            expected_scope="unexpected",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda source_sha, run, jobs: run["repository"].update(
                full_name="attacker/fork"
            ),
            "repository",
        ),
        (
            lambda source_sha, run, jobs: run.update(name="Different workflow"),
            "workflow name",
        ),
        (
            lambda source_sha, run, jobs: run.update(
                path=".github/workflows/different.yml"
            ),
            "workflow path",
        ),
        (
            lambda source_sha, run, jobs: run.update(event="pull_request"),
            "event",
        ),
        (
            lambda source_sha, run, jobs: run.update(head_branch="feature"),
            "main",
        ),
        (
            lambda source_sha, run, jobs: run.update(head_sha="b" * 40),
            "release source",
        ),
        (
            lambda source_sha, run, jobs: run.update(conclusion="failure"),
            "successfully",
        ),
        (
            lambda source_sha, run, jobs: jobs.pop(),
            "missing successful",
        ),
        (
            lambda source_sha, run, jobs: jobs[-1].update(conclusion="failure"),
            "missing successful",
        ),
    ],
)
def test_untrusted_upstream_metadata_or_incomplete_jobs_fail_closed(
    mutation, message
):
    module = _load_module()
    source_sha, run, jobs = _trusted_evidence(module)
    mutation(source_sha, run, jobs)

    with pytest.raises(module.CITrustError, match=message):
        module.validate_upstream_run(
            run,
            jobs,
            expected_repository="giraffu/All_bot",
            expected_sha=source_sha,
            expected_main_sha=source_sha,
        )


def test_stale_upstream_sha_is_rejected_even_when_that_run_passed():
    module = _load_module()
    source_sha, run, jobs = _trusted_evidence(module)

    with pytest.raises(module.CITrustError, match="current protected main head"):
        module.validate_upstream_run(
            run,
            jobs,
            expected_repository="giraffu/All_bot",
            expected_sha=source_sha,
            expected_main_sha="b" * 40,
        )


def test_expected_python_shards_match_the_upstream_workflow_contract():
    module = _load_module()
    workflow = (ROOT / ".github/workflows/control-plane-release.yml").read_text(
        encoding="utf-8"
    )

    python_job = workflow.split("\n  python-tests:\n", 1)[1].split(
        "\n  postgres-integration-tests:\n", 1
    )[0]
    workflow_shards = set(re.findall(r"^          - name: (.+)$", python_job, re.M))

    assert workflow_shards == set(module.EXPECTED_PYTHON_SHARDS)


def test_job_api_pagination_is_pinned_to_latest_attempt(monkeypatch):
    module = _load_module()
    urls = []
    first_page = [
        {"name": f"irrelevant-{index}", "status": "completed"}
        for index in range(100)
    ]

    def fake_github_json(url, *, token):
        urls.append(url)
        assert token == "synthetic-token"
        if "/jobs?" not in url:
            return {"id": 123}
        if url.endswith("page=1"):
            return {"jobs": first_page}
        return {"jobs": [{"name": "web-tests"}]}

    monkeypatch.setattr(module, "_github_json", fake_github_json)

    run, jobs = module._fetch_run_and_jobs(
        repository="giraffu/All_bot", run_id=123, token="synthetic-token"
    )

    assert run == {"id": 123}
    assert len(jobs) == 101
    assert "filter=latest" in urls[1]
    assert "page=2" in urls[2]


def test_eventually_consistent_jobs_are_retried_then_trusted():
    module = _load_module()
    source_sha, run, jobs = _trusted_evidence(module, event="push")
    incomplete = [job for job in jobs if "services-t-z" not in job["name"]]
    attempts = iter([(run, incomplete), (run, jobs)])
    sleeps = []

    result = module.fetch_and_validate_upstream_run(
        fetch=lambda: next(attempts),
        expected_repository="giraffu/All_bot",
        expected_sha=source_sha,
        expected_main_sha=source_sha,
        attempts=2,
        retry_interval_seconds=5,
        sleep=lambda seconds: sleeps.append(seconds),
    )

    assert result["head_sha"] == source_sha
    assert sleeps == [5]


def test_non_transient_upstream_mismatch_is_not_retried():
    module = _load_module()
    source_sha, run, jobs = _trusted_evidence(module, event="push")
    run["repository"]["full_name"] = "attacker/fork"
    fetches = []

    def fetch():
        fetches.append(True)
        return run, jobs

    with pytest.raises(module.CITrustError, match="repository"):
        module.fetch_and_validate_upstream_run(
            fetch=fetch,
            expected_repository="giraffu/All_bot",
            expected_sha=source_sha,
            expected_main_sha=source_sha,
            attempts=7,
            retry_interval_seconds=5,
            sleep=lambda _seconds: pytest.fail("metadata mismatch must not retry"),
        )

    assert len(fetches) == 1


def test_eventual_consistency_retry_is_bounded_and_fails_closed():
    module = _load_module()
    source_sha, run, jobs = _trusted_evidence(module, event="push")
    incomplete = [job for job in jobs if "services-t-z" not in job["name"]]
    fetches = []
    sleeps = []

    with pytest.raises(module.CITrustError, match="services-t-z"):
        module.fetch_and_validate_upstream_run(
            fetch=lambda: fetches.append(True) or (run, incomplete),
            expected_repository="giraffu/All_bot",
            expected_sha=source_sha,
            expected_main_sha=source_sha,
            attempts=7,
            retry_interval_seconds=5,
            sleep=lambda seconds: sleeps.append(seconds),
        )

    assert len(fetches) == 7
    assert sleeps == [5] * 6
