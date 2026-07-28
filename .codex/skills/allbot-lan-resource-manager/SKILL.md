---
name: "allbot-lan-resource-manager"
description: "开发和维护本地主服务器资源管理平台。修改 lan_resource_manager、LAN AIO、模块目录、隔离 runner 或局域网访问控制时必须使用。"
---

# AllBot Local Resource Manager

## 必读入口

1. `.codex/skills/allbot-lan-aio-operator/SKILL.md`
2. `.codex/skills/allbot-ops-deployment/SKILL.md`
3. `lan_resource_manager/README.md`
4. `docs/子模块_LAN_AIO本地资源管理平台_lan_resource_manager.md`

修改 Vue 同时加载 `vue-best-practices`；行为修改加载 `allbot-tdd`；知识变化
加载 `allbot-kb-auto-updater`。

## 固定边界

- 平台不实现第二套 fleet、main coordinator 或 release engine。
- LAN AIO 只能通过固定 operator 调用，一次一个 slot；不得自由 SSH/Docker、
  挂载 Docker Socket、自动 reconcile、跨槽批量操作或泄露 env/密钥。
- LAN Web 必须保留 CIDR、bind IP、Trusted Host、Origin、JSON 与 CSRF 限制。
- 开发槽集成只允许
  `auto_integrate_handoffs.py integrate-all --execute`；协调器只写 main，不查询
  CI、不构建、不部署。冲突记录 `needs-rebase` 后继续其它任务。
- 候选视图只展示当前 main 和 `deploy/module-catalog.json`，不查询 CI、
  bundle、change scope 或 test evidence，也不产生 blocker。
- 旧 plan-token/bulk-test/GitHub-build 发布 UI 已退役，runner 对这些动作返回
  `module_release_cli_required`。实际构建、部署、回滚和状态统一使用
  `scripts/release.py` 的四个明确命令。
- release runner 和 Web 容器不得读取或显示无关云/GitHub/GHCR/Pages 凭据。
- 容器重启后未完成的 mutation 标为 interrupted，不自动恢复或续跑。
- 生产、数据库、Cloudflare、RunPod、GPU/LAN mutation 仍需用户明确命令；
  资源平台只读能力不构成授权。

## 最小验证

```bash
python -m pytest -q lan_resource_manager/tests
python -m pytest -q tests/ops/test_auto_integrate_handoffs.py tests/ops/test_release_cli.py
python scripts/doc_quality_checker.py
```
