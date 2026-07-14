# ADR 0004: 三发布链与模块化薄镜像

日期：2026-07-15

## Status

Accepted；schema v2、薄镜像与 GPU baked runtime 已进入代码基线。正式晋级仍需云测试逐模块验收，本文不授权正式部署或 legacy 执行面下线。

## Context

schema v1 将多个控制面进程装入 `allbot-app`、将 Agent/Relay 装入同一个 Worker 镜像，并把 Dashboard/QQCC 两套后端和前端分别复用同一镜像。任何局部修改都会重建和拉取大范围产物，也无法单独证明某个正式模块运行的是云测试验证过的 digest。RunPod profile 还会在启动时 clone 可变 `deploy` 分支，使镜像 digest 不能完整代表 agent/workflow 运行闭包。

控制面、测试 Worker/Relay 与正式 GPU profile 的变更频率、验收证据和回滚对象不同。通用 Worker smoke 也不能证明目标 ComfyUI/profile/model manifest 在指定 GPU 上可运行。

## Decision

- 发布域固定为 `control-plane`、`test-execution`、`gpu-execution`。`release-index.json` 引用三份环境无关 manifest；test/prod 只选择 artifact 并注入配置。
- Python 使用不含业务源码的 `allbot-python-runtime-base`；测试 Agent 另有 `allbot-python-worker-base`。每个控制面服务、Agent、Relay 和两套前端分别产生不可变镜像。Public Web 仍是一份带 SHA256 的 tar。
- artifact 保存自己的 source SHA、OCI revision、digest、base digest 与依赖闭包。未变化 artifact 可复用旧 digest；base digest 变化强制重建所有后代。
- 正式逐模块晋级只接受云测试 verified record 中同名、同 digest 的 artifact；共享协议、迁移或依赖分析可以扩大原子集合，显式选择不能缩小它。
- Agent/Relay 只属于测试执行链。正式 legacy Relay 是否下线由只读运行态审计决定，不由控制面 release 隐式处理。
- RunPod/LAN profile 镜像烘焙 `remote_workers` agent 和 workflow，并写 agent/workflow revision label；启动时不再 clone AllBot 分支。模型继续外置，但 GPU manifest 固定 object key、size 与 SHA256。
- 每个变化的 GPU profile 必须独立 canary，证据至少包含真实镜像 digest、baked revisions、model checksum、Central task type、输入下载、输出上传、终态回流和回滚演练。

## Alternatives Considered

- 继续共享大镜像，仅增加更多 tag：tag 无法提供模块级依赖闭包和独立晋级证据。
- 每个环境分别构建：正式产物将不再是测试环境验证过的同一 digest。
- 只用通用测试 Worker 验证 GPU 改动：不能覆盖 ComfyUI nodes、目标显卡、workflow 与外置模型组合。
- RunPod 启动时按 Git SHA checkout：仍增加启动网络依赖，且实际容器文件不再只由镜像 digest 决定。

## Consequences

- 基础镜像、模块镜像与 GPU profile 有独立构建/缓存/回滚记录，局部发布的拉取量和风险面下降。
- 首次 v2 聚合需要三条链都有完整 artifact；GPU 输入变化会阻断控制面 bundle，直到逐 profile 构建和 canary 证据完成。
- Compose 与部署状态改为 track-scoped；旧 schema v1 状态只保留兼容读取，不再由 CI 发布。
- GPU 镜像增大一份 agent/workflow 源码体积，但不包含业务模型权重；运行时不再依赖 GitHub/`deploy` 分支网络。

## References

- `deploy/release-artifacts-v2.json`
- `scripts/release_manifest_v2.py`
- `scripts/release.py`
- `scripts/gpu_profile_release_v2.py`
- `.github/workflows/modular-release-v2.yml`
- `docs/子模块_Git不可变发布_git_immutable_release.md`
