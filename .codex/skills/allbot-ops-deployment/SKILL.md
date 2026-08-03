---
name: "allbot-ops-deployment"
description: "处理独立模块不可变构建、精确 digest 部署、目标回滚、迁移和 GPU/RunPod/LAN；生产 mutation 必须用户明确确认。"
---

# AllBot 模块发布

## 资料

| 场景 | 必读资料 |
| --- | --- |
| 模块构建、部署、状态、回滚 | `docs/子模块_Git不可变发布_git_immutable_release.md` |
| test/prod 拓扑 | 对应 cloud test/prod 控制面文档 |
| GPU/RunPod/LAN | GPU 控制器文档；LAN mutation 再加载 `allbot-lan-aio-operator` |
| Cloudflare Pages | `allbot-cloudflare-ops` |

## 发布模型

`deploy/module-catalog.json` 是独立模块目录，`scripts/release.py` 只有
`build/deploy/rollback/status`。构建必须明确 `--module` 和完整 SHA，只递归
必要 base；不读取 changed paths、CI、测试批准、release bundle、其它 track
或 GPU baseline。

控制面云构建可显式选择 Buildx builder、registry cache prefix 和 progress。
build-only base 使用 Dockerfile、显式 `build_inputs` 与上游精确 digest 的
内容身份，不跟随应用 SHA；最终业务产物仍用 SHA 并返回精确 digest。loopback
代理必须在 build 前拒绝。GitHub self-hosted workflow 只允许手动 protected
main，拒绝 PR/fork 和 GPU kind；GPU/ComfyUI 继续本地构建。

部署一次只替换一个模块的精确 `repository@sha256:digest`。test 人工验收是
操作者判断，不写成 prod 资格；prod 仅额外要求 `--confirm-prod`。模块没有
test 目标时可拒绝 test，但不阻断直接部署 prod。

## 构建前网络与缓存预检

- 在调用 `release.py build` 前先检查标准大小写 proxy 变量；不要把第一次构建失败
  当作代理探针。Buildx 使用容器网络，`127.0.0.1`、`localhost`、`::1` 对它指向
  构建容器自身。
- 若本机代理是 loopback URL，先用 `ss` 确认该端口监听非回环地址，再从 Docker
  `bridge` 网络动态读取 gateway，将同一 scheme/port 临时映射到 gateway；只为本次
  build 同时覆盖大小写 `HTTP_PROXY`/`HTTPS_PROXY`，保留原 `NO_PROXY`。禁止把代理
  地址写入 Git、镜像、发布状态或普通日志。若代理只监听回环，停止并报告，不盲等。
- `release.py build` 会先检查目标 tag：同一内容身份的 build-only base 直接复用；
  业务模块仍按完整 Git SHA 产出新 digest。只构建本次部署需要的明确模块，不为
  deploy、rollback 或重复部署重新 build。
- 共享 test/prod 禁止源码 bind mount、容器内改代码和热重载。代码变化必须生成新
  immutable digest，但这应是 BuildKit 增量构建：复用精确 base 和可用 layer/cache，
  只重做被 `COPY` 或依赖变化影响的层。开发机临时热重载不具备发布身份，不能拿来
  替代共享环境构建。

Compose 只重建目标 service；Pages 只更新目标项目；GPU 必须明确
`--operator runpod|lan --slot <exact-slot>`；config/compose contract 只切换
自身 active identity；migration 独立执行。
带 Worker 新协议的发布先部署向后兼容的 Central/Web API，再部署 Worker，最后
激活前端；回滚反向执行，不能让新 Worker 调用已经回滚的控制面接口。

## 结果与恢复

部署前读取目标 live identity，部署后执行 adapter 健康检查。失败只回滚目标
模块 previous identity并报告当前 identity；migration 失败保留现场，不自动
downgrade 或恢复备份。状态按 `env/module` 独立保存。
本地 state backend 保持兼容；持久 Runner workflow 使用目标机
`/var/lib/allbot/module-release-state/<env>/<module>/` 的原子 remote backend。
Environment secret 只能在批准 job 的 tmpfs 中短暂解码并在退出清理。

## 红线

- 读取本地凭据不授权环境 mutation，也不得输出秘密。
- prod、数据库、Cloudflare、RunPod、GPU/LAN mutation 必须用户明确要求。
- 禁止目标机 build、源码同步/bind mount、mutable tag、无目标 Compose
  mutation、跨 slot 批量操作。
- main 合入、focused tests 和 test 人工结果均不是发布器门禁。

## 最小验证

```bash
python -m pytest -q tests/ops/test_release_cli.py tests/ops/test_gpu_release_rollout.py
python scripts/doc_quality_checker.py
```
