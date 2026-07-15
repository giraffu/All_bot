# RunPod 与 LAN AIO Runtime 细节

本文件用于承接低频、易过期的 RunPod / LAN AIO 操作记忆。执行任何 mutation 前，必须回到主技能、相关 docs、脚本 `--help`、Central `/system/workers` 和当前环境做复核。

## RunPod 手动池
- 日常入口优先使用 `scripts/runpod_prod_ops.sh status|up|add|enable|disable|restart|down|scale|canary|rollback`。
- wrapper 默认 dry-run；真实 mutation 需要 `--execute`、明确 profile，并满足生产确认规则。
- `add` 表示新增 slot，不应删除已有 Pod；`restart` 应走 RunPod 原生 restart，不用 stop/start 模拟。
- 判断是否可接单必须同时看 Pod 状态、worker heartbeat、agent control 和 `current_task_id/current_task_type`。
- RunPod profile 镜像入口可能复用已有 `remote_workers` bundle；怀疑 bundle 过旧时，先 disable，再诊断更新或重建。
- 统一 RunPod create request 对后续 autoscaler/手动新建 Pod 注入深度 1 原子预接：`PREFETCH_ENABLED=true`、`PREFETCH_RESERVE_TASK=true`、`PREFETCH_DEPTH=1`、`PREFETCH_CONSUME_WAIT_SECONDS=10`，且 `PREFETCH_TASK_TYPES=SUPPORTED_TASK_TYPES`。该配置不回写存量 Pod；新 Pod 必须使用 `gpu-execution` track 验证过的 baked agent/workflow 镜像 digest，不能只靠环境变量让旧 Worker 获得预接实现，也不得在启动时 clone `deploy` 分支。
- `pornmaster_flux2_edit_bf16` 复用 PornMaster single-edit API workflow，并由 BF16 patcher 切换 UNet；不可变 prod Dashboard overlay 必须注入 `RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT`，镜像 smoke 必须检查 BF16 workflow、mapping 与解析表三者同时存在。
- `pornmaster_flux2_edit_bf16` 是 RTX 4090 profile，仅声明同名任务、固定 `--lowvram`、独立 model manifest；已纳入 Dashboard autoscaler，按同一套 add/down/restart/enable、锁定跳过、最短生命周期和冷却规则管理，默认单任务 30 秒、清空阈值 30 分钟。用临时分支验证 workflow 时要显式设置 `RUNPOD_BOOTSTRAP_GIT_BRANCH`，不是 `ALLBOT_RUNPOD_GIT_BRANCH`；创建后还必须从 RunPod Pod env 反查实际 `ALLBOT_RUNPOD_GIT_BRANCH`。
- 模型仓库已有源下载链接时，优先在云控制机/transfer Pod 流式写 R2；已存在的公用模型对象使用 R2 server-side multipart copy，禁止先下到本地再上传。

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
