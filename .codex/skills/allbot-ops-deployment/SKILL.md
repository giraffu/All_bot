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

控制面镜像默认优先 SGP1 云 BuildKit，并显式传入已验证的远端 builder；CLI 的
空默认不代表推荐本机冷构建。Pages/contract 本地打包 OCI；GPU/LAN 按对应
operator、registry 和硬件约束选择 builder。
build-only base 使用 Dockerfile、显式 `build_inputs` 与上游精确 digest 的
内容身份，不跟随应用 SHA；最终业务产物仍用 SHA 并返回精确 digest。loopback
代理必须在 build 前拒绝。GitHub self-hosted workflow 只允许手动 protected
main，拒绝 PR/fork 和 GPU kind。GPU/ComfyUI 由 operator 直接调用
`release.py build`；受保护 Runner 内使用 `allbot-sgp1`。本地云构建默认通过
`allbot-do-sgp1-build` 登录，以 `actions` 运行；`deploy` 看不到 builder
不应回退本机。artifact 不授权 RunPod/LAN rollout。

部署一次只替换一个模块的精确 `repository@sha256:digest`。test 人工验收是
操作者判断，不写成 prod 资格；prod 仅额外要求 `--confirm-prod`。模块没有
test 目标时可拒绝 test，但不阻断直接部署 prod。

## 构建前网络与缓存预检

- 控制面 image 先检查 SGP1 builder；仅远端不健康、依赖无受控传输路径或用户明确
  要求时才回退本机，并说明原因。
- Worker artifact 不要求经过 GHCR；用户要求使用本地 registry 时仍可使用云
  builder：通过现有 SSH/Tailscale 管理链路，把云构建
  主机的非冲突 loopback registry 端口临时反向转发到本地 registry；本地发布进程与
  远端 BuildKit 必须用同一个 registry namespace/tag，分别验证 Registry API、
  push 后 manifest digest 和 OCI revision。通道只绑定远端 loopback，不新增公网监听、
  不复制源码、不在目标机 build。registry 大层传输与 BuildKit/Docker 控制面使用
  独立 SSH 会话，避免大层占满 multiplex 连接导致 build context 超时；结束后关闭
  通道。运行端若也不能直连 LAN registry，
  可在部署窗口建立同类 loopback 通道拉取同一 repository path 的精确 digest。
- 云主机 loopback 反向 registry 通道使用 `actions` 的 `network=host`
  builder `allbot-sgp1-host`；bridge 模式的 `allbot-sgp1` 看不到宿主 loopback。
  transport 别名不得改变精确 digest，也不得改坏共享 builder。
- 构建前检查大小写 proxy 变量和 builder daemon env；loopback 代理必须先证明容器
  可达，再按专题文档临时映射 Docker gateway。不得输出凭据、改坏共享 builder，
  或把代理写入 Git、镜像与发布状态。
- `release.py build` 会先检查目标 tag：同一内容身份的 build-only base 直接复用；
  业务模块仍按完整 Git SHA 产出新 digest。只构建本次部署需要的明确模块，不为
  deploy、rollback 或重复部署重新 build。
- registry cache 只优化性能。只有 manifest 已推送且 digest 可独立解析时，才可停止
  卡住的 cache export；否则构建不算成功。
- 共享 test/prod 禁止源码 bind mount、容器内改代码和热重载。代码变化必须生成新
  immutable digest，但这应是 BuildKit 增量构建：复用精确 base 和可用 layer/cache，
  只重做被 `COPY` 或依赖变化影响的层。开发机临时热重载不具备发布身份，不能拿来
  替代共享环境构建。

Compose 使用 `--force-recreate` 只重建目标 service，使同 digest 的配置 revision
切换也真正进入新容器；Pages 只更新目标项目；GPU 必须明确
`--operator runpod|lan --slot <exact-slot>`；config/compose contract 只切换
自身 active identity；migration 独立执行。
远端 `/etc/allbot/<env>.env` 保持 `root:root 600`；发布器通过 `sudo -n docker
compose` 读取它，不得为 deploy 用户放宽正式 env 权限。
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
