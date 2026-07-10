#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_ROOT = ROOT / "backups" / "cloud-prod-shadow"
DEFAULT_LOG_PATH = ROOT / "logs" / "local-analytics-shadow-pipeline.log"
DEFAULT_VECTOR_LOCK_PATH = (
    ROOT / "local_analytics_platform" / "data" / "prompt_vectors" / ".refresh_prompt_vectors.lock"
)
SAFE_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
DEFAULT_MODEL_ID = "qwen3-embedding-8b"
DEFAULT_MODEL_KEY = "text-embedding-qwen3-embedding-8b"
LOCAL_ANALYTICS_TABLE_ALLOWLIST = (
    "analytics_prompt_mart_state",
    "analytics_prompt_dim",
    "analytics_prompt_occurrence",
    "analytics_prompt_group_stats",
    "analytics_prompt_rollup_stats",
    "analytics_prompt_slim_candidates",
    "analytics_prompt_token_alias_rules",
    "analytics_prompt_token_custom_terms",
    "analytics_prompt_token_deleted_rules",
    "analytics_prompt_token_extract_cache",
    "analytics_prompt_token_prompts",
    "analytics_prompt_token_stats",
    "analytics_prompt_vector_state",
    "analytics_prompt_embeddings",
    "analytics_user_profile_daily_snapshots",
)


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class PipelineConfig:
    execute: bool = False
    restore_from_db: str | None = None
    batch_size: int = 128
    mart_full: bool = False
    shadow_db: str = "bot_db_prod_shadow"
    postgres_container: str = "allbot-postgres-prod-shadow-pg18"
    postgres_user: str = "postgres"
    analytics_container: str = "allbot-local-analytics-platform"
    backup_root: Path = DEFAULT_BACKUP_ROOT
    log_path: Path = DEFAULT_LOG_PATH
    vector_lock_path: Path = DEFAULT_VECTOR_LOCK_PATH
    statement_timeout_ms: int = 3_600_000
    lm_studio_base_url: str = "http://127.0.0.1:1234/v1"
    model_id: str = DEFAULT_MODEL_ID
    model_key: str = DEFAULT_MODEL_KEY
    shadow_lock_timeout_seconds: int = 12 * 60 * 60

    @property
    def pipeline_lock_path(self) -> Path:
        return self.backup_root / ".local-analytics-refresh.lock"

    @property
    def shadow_lock_path(self) -> Path:
        return self.backup_root / ".shadow-sync.lock"


class PipelineCommandRunner:
    def __init__(self, *, execute: bool, log_path: Path) -> None:
        self.execute = execute
        self.log_path = log_path
        self.commands: list[tuple[str | None, list[str]]] = []

    def run(self, cmd: Sequence[str], *, label: str | None = None) -> None:
        rendered = self._render(cmd, label=label)
        self.commands.append((label, list(cmd)))
        self._log(rendered)
        if not self.execute:
            print(f"[dry-run] {rendered}")
            return
        with self.log_path.open("a", encoding="utf-8") as handle:
            subprocess.run(list(cmd), check=True, text=True, stdout=handle, stderr=handle)

    def capture(self, cmd: Sequence[str], *, label: str | None = None) -> str:
        rendered = self._render(cmd, label=label)
        self.commands.append((label, list(cmd)))
        self._log(rendered)
        if not self.execute:
            print(f"[dry-run] {rendered}")
            return ""
        completed = subprocess.run(
            list(cmd),
            check=True,
            text=True,
            capture_output=True,
        )
        self._log(completed.stdout)
        if completed.stderr:
            self._log(completed.stderr)
        return completed.stdout

    def _render(self, cmd: Sequence[str], *, label: str | None) -> str:
        prefix = f"[{label}] " if label else ""
        return prefix + " ".join(shlex.quote(part) for part in cmd)

    def _log(self, text: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(text.rstrip() + "\n")


def validate_db_name(name: str, *, label: str) -> None:
    if not SAFE_DB_NAME_RE.fullmatch(name):
        raise PipelineError(f"{label} must be a simple PostgreSQL database name")


def copy_local_analytics_tables_cmd(config: PipelineConfig, source_db: str) -> list[str]:
    validate_db_name(source_db, label="restore source database")
    validate_db_name(config.shadow_db, label="shadow database")
    source = shlex.quote(source_db)
    target = shlex.quote(config.shadow_db)
    user = shlex.quote(config.postgres_user)
    table_names_sql = ", ".join(f"'{table_name}'" for table_name in LOCAL_ANALYTICS_TABLE_ALLOWLIST)
    table_predicate = f"tablename in ({table_names_sql})"
    table_list_sql = (
        "select tablename from pg_tables "
        "where schemaname = 'public' "
        f"and ({table_predicate}) "
        "order by tablename"
    )
    script = "\n".join(
        [
            "set -eu",
            "tmp_dump=/tmp/allbot_local_analytics_restore.dump",
            "tmp_tables=/tmp/allbot_local_analytics_tables.txt",
            "rm -f \"$tmp_dump\"",
            f"psql -U {user} -d {source} -v ON_ERROR_STOP=1 -At -c {shlex.quote(table_list_sql)} > \"$tmp_tables\"",
            "if [ ! -s \"$tmp_tables\" ]; then",
            "  echo 'Local analytics table restore skipped: no local analytics tables found'",
            "  exit 0",
            "fi",
            "dump_table_args=\"\"",
            "while IFS= read -r table_name; do",
            "  dump_table_args=\"$dump_table_args --table=public.$table_name\"",
            "done < \"$tmp_tables\"",
            f"pg_dump -U {user} -d {source} --format=custom --schema=public $dump_table_args --file=\"$tmp_dump\"",
            f"psql -U {user} -d {target} -v ON_ERROR_STOP=1 <<'SQL'",
            "do $$",
            "declare row record;",
            "begin",
            "  for row in",
            "    select schemaname, tablename from pg_tables",
            f"    where schemaname = 'public' and ({table_predicate})",
            "  loop",
            "    execute format('drop table if exists %I.%I cascade', row.schemaname, row.tablename);",
            "  end loop;",
            "end $$;",
            "SQL",
            f"pg_restore -U {user} --no-owner --no-privileges -d {target} \"$tmp_dump\"",
            "rm -f \"$tmp_dump\" \"$tmp_tables\"",
        ]
    )
    return ["docker", "exec", config.postgres_container, "sh", "-lc", script]


def analytics_python_cmd(config: PipelineConfig, module: str, *args: str) -> list[str]:
    return [
        "docker",
        "exec",
        config.analytics_container,
        "python",
        "-m",
        module,
        *args,
    ]


def lm_studio_ready(config: PipelineConfig) -> bool:
    try:
        with urllib.request.urlopen(f"{config.lm_studio_base_url.rstrip('/')}/models", timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return False
    models = payload.get("data") or []
    model_ids = {str(model.get("id") or "") for model in models if isinstance(model, dict)}
    return config.model_id in model_ids or config.model_key in model_ids


def acquire_pipeline_lock(config: PipelineConfig):
    if not config.execute:
        return None
    config.backup_root.mkdir(parents=True, exist_ok=True)
    handle = config.pipeline_lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.write(f"pid={os.getpid()} started_at={time.time()}\n")
    handle.flush()
    return handle


def wait_for_shadow_sync(config: PipelineConfig) -> None:
    if not config.execute or not config.shadow_lock_path.exists():
        return
    deadline = time.monotonic() + config.shadow_lock_timeout_seconds
    while True:
        with config.shadow_lock_path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(handle, fcntl.LOCK_UN)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PipelineError("timed out waiting for cloud-prod shadow sync lock")
                time.sleep(30)


def vector_refresh_lock_is_held(config: PipelineConfig) -> bool:
    if not config.execute or not config.vector_lock_path.exists():
        return False
    try:
        handle = config.vector_lock_path.open("r", encoding="utf-8")
    except PermissionError:
        return True
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False
    finally:
        handle.close()


def run_pipeline(
    config: PipelineConfig,
    *,
    runner: PipelineCommandRunner | None = None,
    lm_studio_checker: Callable[[PipelineConfig], bool] = lm_studio_ready,
) -> dict[str, str]:
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    runner = runner or PipelineCommandRunner(execute=config.execute, log_path=config.log_path)
    lock_handle = acquire_pipeline_lock(config)
    if config.execute and lock_handle is None:
        message = {"status": "skipped_lock_held"}
        config.log_path.parent.mkdir(parents=True, exist_ok=True)
        with config.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(message, sort_keys=True) + "\n")
        return message

    result = {"status": "ok", "embedding": "not_requested"}
    try:
        wait_for_shadow_sync(config)
        if config.restore_from_db:
            runner.run(
                copy_local_analytics_tables_cmd(config, config.restore_from_db),
                label="copy-local-analytics",
            )

        runner.run(
            analytics_python_cmd(
                config,
                "app.refresh_user_profile_snapshots",
                "--statement-timeout-ms",
                str(config.statement_timeout_ms),
            ),
            label="refresh-user-profile-snapshot",
        )

        if vector_refresh_lock_is_held(config):
            message = {"status": "skipped_vector_lock_held"}
            with config.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(message, sort_keys=True) + "\n")
            return message

        mart_args = ["--statement-timeout-ms", str(config.statement_timeout_ms)]
        if config.mart_full:
            mart_args.insert(0, "--full")
        runner.run(
            analytics_python_cmd(config, "app.refresh_prompt_mart", *mart_args),
            label="refresh-prompt-mart",
        )
        runner.run(
            analytics_python_cmd(
                config,
                "app.refresh_prompt_slim_table",
                "--statement-timeout-ms",
                str(config.statement_timeout_ms),
            ),
            label="refresh-prompt-slim",
        )
        runner.run(
            analytics_python_cmd(
                config,
                "app.refresh_prompt_vectors",
                "--tokens-only",
                "--statement-timeout-ms",
                str(config.statement_timeout_ms),
            ),
            label="refresh-prompt-tokens",
        )

        lm_studio_available = lm_studio_checker(config)
        if not lm_studio_available:
            result["embedding"] = "skipped_lm_studio_unavailable"
            runner.run(["sh", "-lc", "echo LM Studio embedding model unavailable; skipping embeddings"], label="skip-embeddings")
        else:
            runner.run(
                analytics_python_cmd(
                    config,
                    "app.refresh_prompt_vectors",
                    "--embed-only",
                    "--skip-token-refresh",
                    "--batch-size",
                    str(config.batch_size),
                    "--statement-timeout-ms",
                    str(config.statement_timeout_ms),
                ),
                label="refresh-prompt-embeddings",
            )
            result["embedding"] = "attempted"

        return result
    finally:
        if lock_handle is not None:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
            lock_handle.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh local analytics after cloud-prod shadow sync.")
    parser.add_argument("--execute", action="store_true", help="run real Docker/PostgreSQL commands")
    parser.add_argument(
        "--restore-from-db",
        help="copy local analytics tables such as analytics_prompt_* and analytics_user_profile_* from this database first",
    )
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument(
        "--full-mart",
        action="store_true",
        help="force a full Prompt Mart rebuild instead of the default incremental refresh",
    )
    parser.add_argument("--shadow-db", default="bot_db_prod_shadow")
    parser.add_argument("--postgres-container", default="allbot-postgres-prod-shadow-pg18")
    parser.add_argument("--postgres-user", default="postgres")
    parser.add_argument("--analytics-container", default="allbot-local-analytics-platform")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--vector-lock-path", type=Path, default=DEFAULT_VECTOR_LOCK_PATH)
    parser.add_argument("--statement-timeout-ms", type=int, default=3_600_000)
    parser.add_argument("--lm-studio-base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--model-key", default=DEFAULT_MODEL_KEY)
    parser.add_argument("--shadow-lock-timeout-seconds", type=int, default=12 * 60 * 60)
    return parser


def config_from_args(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(
        execute=bool(args.execute),
        restore_from_db=args.restore_from_db,
        batch_size=int(args.batch_size),
        mart_full=bool(args.full_mart),
        shadow_db=args.shadow_db,
        postgres_container=args.postgres_container,
        postgres_user=args.postgres_user,
        analytics_container=args.analytics_container,
        backup_root=args.backup_root,
        log_path=args.log_path,
        vector_lock_path=args.vector_lock_path,
        statement_timeout_ms=int(args.statement_timeout_ms),
        lm_studio_base_url=args.lm_studio_base_url,
        model_id=args.model_id,
        model_key=args.model_key,
        shadow_lock_timeout_seconds=int(args.shadow_lock_timeout_seconds),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_pipeline(config_from_args(args))
    except (PipelineError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
