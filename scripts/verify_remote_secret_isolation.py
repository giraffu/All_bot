#!/usr/bin/env python3
"""Compare test/prod secrets with a remote HMAC challenge, never their values."""

from __future__ import annotations

import argparse
import base64
import hmac
import json
import re
import secrets
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence


DEFAULT_KEYS = ("AGENT_SECRET_TOKEN", "API_TOKEN", "AUTH_TOKEN")
REMOTE_PROGRAM = r"""
import hashlib,hmac,json,sys
path,challenge,*keys=sys.argv[1:]
values={}
for raw in open(path, encoding='utf-8'):
    line=raw.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key,value=line.split('=',1)
    values[key.strip()]=value.strip().strip('"').strip("'")
result={}
for key in keys:
    value=values.get(key,'')
    if not value:
        raise SystemExit('missing required secret key: '+key)
    result[key]=hmac.new(value.encode(), challenge.encode(), hashlib.sha256).hexdigest()
print(json.dumps(result,sort_keys=True))
"""


class IsolationError(RuntimeError):
    pass


def _remote_hmac(
    host: str, env_file: str, challenge: str, keys: Sequence[str]
) -> dict[str, str]:
    encoded = base64.b64encode(REMOTE_PROGRAM.encode()).decode("ascii")
    program = "exec(__import__('base64').b64decode('" + encoded + "').decode())"
    remote_command = " ".join(
        shlex.quote(value)
        for value in ("python3", "-c", program, env_file, challenge, *keys)
    )
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        host,
        remote_command,
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = result.stderr.strip().splitlines()
        raise IsolationError(detail[-1] if detail else "remote secret challenge failed")
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise IsolationError("remote secret challenge output is invalid") from exc
    if not isinstance(document, dict) or set(document) != set(keys):
        raise IsolationError("remote secret challenge output is incomplete")
    return {str(key): str(value) for key, value in document.items()}


def reused_keys(test: Mapping[str, str], prod: Mapping[str, str]) -> list[str]:
    if set(test) != set(prod):
        raise IsolationError("secret challenge key sets differ")
    return sorted(key for key in test if hmac.compare_digest(test[key], prod[key]))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-host", required=True)
    parser.add_argument("--prod-host", required=True)
    parser.add_argument("--test-env-file", default="/etc/allbot/test.env")
    parser.add_argument("--prod-env-file", default="/etc/allbot/prod.env")
    parser.add_argument("--key", action="append", dest="keys")
    args = parser.parse_args(argv)
    keys = tuple(dict.fromkeys(args.keys or DEFAULT_KEYS))
    if not keys or any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) for key in keys):
        print(
            "ERROR: secret key names must be uppercase environment keys",
            file=sys.stderr,
        )
        return 2
    challenge = secrets.token_hex(32)
    try:
        test = _remote_hmac(args.test_host, args.test_env_file, challenge, keys)
        prod = _remote_hmac(args.prod_host, args.prod_env_file, challenge, keys)
        reused = reused_keys(test, prod)
    except IsolationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"checked_keys": sorted(keys), "reused_keys": reused}, sort_keys=True
        )
    )
    return 2 if reused else 0


if __name__ == "__main__":
    raise SystemExit(main())
