from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import company_operations_vault as vault_module


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "company_operations_vault.py"


def _write_json(path: Path, payload: dict[str, object], mode: int = 0o600) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(mode)


def _valid_vault(root: Path) -> None:
    root.mkdir(mode=0o700, parents=True)
    (root / "evidence").mkdir(mode=0o700)
    (root / "ledger").mkdir(mode=0o700)
    _write_json(root / "identity.json", {"company": {"legal_name": "Example Co"}})
    _write_json(
        root / "credentials.json",
        {"bank": {"password": "never-print-me"}, "alipay": {"password": "also-secret"}},
    )
    _write_json(root / "hardware-secrets.json", {"bank_token": {"pin": "123456"}})
    _write_json(root / "operations.json", {"tax": {"status": "pending"}})


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_check_accepts_private_vault_without_echoing_values(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _valid_vault(vault)

    result = _run("check", "--root", str(vault), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["files"] == {
        "credentials.json": "present",
        "hardware-secrets.json": "present",
        "identity.json": "present",
        "operations.json": "present",
    }
    assert "never-print-me" not in result.stdout
    assert "also-secret" not in result.stdout
    assert "123456" not in result.stdout


def test_check_rejects_group_readable_secret_file(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _valid_vault(vault)
    (vault / "credentials.json").chmod(0o640)

    result = _run("check", "--root", str(vault), "--json")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["issues"] == ["credentials.json must have mode 0600"]


def test_check_uses_xdg_config_home_by_default(tmp_path: Path) -> None:
    vault = tmp_path / "allbot" / "company-operations"
    _valid_vault(vault)
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path)

    result = _run("check", "--json", env=env)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["root"] == str(vault)


def test_check_rejects_symlinked_secret_file(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _valid_vault(vault)
    target = tmp_path / "external.json"
    _write_json(target, {"password": "outside"})
    (vault / "credentials.json").unlink()
    (vault / "credentials.json").symlink_to(target)

    result = _run("check", "--root", str(vault), "--json")

    assert result.returncode == 1
    assert json.loads(result.stdout)["issues"] == [
        "credentials.json must be a regular file, not a symlink"
    ]


def test_check_rejects_vault_owned_by_another_user(
    tmp_path: Path, monkeypatch
) -> None:
    vault = tmp_path / "vault"
    _valid_vault(vault)
    current_uid = os.geteuid()
    monkeypatch.setattr(vault_module.os, "geteuid", lambda: current_uid + 1)

    payload, returncode = vault_module.check(vault)

    assert returncode == 1
    assert "vault root must be owned by the current user" in payload["issues"]


def test_check_rejects_group_readable_nested_evidence(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _valid_vault(vault)
    evidence = vault / "evidence" / "receipt.pdf"
    evidence.write_bytes(b"not-a-real-pdf")
    evidence.chmod(0o640)

    result = _run("check", "--root", str(vault), "--json")

    assert result.returncode == 1
    assert json.loads(result.stdout)["issues"] == [
        "evidence/receipt.pdf must have mode 0600"
    ]
