---
name: "allbot-lan-resource-manager"
description: "开发和维护本地主服务器资源管理平台。修改 lan_resource_manager 的 FastAPI/Vue、LAN AIO、可信 main 构建、模块部署、生成维护、隔离 runner、Compose 或局域网访问控制时必须使用。"
---

# AllBot Local Resource Manager

本技能覆盖 `lan_resource_manager/`。平台同时提供受限 LAN AIO UI、A–H
集成/对齐 UI 与不可变模块发布 UI，不实现第二套 fleet、integration coordinator
或 release engine。

## 必读入口

1. `.codex/skills/allbot-lan-aio-operator/SKILL.md`
2. `.codex/skills/allbot-ops-deployment/SKILL.md`
3. `lan_resource_manager/README.md`
4. `docs/子模块_LAN_AIO本地资源管理平台_lan_resource_manager.md`

修改 Vue 时同时加载 `vue-best-practices`；修改行为或安全门禁时加载
`allbot-tdd`；交付时加载 `allbot-kb-auto-updater`。

## 固定边界

- 后端只能通过 `OperatorPort` 调用 `scripts/lan_aio_fleet_prod_ops.py` 的
  `list/status/takeover/recover`，不得调用 Dashboard 已废弃 slot API。
- 网页只允许 `catalog_ready + enabled + retargetable` 候选；其它候选可见但只读。
- 每次切换前必须重新跑目标槽 live status，并要求 state `passed`、预期 current
  未变化。空槽必须已经由 ledger 明确记录为 `intentionally_empty`。
- 一次只允许一个 mutation；不得自动 reconcile、强杀任务、自由执行 SSH/Docker、
  挂载 Docker Socket或暴露 env/密钥/原始命令输出。
- 无登录不等于无保护：必须保留 LAN CIDR、精确 bind IP、Trusted Host、Origin、
  JSON 与 CSRF 门禁。
- 容器重启后把未完成的 LAN/部署/维护 mutation 标记为 `interrupted`，只展示
  operator ledger/history 的事实，不自动 recover 或续跑；GitHub build 可按原
  SHA/run ID 恢复只读观察，但不得重复 dispatch。
- 构建只允许当前远端 main 精确 SHA；缺可信 CI 时 dispatch
  `control-plane-release.yml`，已有同 SHA 成功 CI 时可带固定 `main/full` 参数与
  上游 run ID 补跑 modular workflow。禁止 build-only 包。lightweight 或
  release-tooling main 不构建 bundle，部署候选沿 main 历史选择最近不可变 bundle。
  runner 必须通过已认证 `gh api` 解析 main，并从兼容的 run list 按 `headSha`
  过滤；不得依赖容器内匿名 `git ls-remote` 或特定新版 `gh --commit` 参数。
- 部署只允许 `deploy/release-policy.yml` 中一个完整独立模块组，并固定
  `release.py plan -> deploy`、短效 plan token、目标环境和精确 SHA。禁止
  `--skip-gate`、emergency、自由 service、任意 config apply、rollback/recover
  或 GPU execution。唯一 recover 例外是测试环境当前精确 SHA 的
  `--repair-rollback-materials`：必须由固定 dashboard 兼容入口核对实际运行
  digest，且不得 pull/up/stop/restart、进入维护或改 deployment state。
- Web 容器不得读取云 SSH、GitHub/GHCR 或 Pages 凭据。所有发布命令必须经过独立
  Unix socket runner 的动作和参数白名单；runner 同样不得挂载 Docker Socket。
  runner 镜像必须内置 digest-pinned Node 22 与 npm/npx，供发布器按前端 lockfile
  的精确 Wrangler 版本上传测试 Pages；npm cache 必须指向 runner 已有的精确可写
  release-cache volume，XDG config 同样不得回落到只读 home；不得依赖宿主 Node
  或临时安装系统包。Pages mutation 前必须先校验 canonical SHA 与 runtime
  revision；同 SHA 多条记录时必须按 canonical deployment ID 选定记录。完全
  匹配时复用现有成功部署，保证中断重试幂等。
  固定 SSH config 对同一 allowlisted 云主机最多尝试 4 次建连，并保留 bounded
  connect/server-alive 超时；不得因重试扩大 host、key 或环境范围。
  远端 SSH 状态不可用时只阻断对应环境操作并返回脱敏错误，main/CI/bundle/catalog
  继续局部展示，不得让一个环境探测清空整个部署页。发布 planner 读取远端
  `current.json` 时也必须区分明确的文件不存在与 SSH/权限故障；后者不得伪装成
  首次部署或缺失 schema-v2 基线。
- 手动维护只管理 `/var/lib/allbot/<env>/runtime/GENERATION_MAINTENANCE`。只允许
  平台解除自身 owner metadata 建立的维护；活动/恢复事务或未知 owner 必须阻断。
- 开发槽集成只允许固定调用 `auto_integrate_handoffs.py integrate-all --execute`：
  可收敛已被新 main 包含的 pending，以及被更新 main 超越的旧
  `deploying-test` 失败；冲突、CI、构建和当前 main 测试失败继续 fail closed。
  `lightweight` 与 `release-tooling` 在 main CI 通过后完成批次，不等待不存在的
  modular bundle，也不部署共享 test；runtime/operator 保持既有 bundle 流程。
  修复失败原因后只能以 `RETRY <batch>` 精确确认重试一个既有失败批次。
  集成没有 prod 参数。对齐只允许 `manage_ai_workspaces.py align-merged`，dirty、
  未初始化或尚未被 main 包含的槽必须原样保留并显示 blocker。
- 测试全模块部署只接受 release policy 中 test 可用模块组的精确全集，并以重复
  `--modules` 组成一次原子 `plan -> deploy`；这样共享 migration/config contract
  在完整集合内统一判断，不得逐模块用陈旧 artifact source SHA 重放全局 blocker。
  远端 artifact history 必须一次受限批量读取，禁止按历史条目反复新建 SSH。
  test catalog 中尚无运行基线的 artifact 必须由 policy 显式列入
  `initial_artifacts`；不得接受子集、任意 service 或泛化为 prod bulk deploy。
- GPU 正式候选准备只允许当前 main 和 `GPU BUILD <sha>`，固定调用
  `prepare_gpu_release_v2.py` 补齐 exact-SHA 镜像、attested manifest 与 bundle；
  不得创建 Pod、部署 prod、伪造 canary-verified 或覆盖不可变 tag。
- 测试配置漂移只允许 `TEST CONFIG <sha>`，固定调用
  `sync_test_release_config.py` 的 test `config-plan -> config-apply`；不得暴露 env
  选择、prod confirmation 或手动维护动作。
- 测试回滚材料修复只允许 `REPAIR TEST ROLLBACK <current-sha>`，先从测试状态重新
  确认 current SHA，再固定调用 test control-plane 的 dashboard
  `recover --repair-rollback-materials --execute` 兼容入口；不得提供 prod 对称入口。
- 构建不会自动部署。测试与正式部署均须重新生成计划并输入
  `TEST|PROD <module> <full-sha>`；正式执行仍固定 `--confirm-prod`。
- 页面问号固定打开 `/help.html`，覆盖完整流程、就绪判定和安全边界。

## 最小验证

```bash
python -m pytest -q lan_resource_manager/tests
python -m pytest -q tests/scripts/test_release_maintenance.py
cd lan_resource_manager/frontend
npm ci
npm test
npm run build
cd ..
docker compose --env-file .env.example -f compose.yml config --quiet
```

视觉变更继续用 Playwright Chromium 验收桌面和移动布局。开发和测试不得执行真实
GPU mutation；持久化启动只在代码进入目标主目录后进行。
