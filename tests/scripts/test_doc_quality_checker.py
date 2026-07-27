from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "doc_quality_checker.py"


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _valid_fixture(root: Path) -> None:
    _write(root, "README.md", "# Fixture\n")
    _write(
        root,
        "AGENTS.md",
        "# Routes\n\nUse `sample-skill` for sample work.\n",
    )
    _write(
        root,
        ".codex/skills/sample-skill/SKILL.md",
        "---\nname: sample-skill\ndescription: sample\n---\n\n"
        "# Sample Skill\n\nRead `docs/system_architecture_report.md`.\n",
    )
    _write(
        root,
        "docs/skills/README.md",
        "# Skills\n\n| Skill | Purpose |\n| --- | --- |\n"
        "| `sample-skill` | sample work |\n",
    )
    for path in (
        "docs/system_architecture_report.md",
        "docs/子模块_任务调度_task_scheduler.md",
        "docs/子模块_中控API与节点通信_central_api.md",
        "docs/子模块_任务黄金路径回归清单_task_golden_path.md",
    ):
        _write(root, path, f"# {Path(path).stem}\n\nCurrent guidance.\n")
    _write(
        root,
        "docs/adr/0001-old.md",
        "# Old ADR\n\nStatus: Superseded by ADR 0002.\n",
    )
    _write(
        root,
        "docs/archive/README.md",
        "# Archive\n\nHistorical evidence; not current SOP.\n",
    )
    active_docs = [
        "docs/adr/0001-old.md",
        "docs/knowledge_base_audit_matrix.md",
        "docs/skills/README.md",
        "docs/system_architecture_report.md",
        "docs/子模块_中控API与节点通信_central_api.md",
        "docs/子模块_任务调度_task_scheduler.md",
        "docs/子模块_任务黄金路径回归清单_task_golden_path.md",
    ]
    rows = "\n".join(
        f"| `{path}` | purpose | source | current | on demand |"
        for path in active_docs
    )
    _write(
        root,
        "docs/knowledge_base_audit_matrix.md",
        "# Knowledge Base Audit Matrix\n\n"
        "## Active knowledge\n\n"
        "| Path | Purpose | Fact source | Status | Load when |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"{rows}\n",
    )


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_valid_layered_knowledge_base_passes(tmp_path: Path) -> None:
    _valid_fixture(tmp_path)

    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Doc quality check passed" in result.stdout


def test_unregistered_active_doc_and_duplicate_matrix_row_fail(tmp_path: Path) -> None:
    _valid_fixture(tmp_path)
    _write(tmp_path, "docs/unregistered.md", "# Missing\n")
    matrix = tmp_path / "docs/knowledge_base_audit_matrix.md"
    matrix.write_text(
        matrix.read_text(encoding="utf-8")
        + "| `docs/system_architecture_report.md` | duplicate | source | current | always |\n",
        encoding="utf-8",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "未登记活跃文档" in result.stdout
    assert "重复登记" in result.stdout


def test_missing_skill_routes_fail(tmp_path: Path) -> None:
    _valid_fixture(tmp_path)
    _write(tmp_path, "AGENTS.md", "# Routes\n")
    _write(tmp_path, "docs/skills/README.md", "# Skills\n")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "AGENTS.md 缺少 Skill 路由" in result.stdout
    assert "技能索引缺少 Skill" in result.stdout


def test_oversized_skill_and_changelog_matrix_fail(tmp_path: Path) -> None:
    _valid_fixture(tmp_path)
    _write(
        tmp_path,
        ".codex/skills/sample-skill/SKILL.md",
        "---\nname: sample-skill\ndescription: sample\n---\n# Sample\n"
        + ("x" * 20_100),
    )
    matrix = tmp_path / "docs/knowledge_base_audit_matrix.md"
    matrix.write_text(
        "# Knowledge Base Audit Matrix\n\n"
        "> 2026-07-27：本轮已修正某现场问题。\n\n"
        + matrix.read_text(encoding="utf-8").split("\n", 1)[1],
        encoding="utf-8",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "Skill 超过 16000 bytes" in result.stdout
    assert "审计矩阵包含逐日流水" in result.stdout


def test_broken_internal_markdown_link_fails(tmp_path: Path) -> None:
    _valid_fixture(tmp_path)
    _write(
        tmp_path,
        "docs/system_architecture_report.md",
        "# Architecture\n\nSee [missing](./missing.md).\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "Markdown 链接目标不存在" in result.stdout


def test_dated_runtime_fact_in_skill_fails(tmp_path: Path) -> None:
    _valid_fixture(tmp_path)
    skill = tmp_path / ".codex/skills/sample-skill/SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8")
        + "\n2026-07-27 已上线某个临时 Pod，当前地址固定不变。\n",
        encoding="utf-8",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "Skill 包含日期化运行态" in result.stdout


def test_context_packet_skill_requires_doc_route_and_validation(
    tmp_path: Path,
) -> None:
    _valid_fixture(tmp_path)
    _write(
        tmp_path,
        ".codex/skills/allbot-task-engine/SKILL.md",
        "---\nname: allbot-task-engine\ndescription: task\n---\n"
        "# Task Engine\n\nOnly prose, without routing or checks.\n",
    )
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\n`allbot-task-engine`\n",
        encoding="utf-8",
    )
    index = tmp_path / "docs/skills/README.md"
    index.write_text(
        index.read_text(encoding="utf-8")
        + "\n`allbot-task-engine`\n",
        encoding="utf-8",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "缺少按需文档路由" in result.stdout
    assert "缺少最小验证" in result.stdout


def test_oversized_active_doc_fails(tmp_path: Path) -> None:
    _valid_fixture(tmp_path)
    _write(
        tmp_path,
        "docs/system_architecture_report.md",
        "# Architecture\n\n" + ("stable contract\n" * 6_000),
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "活跃文档超过单文件预算" in result.stdout
