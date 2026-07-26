---
name: "allbot-lan-resource-manager"
description: "开发和维护本地主服务器的 LAN AIO 资源管理平台。修改 lan_resource_manager 的 FastAPI/Vue、Compose、局域网访问控制、状态聚合或网页单卡切换时必须使用。"
---

# AllBot LAN AIO Resource Manager

本技能覆盖 `lan_resource_manager/`。平台是现有 LAN AIO operator 的受限本地 UI，
不是第二套 fleet 实现。

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
- 容器重启后把本地未完成 UI operation 标记为 `interrupted`，只展示 operator
  ledger/history 的事实，不自动 recover 或续跑。

## 最小验证

```bash
python -m pytest -q lan_resource_manager/tests
cd lan_resource_manager/frontend
npm ci
npm test
npm run build
cd ..
docker compose --env-file .env.example -f compose.yml config --quiet
```

视觉变更继续用 Playwright Chromium 验收桌面和移动布局。开发和测试不得执行真实
GPU mutation；持久化启动只在代码进入目标主目录后进行。
