---
name: allbot-concurrent-workspaces
description: "管理 AllBot A-H 固定 worktree、不可变 handoff、needs-rebase 与轻量 main 单写者协调。"
---

# AllBot 并发工作区

## 资料

- claim/handoff：`docs/并发AI自动接单使用指南_auto_workspace_claim.md`
- 协调器：`docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md`
- 模块发布：`allbot-ops-deployment`

## 开发槽位

主目录写仓库任务先执行：

```bash
python scripts/manage_ai_workspaces.py claim --task <kebab-case-slug>
```

后续读取、修改、测试和 Git 只在返回的 A-H worktree。任务自行决定 focused
tests，提交并推送精确远端 head 后执行：

```bash
python scripts/manage_ai_workspaces.py handoff --slot <A-H>
```

handoff 成功入队后才释放槽位。功能槽位不得直接 push main，也不负责构建或
部署环境。

## main 单写者

`scripts/auto_integrate_handoffs.py integrate-all --execute` 持有进程锁，逐个：

1. 获取最新 `origin/main` 与 handoff 精确 head；
2. 拒绝被改写的远端 head；
3. 在临时 worktree 执行 `merge --no-ff`；
4. 无冲突直接 push main；并发前进则重新获取 main 后重试；
5. 内容冲突转入 `needs-rebase` 并继续下一个 pending。

协调器只协调 main 写入，不创建 PR、不运行/等待 CI、不组 batch、不构建产物、
不部署 test/prod。重启时 `integrating` 可恢复为 pending，completed 不重复合入。

## 冲突修订

`needs-rebase` 不自动重试。原槽位或新槽位从最新 main 重做，推送新 head 后：

```bash
python scripts/manage_ai_workspaces.py handoff \
  --slot <A-H> --supersedes <旧handoff-id>
```

新记录进入 pending，旧记录标记 superseded。禁止改写旧 handoff 分支/head。

## 最小验证

```bash
python -m pytest -q tests/ops/test_manage_ai_workspaces.py \
  tests/ops/test_auto_integrate_handoffs.py
```
