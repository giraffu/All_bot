# A–H 并发开发与轻量 main 协调

A–H 保留独立 worktree、任务分支、不可变 handoff 和唯一 main 写者。协调器
解决的是并发写入顺序，不是 CI 或发布门禁。

```text
claim → 开发 → 自选 focused tests → commit/push
      → handoff(branch/head/base_sha) → 释放槽位
```

handoff 状态为 `pending`、`integrating`、`completed`、`needs-rebase`。

## 协调器

```bash
python scripts/auto_integrate_handoffs.py integrate-all --execute
```

协调器持有进程锁并逐个 fetch 最新 main 和精确远端 head，在临时 worktree
执行 `merge --no-ff`。push 前 main 若前进则重新 fetch/merge。内容冲突记录
冲突文件和当时 main SHA，转入 `needs-rebase`，然后继续后续 pending。

协调器不组 release batch、不创建或等待 PR、不运行或等待 CI、不分析 scope、
不构建 bundle、不部署 test。旧 failed batch 不阻断新队列。

## needs-rebase

冲突项不自动重试。原槽位或新槽位从最新 main 重做并产生新 head：

```bash
python scripts/manage_ai_workspaces.py handoff \
  --slot E --supersedes <旧handoff-id>
```

旧记录标记 superseded，新记录进入 pending。远端 head 漂移只拒绝当前 handoff。
协调器重启会恢复遗留 integrating；已是 main 祖先的 head 直接 completed。

构建和环境部署是操作者之后的独立动作，参见模块发布文档。
