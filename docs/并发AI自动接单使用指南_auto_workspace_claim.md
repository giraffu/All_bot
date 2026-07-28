# 并发 AI 自动接单使用指南

用户直接在主目录提出写仓库需求。AI 会自动：

1. `claim --task <slug>` 取得 A–H 空槽；
2. 只在该 worktree 开发；
3. 自行决定 focused tests；
4. commit 并 push 任务分支；
5. `handoff --slot <A-H>` 冻结 branch/head/base SHA并释放槽位。

多个窗口可以同时开发，但不会拿到同一槽位。槽位释放后即能接新任务；协调器
按冻结的远端 identity 读取旧任务，不依赖槽位当前内容。

## 自动集成

用户级 timer 每次取一个 pending handoff，由唯一写者直接合并到最新 main。
它不创建 PR、不等待 CI、不构建产物，也不部署测试环境。

单个 handoff 冲突时进入 `needs-rebase`，后续任务继续集成。修复者基于最新
main 重做并用新 handoff 替代旧记录：

```bash
python scripts/manage_ai_workspaces.py handoff \
  --slot <A-H> --supersedes <旧handoff-id>
```

查看队列：

```bash
python scripts/auto_integrate_handoffs.py status
```

## 授权边界

A–H 可以只读真实配置、env、凭据、日志和远端状态，但不得泄露秘密。读到凭据
不授权 test/prod、Cloudflare、数据库或 GPU mutation。协调器只有 main 写权限，
没有环境部署接口。构建和部署由操作者之后明确执行。

A–H 全占用时停止，不回退主目录写代码。
