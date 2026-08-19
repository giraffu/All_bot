# 子模块：运维指南与容器管理（Ops & Deployment）

本文件是通用运维入口，只维护场景路由、事实源、授权和不可越过的恢复边界。
固定 IP、容器数量、当前 Pod/Worker、某次发布结果和一次性 canary 不属于这里。

## 1. 先按现象路由

| 现象或目标 | 先加载 | 当前事实源 |
| --- | --- | --- |
| 网站/Bot/Dashboard/API 不可用、5xx、超时、容器退出 | `ops-log-monitor` + `allbot-diagnosing-bugs` | release/config identity、health、logs、metrics、live service discovery |
| 构建、部署、回滚、查看模块状态 | `allbot-ops-deployment` | `deploy/module-catalog.json`、`scripts/release.py --help` |
| 启停、重启、重建 Compose/systemd 服务 | 本 Skill + 日志诊断 Skill | 目标环境 contract、active module state、live process/container |
| env/config/secret 投影 | 本 Skill | `deploy/env.schema.yml`、`deploy/service-env-contract.yml`、config/compose contract |
| Alembic、PostgreSQL/Redis 备份恢复或灾备 | 本 Skill + 数据恢复文档 | schema head、备份清单、restore 脚本和目标 live identity |
| 域名、DNS、Tunnel、Access、Pages、R2 公网 | `allbot-cloudflare-ops` | Cloudflare live API + origin health |
| SSH 失败 | `allbot-cloud-ssh` | `ssh -G`、TCP/握手/认证分段证据、云控制台 |
| 队列、Worker、任务卡住 | `allbot-task-engine` + 诊断 Skill | TaskRegistry、Central queue/status/workers、Worker/ComfyUI |
| GPU/RunPod/LAN | 本 Skill + 诊断 Skill | provider/catalog/ledger/live；LAN 单卡 mutation 加 `allbot-lan-aio-operator` |
| 本地分析、NAS/MinIO、R2 冷清理 | 对应本地分析/媒体归档 Skill | 专项代码、状态账本、live health |

日志、health、状态和只读数据库查询可以建立事实；它们不授权 restart、retry、
cancel、scale、迁移、删除或发布。

## 2. 事实源优先级

1. 代码与声明式配置：module catalog、Dockerfile、overlay、env/schema、service
   contract 和 operator config；
2. 构建/发布身份：完整 Git SHA、OCI revision、精确
   `repository@sha256:digest`、目标 active/previous state；
3. 运行现实：目标机/平台当前容器、systemd、health、Central/provider、数据库
   migration head 和 Cloudflare API；
4. 专项文档中的稳定 SOP；
5. archive/evidence 只用于追溯，不能覆盖以上当前事实。

文档中的 hostname、端口、profile、worker 数或时间点若与 live 不同，以声明式
配置和只读探测为准，并把文档标记为需要校准。

## 3. 授权矩阵

- 只读检查目标范围内的配置元数据、日志、health、release state 和远端状态，
  但不得输出 secret、完整 env、预签 URL 或私密用户数据。
- 写代码、提交分支和 handoff 不授权部署 test；“修 bug/验证配置”也不默认授权
  共享环境 mutation。
- test 部署、服务重启和测试数据库迁移必须是用户请求范围内的明确操作。
- prod、数据库、Cloudflare、RunPod/GPU/LAN、灾备切换、数据删除和凭据轮换
  必须由用户明确指定目标与动作；prod module deploy 还必须使用
  `--confirm-prod`。
- 一次授权不自动扩展到相邻模块、其它环境、其它 GPU/slot 或后续操作。

## 4. 不可变模块发布

`deploy/module-catalog.json` 是模块目录，`scripts/release.py` 是构建、部署、状态
和回滚的 canonical CLI：

```bash
python3 scripts/release.py build --module <module> --sha <40-char-sha>
python3 scripts/release.py deploy \
  --env <test|prod> --module <module> \
  --artifact <repository@sha256:digest> [--confirm-prod]
python3 scripts/release.py status --env <test|prod> --module <module>
python3 scripts/release.py rollback --env <test|prod> --module <module>
```

- build 必须来自完整 SHA 和明确模块；目标机只消费不可变 artifact，不 build、
  rsync 源码或使用源码 bind mount。
- deploy 一次只切目标模块，先读取 live identity，成功后回读 adapter health；
  失败只恢复该模块 previous identity。
- test 与 prod 分别选择 artifact，不存在由 CI/test evidence 自动批准或晋级
  prod 的链路。focused tests 与人工结果是操作者证据，不是 release CLI 门禁。
- migration、Pages、config/compose contract 和 GPU profile 是独立 catalog 目标或
  专项 operator，不由应用模块隐式扩张。
- 跨模块协议按兼容顺序逐个部署；不要使用“整栈重建”替代明确 rollout。

详细构建器、remote state、Pages/GPU adapter 与回滚语义读取
`docs/子模块_Git不可变发布_git_immutable_release.md` 和目标控制面文档。

## 5. 服务恢复与配置变更

服务异常先完成：环境/时间窗 → 当前 SHA/digest/config revision → health/log/依赖
分段 → 一个可证伪根因。只有用户授权恢复后才执行最小 mutation。

- restart/recreate 前记录目标容器或 unit、image digest、配置 revision、依赖状态
  和回滚命令；只触及目标 service。
- 同 digest 的 config revision 切换需要显式 recreate；不能假设普通 restart 会
  重载 Compose/env 投影。
- Compose 服务若在 `environment` 增加自身开关，必须显式合并公共运行环境；
  `ALLBOT_RELEASE_SHA`、`PYTHONUNBUFFERED` 与 `TZ` 不能因 YAML map 覆盖而丢失。
  发布验收同时核对 OCI revision、容器 `ALLBOT_RELEASE_SHA` 和精确 image digest。
- 不在容器内热改代码/config，不打印 `compose config` 或全量 `env` 到报告。
- 配置变更先通过 schema/service contract；secret 只进入受限文件/tmpfs/secret
  store，不进入 Git、命令回显或 release state。
- 重启后同时验证进程 health 与业务 smoke；“容器 running”不证明 DB、Redis、
  Central、R2 或外部 API 可用。

## 6. 数据库、Redis 与灾备

数据库/Redis 操作先读
`docs/子模块_容灾与持久化_database_recovery.md` 和目标环境控制面文档。

- migration 前确认目标、当前/目标 Alembic head、备份可读性、expand/contract
  顺序和旧代码兼容性。失败保留现场，不自动 downgrade 或恢复备份。
- restore 先在隔离目标验证清单、checksum/schema 和应用兼容；不得用“备份文件
  存在”代替可恢复性。
- Redis 队列/锁/registry 不是普通缓存。不得为解除卡住而直接 flush/delete；
  使用任务 runtime cleanup、取消、退款或专项恢复 seam。
- 云正式整体不可用时，本地接管只走
  `docs/子模块_本地正式灾备切换_local_prod_fallback.md`；灾备授权不等于允许
  丢弃云端新增写入或立即改 DNS。

## 7. 最小验证

代码/文档变更：

```bash
.venv/bin/python -m pytest -q \
  tests/ops/test_release_cli.py \
  tests/ops/test_runtime_env_contract.py \
  tests/ops/test_modular_images.py
python3 scripts/doc_quality_checker.py
```

实际 mutation 交付必须列出：授权原文、环境/模块/资源、变更前后精确 identity、
执行命令类别、health/业务 smoke、回滚对象和未验证运行态；不得把本地测试写成
已部署或把 dry-run 写成已执行。

旧版通用运维长文已归档到
`docs/archive/knowledge-base-changelog/ops_deployment_history_through_20260818.md`，
其中固定 IP、容器清单和旧发布规则只作历史证据。
