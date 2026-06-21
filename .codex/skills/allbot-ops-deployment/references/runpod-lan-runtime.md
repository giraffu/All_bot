# RunPod 与 LAN AIO Runtime 细节

本文件用于承接低频、易过期的 RunPod / LAN AIO 操作记忆。执行任何 mutation 前，必须回到主技能、相关 docs、脚本 `--help`、Central `/system/workers` 和当前环境做复核。

## RunPod 手动池
- 日常入口优先使用 `scripts/runpod_prod_ops.sh status|up|add|enable|disable|restart|down|scale|canary|rollback`。
- wrapper 默认 dry-run；真实 mutation 需要 `--execute`、明确 profile，并满足生产确认规则。
- `add` 表示新增 slot，不应删除已有 Pod；`restart` 应走 RunPod 原生 restart，不用 stop/start 模拟。
- 判断是否可接单必须同时看 Pod 状态、worker heartbeat、agent control 和 `current_task_id/current_task_type`。
- RunPod profile 镜像入口可能复用已有 `remote_workers` bundle；怀疑 bundle 过旧时，先 disable，再诊断更新或重建。

## LAN AIO
- LAN AIO 操作应按单 slot 执行，禁止跨节点批量启用。
- 标准接管顺序：preflight -> registry/镜像准备 -> start disabled -> 验证 disabled heartbeat -> enable -> drain/观察 -> stop old。
- AIO compose 必须指向目标环境，正式环境不得混入 cloud-test、`user-data-test` 或测试 Central。
- AIO entrypoint 必须监管 ComfyUI、relay 和 agent；关键进程退出时应让容器退出并交给 Docker restart policy。
- 重启已接管 AIO 时，先把目标 agent control 置为 disabled，重启单 slot 容器，验证健康和 disabled heartbeat 后再恢复 enabled。

## 安全边界
- 不输出 `.env.cloud.prod`、RunPod API key、agent token、JWT、R2 key、presigned URL 或 `docker compose config` 敏感内容。
- 生产 RunPod create/start/stop/restart/delete/add/scale 需要用户明确确认。
- Docker daemon、GPU 驱动、ComfyUI 服务级变更必须进入维护窗口。
