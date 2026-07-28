# 独立模块不可变发布

## 原则

发布资格由操作者的实际测试结果决定，系统不设置发布门禁。系统只保证：

1. 从操作者指定的完整 Git SHA 构建明确模块；
2. 部署精确 digest 到明确环境和目标；
3. 检查目标模块的执行结果；
4. 失败时只恢复该目标的上一 identity（migration 除外）。

发布器不读取 CI、Git diff、main ancestry、test evidence、approval、bundle、
其它模块状态或 GPU baseline。并发写入协调、focused tests、test 人工验收都
不是发布门禁。

## 模块目录与构建

事实源为 `deploy/module-catalog.json`。每项记录 adapter、build target、必要
base、repository、部署目标、环境支持和结果检查。模块独立构建、部署，不生成
全局 release index，也不因 changed paths 扩大集合。

```bash
python scripts/release.py build \
  --module payment-api \
  --sha <40位main-sha>
```

`--module` 可重复。发布器创建临时干净 worktree，用本机 buildx/GHCR 构建并
push，仅递归必要 base。已有同 SHA 产物时复用并返回精确 digest；外部镜像只
解析 digest。完整 SHA 是构建输入标识，不是 ancestry 门禁。

## 部署

```bash
python scripts/release.py deploy \
  --env test --module payment-api \
  --artifact ghcr.io/example/payment-api@sha256:<digest>
```

```bash
python scripts/release.py deploy \
  --env prod --module payment-api \
  --artifact ghcr.io/example/payment-api@sha256:<digest> --confirm-prod
```

一次只部署一个模块。prod 唯一资格确认是 `--confirm-prod`。test 不支持某模块
时只返回目标不可用，不产生 prod blocker。

GPU 还需 `--operator runpod|lan --slot <exact-slot>`。config/compose contract
只切换目标契约，消费者由操作者随后显式部署。migration 只运行指定 artifact。

`public-web` 的 test/prod 使用同一份环境中立 tar。Pages adapter 从 artifact
annotation 读取完整 Git SHA，在上传前按目标环境读取
`frontend/runtime-config.yml`，覆盖 tar 中的空占位
`allbot-runtime-config.js`，并向 Wrangler 传递 `--commit-hash`。上传后必须从
目标 canonical 域名回读 runtime script，确认完整 SHA、runtime revision、
API 域名和 Bot 用户名均与目标环境一致；未切换时部署失败并进入目标模块回滚。
测试与正式配置由 focused tests 固定为独立 mapping，禁止把 test API/Bot
注入正式 Pages，也禁止测试 Pages 回退到同源 `/api`。

## 状态与恢复

```bash
python scripts/release.py status --env prod --module payment-api
python scripts/release.py rollback \
  --env prod --module payment-api --confirm-prod
```

状态按环境和模块保存 current、previous、最近动作和结果。首次部署从 live
adapter 建立基线。部署失败自动尝试恢复 previous；migration 失败只报告并保留
现场，不自动 downgrade 或恢复备份。

旧 bundle、transaction、acceptance、failed batch 和 evidence 只作历史取证，
不能作为当前命令输入或阻断模块。
