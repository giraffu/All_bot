---
name: "allbot-lan-resource-manager"
description: "开发和维护本地主服务器资源管理平台。修改 lan_resource_manager 的 FastAPI/Vue、LAN AIO、可信 main 构建、模块部署、生成维护、隔离 runner、Compose 或局域网访问控制时必须使用。"
---

# AllBot Local Resource Manager

本技能覆盖 `lan_resource_manager/`。平台同时提供受限 LAN AIO UI 与不可变模块发布
UI，不实现第二套 fleet 或 release engine。

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
- 部署只允许 `deploy/release-policy.yml` 中一个完整独立模块组，并固定
  `release.py plan -> deploy`、短效 plan token、目标环境和精确 SHA。禁止
  `--skip-gate`、emergency、自由 service、config apply、rollback/recover 或 GPU
  execution。
- Web 容器不得读取云 SSH、GitHub/GHCR 或 Pages 凭据。所有发布命令必须经过独立
  Unix socket runner 的动作和参数白名单；runner 同样不得挂载 Docker Socket。
- 手动维护只管理 `/var/lib/allbot/<env>/runtime/GENERATION_MAINTENANCE`。只允许
  平台解除自身 owner metadata 建立的维护；活动/恢复事务或未知 owner 必须阻断。
- 构建不会自动部署。测试与正式部署均须重新生成计划并输入
  `TEST|PROD <module> <full-sha>`；正式执行仍固定 `--confirm-prod`。

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
