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
COMPAT_RELATIVE_PATH = Path("docs/compat_seam_exit_table.md")

HEADING_RE = re.compile(r"^(#{1,6})\s+.+$", re.MULTILINE)
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
MATRIX_PATH_RE = re.compile(r"^\|\s*`([^`]+\.md)`\s*\|", re.MULTILINE)
DATED_CHANGELOG_RE = re.compile(
    r"^>\s*20\d{2}-\d{2}-\d{2}.*(?:本轮|修复|新增|上线|部署|同步)",
    re.MULTILINE,
)
DATED_SKILL_FACT_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
ACTIVE_CHANGELOG_HEADING_RE = re.compile(
    r"^#{1,6}\s+.*(?:changelog|变更记录|更新记录|修改记录|逐日记录)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
SKILL_DESCRIPTION_RE = re.compile(
    r"^description:\s*[\"']?(.*?)[\"']?\s*$", re.MULTILINE
)
DOC_ROUTE_RE = re.compile(r"`docs/[^`\s]+\.md`")
VALIDATION_RE = re.compile(
    r"(?:最小验证|测试要求|验证清单|Validation Commands|交付格式)",
    re.IGNORECASE,
)
MIGRATED_KNOWLEDGE_PATHS = {
    "src/core/gallery_core_dependencies.py": "src/gallery_core_dependencies.py",
    "src/core/gallery_feed_queries.py": "src/services/gallery_feed_queries.py",
    "src/core/user_core_bindings.py": "src/user_core_bindings.py",
    "src/services/bot_task_service.py": (
        "src/services/task_service_entrypoints*.py / src/core/task_core.py"
    ),
}

RETIRED_KNOWLEDGE_PATHS = {
    "scripts/safe_deploy_cloud_prod.sh": (
        "scripts/release.py deploy --env prod --module <module> "
        "--artifact <exact-digest> --confirm-prod"
    ),
    "scripts/cleanup_cloud_test_for_prod.sh": (
        "scripts/release.py deploy --env test --module <module> "
        "--artifact <exact-digest>"
    ),
    "scripts/safe_deploy_cloud_test.sh": (
        "scripts/release.py deploy --env test --module <module> "
        "--artifact <exact-digest>"
    ),
    "scripts/update_cloud_test_with_maintenance.sh": (
        "scripts/release.py deploy --env test --module <module> "
        "--artifact <exact-digest>"
    ),
    "scripts/migrate_local_test_to_cloud_containers.sh": (
        "scripts/release.py deploy --env test --module <module> "
        "--artifact <exact-digest>"
    ),
    "scripts/update_cloud_prod_with_maintenance.sh": (
        "scripts/release.py deploy --env prod --module <module> "
        "--artifact <exact-digest> --confirm-prod"
    ),
    "scripts/lan_pornmaster_flux2_edit_aio_test.sh": (
        "scripts/lan_aio_fleet_prod_ops.py with an exact fleet slot"
    ),
}

MAX_SKILL_BYTES = 16_000
MAX_SKILL_LINE_LENGTH = 1_000
MAX_TOTAL_SKILL_BYTES = 140_000
MAX_MATRIX_BYTES = 35_000
MAX_ACTIVE_DOC_BYTES = 1_000_000
MAX_ACTIVE_DOC_FILE_BYTES = 75_000
MAX_SKILL_DESCRIPTION_CHARS = 600

# Frontmatter is the automatic trigger surface. Each tuple is an alternative
# phrase group; at least one phrase from every group must appear in that
# skill's description. This guards discoverability without forcing exact prose.
OPERATIONAL_DESCRIPTION_TRIGGER_GROUPS = {
    "ops-log-monitor": (
        ("不可用", "5xx", "超时", "告警"),
        ("日志", "health", "metrics", "trace"),
        ("只读", "不自动"),
    ),
    "allbot-ops-deployment": (
        ("部署", "回滚"),
        ("启停", "重启", "重建"),
        ("数据库", "Redis"),
        ("备份", "恢复", "灾备"),
        ("生产", "prod"),
    ),
    "allbot-task-engine": (
        ("pending", "running", "卡住"),
        ("Worker", "不接单"),
        ("队列", "zombie", "取消"),
    ),
    "allbot-cloudflare-ops": (
        ("DNS", "Tunnel"),
        ("404", "502", "TLS"),
        ("Access", "Pages", "R2"),
    ),
    "allbot-cloud-ssh": (
        ("SSH", "Permission denied"),
        ("超时", "拒绝连接", "断连"),
        ("主机密钥", "公钥", "known_hosts"),
    ),
    "allbot-lan-aio-operator": (
        ("OOM", "Xid"),
        ("不接单", "掉线", "容器停止"),
        ("takeover", "recover", "restart"),
    ),
    "allbot-gallery-storage": (
        ("R2", "预签", "CORS", "媒体 404"),
        ("投稿", "点赞", "点踩"),
    ),
    "allbot-local-media-archive": (
        ("NAS", "MinIO"),
        ("丢失", "恢复"),
        ("清理", "迁移"),
    ),
}

CURRENT_ENTRYPOINT_STALE_FACTS = {
    "单批次 main PR": "不可变 handoff + 本机 main 单写者，不创建 PR",
    "共享 test 只有一个写入者": "协调器不部署共享 test",
    "经 CI 构建 digest-pinned": "操作者从完整 SHA 显式构建目标模块",
    "先部署/验收云测试，再把同 SHA、同 digest 晋级正式": (
        "test/prod 各自显式选择精确 artifact"
    ),
    "在用户完成测试验收前，不得把测试环境变更直接同步到正式": (
        "发布器不消费测试资格；prod mutation 只依赖明确授权与精确目标"
    ),
}

CONTEXT_PACKET_SKILLS = {
    "allbot-billing-auth",
    "allbot-cloudflare-ops",
    "allbot-comfy-models",
    "allbot-concurrent-workspaces",
    "allbot-gallery-storage",
    "allbot-lan-aio-operator",
    "allbot-lan-resource-manager",
    "allbot-local-analytics-prompt-semantics",
    "allbot-ops-deployment",
    "allbot-qqcc-lazy-bot",
    "allbot-task-engine",
    "allbot-tg-fsm",
}


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
        size = path.stat().st_size
        total_bytes += size
        text = read_text(path)
        rel = relative(path, root)
        if size > MAX_ACTIVE_DOC_FILE_BYTES:
            errors.append(
                "活跃文档超过单文件预算: "
                f"{rel} ({size} > {MAX_ACTIVE_DOC_FILE_BYTES} bytes)"
            )
        if not text.strip():
            errors.append(f"文档为空: {rel}")
            continue
        if not text.splitlines()[0].strip().startswith("# "):
            errors.append(f"首行不是一级标题: {rel}")
        if not HEADING_RE.search(text):
            errors.append(f"未检测到 Markdown 标题: {rel}")
        if ACTIVE_CHANGELOG_HEADING_RE.search(text):
            errors.append(
                "活跃文档包含 Changelog/逐日记录；请迁入 docs/archive/: "
                f"{rel}"
            )

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
        text = read_text(path)
        match = SKILL_DESCRIPTION_RE.search(text)
        description = match.group(1).strip() if match else ""
        if not description:
            errors.append(f"Skill 缺少 frontmatter description: {relative(path, root)}")
        elif len(description) > MAX_SKILL_DESCRIPTION_CHARS:
            errors.append(
                "Skill description 过长: "
                f"{relative(path, root)} ({len(description)} > "
                f"{MAX_SKILL_DESCRIPTION_CHARS} chars)"
            )
        trigger_groups = OPERATIONAL_DESCRIPTION_TRIGGER_GROUPS.get(skill_name, ())
        for alternatives in trigger_groups:
            if not any(term.lower() in description.lower() for term in alternatives):
                errors.append(
                    "运维 Skill description 缺少用户意图触发词: "
                    f"{relative(path, root)} 需要包含 "
                    + " / ".join(alternatives)
                )
        max_line = max((len(line) for line in text.splitlines()), default=0)
        if max_line > MAX_SKILL_LINE_LENGTH:
            errors.append(
                f"Skill 存在超长行: {relative(path, root)} "
                f"({max_line} > {MAX_SKILL_LINE_LENGTH})"
            )
        if DATED_SKILL_FACT_RE.search(text):
            errors.append(
                "Skill 包含日期化运行态；请迁入专项文档、evidence 或 archive: "
                f"{relative(path, root)}"
            )
        if skill_name in CONTEXT_PACKET_SKILLS:
            if not DOC_ROUTE_RE.search(text):
                errors.append(
                    f"领域 Skill 缺少按需文档路由: {relative(path, root)}"
                )
            if not VALIDATION_RE.search(text):
                errors.append(
                    f"领域 Skill 缺少最小验证: {relative(path, root)}"
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
    for path in sorted(registered_paths):
        registered = (root / path).resolve()
        try:
            registered.relative_to(root.resolve())
        except ValueError:
            errors.append(f"审计矩阵登记路径越出仓库: {path}")
            continue
        if not registered.is_file():
            errors.append(f"审计矩阵登记路径不存在: {path}")

    for line in text.splitlines():
        if line.startswith("| `docs/archive/") or "| archived |" in line:
            errors.append(
                "审计矩阵不得登记归档材料: "
                f"{line.split('|')[1].strip()}"
            )


def verify_current_history_boundaries(root: Path, errors: list[str]) -> None:
    current_sources = list_active_docs(root)
    current_sources.extend(list_skill_files(root))
    for source in current_sources:
        text = read_text(source)
        for old_path, canonical_path in MIGRATED_KNOWLEDGE_PATHS.items():
            if old_path not in text:
                continue
            errors.append(
                "知识文档引用已迁移路径: "
                f"{relative(source, root)}: {old_path} -> {canonical_path}"
            )
        for retired_path, canonical_entrypoint in RETIRED_KNOWLEDGE_PATHS.items():
            if retired_path not in text:
                continue
            errors.append(
                "知识文档引用已退役入口: "
                f"{relative(source, root)}: {retired_path} -> "
                f"{canonical_entrypoint}"
            )

    compat = root / COMPAT_RELATIVE_PATH
    if compat.is_file():
        text = read_text(compat)
        required_fields = ("责任域", "运行时调用方", "最近复核")
        missing = [field for field in required_fields if field not in text]
        if missing:
            errors.append(
                "兼容退出表缺少当前责任字段: " + "、".join(missing)
            )


def verify_current_entrypoints(root: Path, errors: list[str]) -> None:
    entrypoints = (
        root / "README.md",
        root / "AGENTS.md",
        root / "docs/system_architecture_report.md",
        root / "docs/子模块_运维指南与容器管理_ops_deployment.md",
    )
    for source in entrypoints:
        if not source.is_file():
            continue
        text = read_text(source)
        for stale, canonical in CURRENT_ENTRYPOINT_STALE_FACTS.items():
            if stale in text:
                errors.append(
                    "当前知识入口包含已退役发布事实: "
                    f"{relative(source, root)}: {stale} -> {canonical}"
                )


def run(root: Path) -> list[str]:
    errors: list[str] = []
    verify_required_files(root, errors)
    verify_active_docs(root, errors)
    verify_internal_links(root, errors)
    verify_skill_routes(root, errors)
    verify_matrix(root, errors)
    verify_current_history_boundaries(root, errors)
    verify_current_entrypoints(root, errors)
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
