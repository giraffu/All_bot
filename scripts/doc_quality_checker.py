#!/usr/bin/env python3
"""Validate the layered AllBot knowledge base.

The checker intentionally validates navigation and size budgets rather than
business prose. Runtime truth still belongs to code, focused tests, and explicit
read-only environment checks.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys
from urllib.parse import unquote


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
MATRIX_RELATIVE_PATH = Path("docs/knowledge_base_audit_matrix.md")
SKILL_INDEX_RELATIVE_PATH = Path("docs/skills/README.md")

HEADING_RE = re.compile(r"^(#{1,6})\s+.+$", re.MULTILINE)
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
MATRIX_PATH_RE = re.compile(r"^\|\s*`([^`]+\.md)`\s*\|", re.MULTILINE)
DATED_CHANGELOG_RE = re.compile(
    r"^>\s*20\d{2}-\d{2}-\d{2}.*(?:本轮|修复|新增|上线|部署|同步)",
    re.MULTILINE,
)

MAX_SKILL_BYTES = 20_000
MAX_SKILL_LINE_LENGTH = 1_000
MAX_TOTAL_SKILL_BYTES = 180_000
MAX_MATRIX_BYTES = 35_000
MAX_ACTIVE_DOC_BYTES = 1_050_000


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def list_active_docs(root: Path) -> list[Path]:
    docs_dir = root / "docs"
    if not docs_dir.exists():
        return []
    return sorted(
        path
        for path in docs_dir.rglob("*.md")
        if "archive" not in path.relative_to(docs_dir).parts
        and "release_evidence" not in path.relative_to(docs_dir).parts
    )


def list_skill_files(root: Path) -> list[Path]:
    return sorted((root / ".codex/skills").glob("*/SKILL.md"))


def verify_required_files(root: Path, errors: list[str]) -> None:
    expected = [
        root / "README.md",
        root / "AGENTS.md",
        root / MATRIX_RELATIVE_PATH,
        root / SKILL_INDEX_RELATIVE_PATH,
        root / "docs/system_architecture_report.md",
        root / "docs/子模块_任务调度_task_scheduler.md",
        root / "docs/子模块_中控API与节点通信_central_api.md",
        root / "docs/子模块_任务黄金路径回归清单_task_golden_path.md",
    ]
    for path in expected:
        if not path.is_file():
            errors.append(f"缺少关键知识文件: {relative(path, root)}")


def verify_active_docs(root: Path, errors: list[str]) -> None:
    docs = list_active_docs(root)
    if not docs:
        errors.append("docs/ 下没有活跃 Markdown 文档。")
        return

    total_bytes = 0
    for path in docs:
        total_bytes += path.stat().st_size
        text = read_text(path)
        rel = relative(path, root)
        if not text.strip():
            errors.append(f"文档为空: {rel}")
            continue
        if not text.splitlines()[0].strip().startswith("# "):
            errors.append(f"首行不是一级标题: {rel}")
        if not HEADING_RE.search(text):
            errors.append(f"未检测到 Markdown 标题: {rel}")

    if total_bytes > MAX_ACTIVE_DOC_BYTES:
        errors.append(
            "活跃文档超过体积预算: "
            f"{total_bytes} > {MAX_ACTIVE_DOC_BYTES} bytes"
        )


def _link_target(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().split()[0].strip("<>")
    if (
        not target
        or target.startswith(("#", "http://", "https://", "mailto:", "app://"))
    ):
        return None
    target = unquote(target.split("#", 1)[0])
    if not target or not target.endswith(".md"):
        return None
    return (source.parent / target).resolve()


def verify_internal_links(root: Path, errors: list[str]) -> None:
    sources = [root / "README.md", root / "AGENTS.md"]
    sources.extend(list_active_docs(root))
    sources.extend(list_skill_files(root))
    for source in sources:
        if not source.is_file():
            continue
        for raw_target in MARKDOWN_LINK_RE.findall(read_text(source)):
            target = _link_target(source, raw_target)
            if target is None:
                continue
            try:
                target.relative_to(root.resolve())
            except ValueError:
                errors.append(
                    "Markdown 链接越出仓库: "
                    f"{relative(source, root)} -> {raw_target}"
                )
                continue
            if not target.is_file():
                errors.append(
                    "Markdown 链接目标不存在: "
                    f"{relative(source, root)} -> {raw_target}"
                )


def verify_skill_routes(root: Path, errors: list[str]) -> None:
    agents = root / "AGENTS.md"
    skill_index = root / SKILL_INDEX_RELATIVE_PATH
    if not agents.is_file() or not skill_index.is_file():
        return

    agents_text = read_text(agents)
    index_text = read_text(skill_index)
    skill_files = list_skill_files(root)
    if not skill_files:
        errors.append(".codex/skills 下没有项目级 Skill。")
        return

    total_bytes = 0
    for path in skill_files:
        skill_name = path.parent.name
        size = path.stat().st_size
        total_bytes += size
        if skill_name not in agents_text:
            errors.append(f"AGENTS.md 缺少 Skill 路由: {skill_name}")
        if skill_name not in index_text:
            errors.append(f"技能索引缺少 Skill: {skill_name}")
        if size > MAX_SKILL_BYTES:
            errors.append(
                f"Skill 超过 {MAX_SKILL_BYTES} bytes: "
                f"{relative(path, root)} ({size})"
            )
        max_line = max((len(line) for line in read_text(path).splitlines()), default=0)
        if max_line > MAX_SKILL_LINE_LENGTH:
            errors.append(
                f"Skill 存在超长行: {relative(path, root)} "
                f"({max_line} > {MAX_SKILL_LINE_LENGTH})"
            )

    if total_bytes > MAX_TOTAL_SKILL_BYTES:
        errors.append(
            "Skill 总体积超过预算: "
            f"{total_bytes} > {MAX_TOTAL_SKILL_BYTES} bytes"
        )


def verify_matrix(root: Path, errors: list[str]) -> None:
    matrix = root / MATRIX_RELATIVE_PATH
    if not matrix.is_file():
        return
    text = read_text(matrix)
    size = matrix.stat().st_size
    if size > MAX_MATRIX_BYTES:
        errors.append(
            f"审计矩阵超过体积预算: {size} > {MAX_MATRIX_BYTES} bytes"
        )
    if DATED_CHANGELOG_RE.search(text):
        errors.append("审计矩阵包含逐日流水；请迁入 docs/archive/knowledge-base-changelog/")

    matrix_paths = MATRIX_PATH_RE.findall(text)
    counts = Counter(matrix_paths)
    for path, count in sorted(counts.items()):
        if count > 1:
            errors.append(f"审计矩阵重复登记: {path} ({count} rows)")

    active_paths = {relative(path, root) for path in list_active_docs(root)}
    registered_paths = set(matrix_paths)
    for path in sorted(active_paths - registered_paths):
        errors.append(f"审计矩阵未登记活跃文档: {path}")

    for line in text.splitlines():
        if not line.startswith("| `docs/archive/"):
            continue
        if "| current |" in line:
            errors.append(f"归档材料被标记为 current: {line.split('|')[1].strip()}")


def run(root: Path) -> list[str]:
    errors: list[str] = []
    verify_required_files(root, errors)
    verify_active_docs(root, errors)
    verify_internal_links(root, errors)
    verify_skill_routes(root, errors)
    verify_matrix(root, errors)
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="repository root; defaults to the checker repository",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    errors = run(root)
    if errors:
        print("Doc quality check failed:")
        for item in errors:
            print(f"- {item}")
        return 1
    print("Doc quality check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
