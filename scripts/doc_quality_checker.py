#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / 'docs'
README = ROOT / 'README.md'

DOC_LINK_RE = re.compile(r'\[[^\]]+\]\((\./docs/[^)#]+\.md)\)')
HEADING_RE = re.compile(r'^(#{1,6})\s+.+$', re.MULTILINE)


def list_root_docs() -> list[Path]:
    return sorted(p for p in DOCS_DIR.glob('*.md') if p.is_file())


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def verify_readme_links(errors: list[str]) -> None:
    text = read_text(README)
    for rel in DOC_LINK_RE.findall(text):
        target = (ROOT / rel[2:]).resolve()
        if not target.exists():
            errors.append(f'README 引用了不存在的文档: {rel}')


def verify_doc_files(errors: list[str]) -> None:
    docs = list_root_docs()
    if not docs:
        errors.append('docs/ 根目录下没有任何 Markdown 文档。')
        return

    for path in docs:
        text = read_text(path)
        if not text.strip():
            errors.append(f'文档为空: {path.relative_to(ROOT)}')
            continue
        first_line = text.splitlines()[0].strip()
        if not first_line.startswith('# '):
            errors.append(f'首行不是一级标题: {path.relative_to(ROOT)}')
        if len(HEADING_RE.findall(text)) == 0:
            errors.append(f'未检测到 Markdown 标题: {path.relative_to(ROOT)}')


def verify_special_docs(errors: list[str]) -> None:
    expected = [
        DOCS_DIR / 'system_architecture_report.md',
        DOCS_DIR / '子模块_任务调度_task_scheduler.md',
        DOCS_DIR / '子模块_中控API与节点通信_central_api.md',
        DOCS_DIR / '子模块_任务黄金路径回归清单_task_golden_path.md',
    ]
    for path in expected:
        if not path.exists():
            errors.append(f'缺少关键文档: {path.relative_to(ROOT)}')


def main() -> int:
    errors: list[str] = []
    verify_readme_links(errors)
    verify_doc_files(errors)
    verify_special_docs(errors)

    if errors:
        print('Doc quality check failed:')
        for item in errors:
            print(f'- {item}')
        return 1

    print('Doc quality check passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
