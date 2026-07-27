# 旧远程 Worker 退役记录

2026-07-27，无法接入 Tailscale 的独立远程 GPU Worker/Relay 路径永久退役，
不保留回滚入口。删除内容包括根目录 `remote_workers/`、远程 relay、独立
venv/env 示例以及 Windows/Linux 启动器。

仍在使用的 GPU 镜像资产按当前职责迁移：

- LAN/RunPod worker bundle：`workers/runpod_runtime/`
- RunPod/LAN profile Dockerfile：`workers/runpod_profiles/`
- 镜像内路径：`/opt/allbot/runtime/runpod_worker`

当前执行池只由本地 Worker、LAN AIO 与 RunPod 组成。历史提交保留退役前实现，
活跃 Skill、文档、构建和测试不得再引用旧目录或旧远程 agent ID。
