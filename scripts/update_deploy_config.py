#!/usr/bin/env python3
"""Atomically replace a target env and recreate only config consumers.

The script never prints values. It is deliberately independent from code
release: the current verified SHA/digests remain unchanged.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("allbot_release", ROOT / "scripts/release.py")
assert SPEC is not None and SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def affected_services(policy: Mapping[str, Any], changed_keys: set[str]) -> set[str]:
    services: set[str] = set()
    unknown = set(changed_keys)
    for rule in policy.get("rules", []):
        matched = {
            key
            for key in changed_keys
            if any(fnmatch.fnmatchcase(key, pattern) for pattern in rule.get("patterns", []))
        }
        if matched:
            services.update(rule.get("services", []))
            unknown -= matched
    if unknown:
        release_policy = release.load_structured_file(ROOT / "deploy/release-policy.yml")
        services.update(release_policy["all_services"])
    return services


def run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, input=input_text, text=True, capture_output=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("test", "prod"), required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--host")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-prod", action="store_true")
    args = parser.parse_args()
    try:
        if args.env == "prod" and args.execute and not args.confirm_prod:
            raise release.ReleaseError("production config update requires --confirm-prod")
        if args.execute:
            release.verify_operator_worktree_clean()
        source = Path(args.source)
        values = release.parse_env_file(source)
        revision = release.validate_environment(
            release.load_structured_file(ROOT / "deploy/env.schema.yml"),
            args.env,
            values,
        )
        host = args.host or release.ENVIRONMENT[args.env]["host"]
        target = release.ENVIRONMENT[args.env]["env_file"]
        old_result = run(["ssh", "-o", "BatchMode=yes", host, f"cat {target}"])
        if old_result.returncode != 0:
            raise release.ReleaseError("target environment file is unavailable")
        old_values: dict[str, str] = {}
        for raw in old_result.stdout.splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                old_values[line.split("=", 1)[0].removeprefix("export ").strip()] = line.split("=", 1)[1]
        changed = {
            key for key in set(values) | set(old_values) if values.get(key) != old_values.get(key)
        }
        services = affected_services(
            release.load_structured_file(ROOT / "deploy/config-impact.yml"), changed
        )
        print(json.dumps({
            "environment": args.env,
            "config_revision": revision,
            "changed_keys": sorted(changed),
            "services": sorted(services),
            "mode": "execute" if args.execute else "dry-run",
        }, indent=2, sort_keys=True))
        if not args.execute or not changed:
            return 0
        if "worker" in services or "web-static" in services:
            raise release.ReleaseError(
                "worker/Web config changes require their dedicated release operator after env replacement"
            )
        cloud_services = sorted(services & release.ENVIRONMENT[args.env]["available_services"])
        state_path = f"/var/lib/allbot/deployments/{args.env}/current.json"
        state_result = run(["ssh", "-o", "BatchMode=yes", host, f"cat {state_path}"])
        if state_result.returncode != 0:
            raise release.ReleaseError("current immutable deployment state is unavailable")
        state = json.loads(state_result.stdout)
        sha = release.validate_full_sha(str(state.get("git_sha", "")))
        checkout = f"/home/deploy/APP/All_bot-release/releases/{sha}"
        release_env = f"/var/lib/allbot/releases/{sha}/release.env"
        overlay = release.ENVIRONMENT[args.env]["overlay"]
        project = release.ENVIRONMENT[args.env]["project"]
        temp = target + ".next"
        upload = run(
            ["ssh", "-o", "BatchMode=yes", host, f"umask 077; cat > {shlex.quote(temp)}"],
            input_text=source.read_text(encoding="utf-8"),
        )
        if upload.returncode != 0:
            raise release.ReleaseError("config upload failed")
        service_args = " ".join(shlex.quote(item) for item in cloud_services)
        command = f"""set -euo pipefail
stamp=$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 700 /etc/allbot/backups
cp {shlex.quote(target)} /etc/allbot/backups/{args.env}.env.$stamp
cp {release_env} /etc/allbot/backups/{args.env}.release.env.$stamp
chmod 600 {shlex.quote(temp)}
chown deploy:deploy {shlex.quote(temp)}
mv -f {shlex.quote(temp)} {shlex.quote(target)}
sed 's/^ALLBOT_CONFIG_REVISION=.*/ALLBOT_CONFIG_REVISION={revision}/' {release_env} > {release_env}.next
mv -f {release_env}.next {release_env}
compose='docker compose --project-name {project} --env-file {checkout}/deploy/env.defaults --env-file {target} --env-file {release_env} -f {checkout}/deploy/docker-compose-cloud-base.yml -f {checkout}/{overlay}'
if ! $compose config -q || ! $compose up -d --no-deps {service_args}; then
  cp /etc/allbot/backups/{args.env}.env.$stamp {shlex.quote(target)}
  cp /etc/allbot/backups/{args.env}.release.env.$stamp {release_env}
  chmod 600 {shlex.quote(target)}
  chown deploy:deploy {shlex.quote(target)}
  exit 1
fi
install -d -m 755 /var/lib/allbot/config/{args.env}
printf '%s\n' {shlex.quote(revision)} > /var/lib/allbot/config/{args.env}/current_revision
python -c 'import json,sys; p=sys.argv[1]; r=sys.argv[2]; d=json.load(open(p)); d["config_revision"]=r; t=p+".tmp"; open(t,"w").write(json.dumps(d,sort_keys=True,indent=2)+"\\n"); __import__("os").replace(t,p)' {state_path} {revision}
"""
        result = run(["ssh", "-o", "BatchMode=yes", host, "bash -s"], input_text=command)
        if result.returncode != 0:
            raise release.ReleaseError("config activation failed; previous env was restored")
        return 0
    except (release.ReleaseError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
