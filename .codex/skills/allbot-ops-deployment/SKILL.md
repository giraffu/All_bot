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
main，拒绝 PR/fork 和 GPU kind。GPU/ComfyUI 由 operator 直接调用
`release.py build`，可显式选择云端 `allbot-sgp1` Buildx builder；构建 artifact
不授权或触发任何 RunPod/LAN runtime rollout。

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
- 上述 build 环境变量只覆盖 Dockerfile 的 `RUN` 网络，不能保证 BuildKit daemon
  拉取 `FROM`、导入/导出 registry cache 和推送 manifest 时经过代理。容器型 builder
  必须同时通过 `docker buildx inspect <builder>` 核对 daemon 的大小写 proxy env；
  本机 loopback 代理可使用 `network=host` 的专用 builder，并在创建时写入
  `env.http_proxy`/`env.https_proxy`（以及大写变体）。不得临时改坏或删除其它任务共用
  builder；新建独立 builder，先 `--bootstrap`，再从容器配置回读 env。发布进程本身
  仍使用前述 Docker gateway URL，以通过 loopback 拒绝门禁并覆盖 build step。
- `release.py build` 会先检查目标 tag：同一内容身份的 build-only base 直接复用；
  业务模块仍按完整 Git SHA 产出新 digest。只构建本次部署需要的明确模块，不为
  deploy、rollback 或重复部署重新 build。
- registry `mode=max` cache 是后续热构建的性能优化，不是 artifact 身份。若业务
  manifest 已推送、可按精确 digest 独立解析，而 cache export 在有界观察期内持续无
  进展，可停止 cache export、记录本次缺少远端 cache，并部署已验证 digest；本机
  builder cache 仍可复用。若 manifest 尚未完成推送或 digest 不能独立验证，则不得把
  被中断的 build 当成成功产物。
- 共享 test/prod 禁止源码 bind mount、容器内改代码和热重载。代码变化必须生成新
  immutable digest，但这应是 BuildKit 增量构建：复用精确 base 和可用 layer/cache，
  只重做被 `COPY` 或依赖变化影响的层。开发机临时热重载不具备发布身份，不能拿来
  替代共享环境构建。

Compose 使用 `--force-recreate` 只重建目标 service，使同 digest 的配置 revision
切换也真正进入新容器；Pages 只更新目标项目；GPU 必须明确
`--operator runpod|lan --slot <exact-slot>`；config/compose contract 只切换
自身 active identity；migration 独立执行。
Compose image 默认只消费目标环境已激活的
`/var/lib/allbot/module-contracts/<env>/compose-contract/current`；契约缺失或文件
不完整时 fail closed，禁止静默使用目标机旧仓库副本。仅故障处置时可显式传
`--remote-root` 覆盖，并在恢复后回到 active contract。
Dashboard/QQCC 管理密码哈希必须由 config contract 校验为标准单 `$` bcrypt；
宿主 Compose env source 用单引号保护 `$`，禁止把旧式 `$$` 转义值投影到容器。
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
