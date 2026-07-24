#!/usr/bin/env python3
"""Validate the exact upstream CI run trusted by the modular release workflow."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any


EXPECTED_WORKFLOW_NAME = "Immutable control-plane release"
EXPECTED_WORKFLOW_PATH = ".github/workflows/control-plane-release.yml"
EXPECTED_TEST_JOBS = frozenset(
    {"web-tests", "dashboard-tests", "postgres-integration-tests"}
)
EXPECTED_OPERATOR_JOBS = frozenset({"operator-tests"})
EXPECTED_PYTHON_SHARDS = (
    "services-a-o",
    "services-p",
    "services-q-s",
    "services-t-z",
    "ops-scripts",
    "core-backend",
    "bots",
    "dashboard-analytics",
    "web-workers-misc",
)
ALLOWED_UPSTREAM_EVENTS = frozenset({"push", "workflow_dispatch"})
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PYTHON_JOB_RE = re.compile(r"^python-tests \(([^,]+),")
JOB_CONSISTENCY_ATTEMPTS = 7
JOB_CONSISTENCY_RETRY_SECONDS = 5


class CITrustError(RuntimeError):
    """Raised when an upstream workflow run cannot authorize a full release."""


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _repository_name(run: Mapping[str, Any]) -> str:
    repository = run.get("repository")
    if isinstance(repository, Mapping):
        return _string(repository.get("full_name"))
    return ""


def _successful_job_labels(jobs: Sequence[Mapping[str, Any]]) -> set[str]:
    successful: set[str] = set()
    for job in jobs:
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            continue
        name = _string(job.get("name"))
        if name in EXPECTED_TEST_JOBS or name in EXPECTED_OPERATOR_JOBS:
            successful.add(name)
            continue
        match = PYTHON_JOB_RE.match(name)
        if match and match.group(1) in EXPECTED_PYTHON_SHARDS:
            successful.add(f"python-tests:{match.group(1)}")
    return successful


def validate_upstream_run(
    run: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    *,
    expected_repository: str,
    expected_sha: str,
    expected_main_sha: str,
    expected_scope: str = "runtime",
) -> dict[str, Any]:
    """Return a non-secret trust summary or fail closed."""

    for label, sha in (
        ("expected source", expected_sha),
        ("current main", expected_main_sha),
    ):
        if not FULL_SHA_RE.fullmatch(sha):
            raise CITrustError(f"{label} SHA must be a full lowercase commit SHA")
    if expected_scope not in {"runtime", "operator"}:
        raise CITrustError("upstream change scope must be runtime or operator")
    if _repository_name(run) != expected_repository:
        raise CITrustError("upstream workflow repository does not match")
    if run.get("name") != EXPECTED_WORKFLOW_NAME:
        raise CITrustError("unexpected upstream workflow name")
    if run.get("path") != EXPECTED_WORKFLOW_PATH:
        raise CITrustError("unexpected upstream workflow path")
    event = _string(run.get("event"))
    if event not in ALLOWED_UPSTREAM_EVENTS:
        raise CITrustError("upstream event must be push or workflow_dispatch")
    if run.get("head_branch") != "main":
        raise CITrustError("upstream workflow did not run on main")
    if run.get("head_sha") != expected_sha:
        raise CITrustError("upstream workflow SHA does not match the release source")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise CITrustError("upstream workflow did not complete successfully")

    if expected_scope == "operator":
        expected_jobs = set(EXPECTED_OPERATOR_JOBS)
    else:
        expected_jobs = set(EXPECTED_TEST_JOBS)
        expected_jobs.update(f"python-tests:{name}" for name in EXPECTED_PYTHON_SHARDS)
    successful_jobs = _successful_job_labels(jobs)
    missing = sorted(expected_jobs - successful_jobs)
    if missing:
        raise CITrustError(
            "upstream workflow is missing successful expected test jobs: "
            + ", ".join(missing)
        )

    run_id = run.get("id")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        raise CITrustError("upstream workflow run id is invalid")
    return {
        "run_id": run_id,
        "event": event,
        "head_sha": expected_sha,
        "protected_main_sha": expected_main_sha,
        "scope": expected_scope,
        "successful_test_jobs": sorted(successful_jobs),
    }


def _github_json(url: str, *, token: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise CITrustError("unable to read upstream workflow evidence") from exc


def _fetch_run_and_jobs(
    *, repository: str, run_id: int, token: str
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    quoted_repository = "/".join(
        urllib.parse.quote(part, safe="") for part in repository.split("/")
    )
    base = f"https://api.github.com/repos/{quoted_repository}/actions/runs/{run_id}"
    run = _github_json(base, token=token)
    if not isinstance(run, Mapping):
        raise CITrustError("upstream workflow response is not an object")

    jobs: list[Mapping[str, Any]] = []
    page = 1
    while True:
        document = _github_json(
            f"{base}/jobs?filter=latest&per_page=100&page={page}", token=token
        )
        if not isinstance(document, Mapping) or not isinstance(
            document.get("jobs"), list
        ):
            raise CITrustError("upstream workflow jobs response is invalid")
        page_jobs = [job for job in document["jobs"] if isinstance(job, Mapping)]
        jobs.extend(page_jobs)
        if len(page_jobs) < 100:
            break
        page += 1
    return run, jobs


def _is_retryable_consistency_error(exc: CITrustError) -> bool:
    message = str(exc)
    return message.startswith(
        "upstream workflow is missing successful expected test jobs:"
    ) or message == "upstream workflow did not complete successfully"


def fetch_and_validate_upstream_run(
    *,
    fetch: Callable[
        [], tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]
    ],
    expected_repository: str,
    expected_sha: str,
    expected_main_sha: str,
    expected_scope: str = "runtime",
    attempts: int = JOB_CONSISTENCY_ATTEMPTS,
    retry_interval_seconds: float = JOB_CONSISTENCY_RETRY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Retry only GitHub job-list eventual consistency, then fail closed."""

    if attempts < 1 or retry_interval_seconds < 0:
        raise CITrustError("upstream consistency retry policy is invalid")
    last_error: CITrustError | None = None
    for attempt in range(1, attempts + 1):
        run, jobs = fetch()
        try:
            return validate_upstream_run(
                run,
                jobs,
                expected_repository=expected_repository,
                expected_sha=expected_sha,
                expected_main_sha=expected_main_sha,
                expected_scope=expected_scope,
            )
        except CITrustError as exc:
            last_error = exc
            if attempt == attempts or not _is_retryable_consistency_error(exc):
                raise
            print(
                "upstream job evidence is not consistent yet; "
                f"retrying {attempt}/{attempts - 1}",
                file=sys.stderr,
            )
            sleep(retry_interval_seconds)
    assert last_error is not None
    raise last_error


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-main-sha", required=True)
    parser.add_argument(
        "--expected-scope", choices=("runtime", "operator"), required=True
    )
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    token = os.environ.get(args.token_env, "")
    if not token:
        print(f"missing GitHub token in {args.token_env}", file=sys.stderr)
        return 2
    try:
        summary = fetch_and_validate_upstream_run(
            fetch=lambda: _fetch_run_and_jobs(
                repository=args.repository,
                run_id=args.run_id,
                token=token,
            ),
            expected_repository=args.repository,
            expected_sha=args.expected_sha,
            expected_main_sha=args.expected_main_sha,
            expected_scope=args.expected_scope,
        )
    except CITrustError as exc:
        print(f"untrusted upstream CI run: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
