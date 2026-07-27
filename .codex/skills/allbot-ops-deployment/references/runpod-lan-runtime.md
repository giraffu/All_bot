# RunPod 与 LAN AIO Runtime 细节

本文件用于承接低频、易过期的 RunPod / LAN AIO 操作记忆。执行任何 mutation 前，必须回到主技能、相关 docs、脚本 `--help`、Central `/system/workers` 和当前环境做复核。

## RunPod 手动池
- 日常入口优先使用 `scripts/runpod_prod_ops.sh status|up|add|enable|disable|restart|down|scale|canary|rollback`。
- wrapper 默认 dry-run；真实 mutation 需要 `--execute`、明确 profile，并满足生产确认规则。
- `add` 表示新增 slot，不应删除已有 Pod；`restart` 应走 RunPod 原生 restart，不用 stop/start 模拟。
- 判断是否可接单必须同时看 Pod 状态、worker heartbeat、agent control 和 `current_task_id/current_task_type`。
- RunPod/LAN profile 镜像从 `workers/runpod_runtime/` 烘焙 worker bundle；怀疑 bundle 过旧时，先 disable，再按 release index 诊断或重建。
- 统一 RunPod create request 对后续 autoscaler/手动新建 Pod 注入深度 1 原子预接：`PREFETCH_ENABLED=true`、`PREFETCH_RESERVE_TASK=true`、`PREFETCH_DEPTH=1`、`PREFETCH_CONSUME_WAIT_SECONDS=10`，且 `PREFETCH_TASK_TYPES=SUPPORTED_TASK_TYPES`。该配置不回写存量 Pod；新 Pod 必须使用 `gpu-execution` track 验证过的 baked agent/workflow 镜像 digest，不能只靠环境变量让旧 Worker 获得预接实现，也不得在启动时 clone `deploy` 分支。
- 云正式 `image_to_video` / `wan22_video_v2` 只接受现网兼容 RIFE tag，或 canonical `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video@sha256:<64位小写十六进制>`；release rollout 与 exact rollback 都应传 digest，任意仓库、mutable tag、缩写或大写 digest 必须 fail closed。
- 云正式 Dashboard 的 operation 子进程必须用 catalog 中已验收的 img2img 与 PornMaster baked 镜像 ref 覆盖容器 `/app/.env` 的历史值；手动 add 与 autoscaler 共享该 pin。目标 tag 未发布、baked entrypoint 不可执行或 OCI/agent/workflow revision 不完整时，不得先部署引用它的 Dashboard。
- BF16 profile 同时承接 `pornmaster_flux2_edit_bf16` 与 `pornmaster_flux2_multi_edit_bf16`：分别复用 PornMaster single/multiple-edit API workflow，并由 BF16 patcher 切换 UNet 节点 100/9；不可变 prod Dashboard overlay 必须注入 `RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT`，镜像 smoke 必须检查两份 workflow、mapping 与解析表同时存在。
- `pornmaster_flux2_edit_bf16` 是 RTX 4090 profile，仅声明同名任务、固定 `--lowvram`、独立 model manifest；已纳入 Dashboard autoscaler，按同一套 add/down/restart/enable、锁定跳过、最短生命周期和冷却规则管理，默认单任务 30 秒、清空阈值 30 分钟。用临时分支验证 workflow 时要显式设置 `RUNPOD_BOOTSTRAP_GIT_BRANCH`，不是 `ALLBOT_RUNPOD_GIT_BRANCH`；创建后还必须从 RunPod Pod env 反查实际 `ALLBOT_RUNPOD_GIT_BRANCH`。
- 模型仓库已有源下载链接时，优先在云控制机/transfer Pod 流式写 R2；已存在的公用模型对象使用 R2 server-side multipart copy，禁止先下到本地再上传。
- `ltx_t2v` cloud-test canary 是独立 disabled profile，只承接 `ltx_t2v,ltx_t2v_ic`，固定 5090、180GB container disk、至少 100GB volume、禁用 template 和固定 manifest。必须先取得受保护 main 同一完整 SHA 的 `allbot-gpu-ltx-t2v` attestation/exact digest；transfer Pod 只传公开 dev FP8/Sulphur，Ingredients 从本地 registry 上传。两单 canary 后 disable/drain/delete，确认无 orphan/multipart；不得顺带创建正式 Pod、开启 autoscaler 或 feature flag。

### Dashboard 提供的 Pod SSH

- 连接参数只取自当次 RunPod Pod 页面：优先使用 `ssh.runpod.io` 的代理用户名；直连 TCP 地址/端口只在代理连续失败时作为后备。不要把 Pod ID、临时 IP、端口或现场状态写入 Git。
- 本机使用专用 RunPod debug 私钥。只读取文件名和权限来定位 `~/.ssh/allbot_runpod_debug_*`，不输出私钥内容；找不到或匹配不唯一时停止并请求操作员确认。
- 代理连接必须强制分配 PTY（`ssh -tt`）。该网关有时会在认证或 Pod shell 建立阶段短暂失败；用 `BatchMode=yes`、有限连接超时和最多三次重试。三次均失败才报告失败，不要跳过代理直接改 Pod 状态。
- 有些 RunPod 代理会忽略 SSH 尾随的远程命令。需要非交互式只读检查时，把命令通过标准输入送入该 PTY shell，并以 `exit` 收尾；先设置显式 `PATH`，因为容器的交互 shell 可能没有常规命令路径。

```bash
# RUNPOD_GATEWAY_USER 来自当次 Pod 页面；不要把它、Pod IP 或端口写入文档。
mapfile -t RUNPOD_SSH_KEYS < <(
  find ~/.ssh -maxdepth 1 -type f -name 'allbot_runpod_debug_*' ! -name '*.pub' -perm 600
)
test "${#RUNPOD_SSH_KEYS[@]}" -eq 1 || exit 2
RUNPOD_SSH_KEY="${RUNPOD_SSH_KEYS[0]}"

# 代理不转发尾随命令时，命令由 stdin 送入交互 PTY；每次诊断都重试三次。
runpod_proxy_commands() {
  local attempt ssh_status
  for attempt in 1 2 3; do
    printf '%s\n' "$@" 'exit' | ssh -tt -o BatchMode=yes -o ConnectTimeout=20 \
      -i "$RUNPOD_SSH_KEY" "$RUNPOD_GATEWAY_USER@ssh.runpod.io"
    ssh_status=${PIPESTATUS[1]}
    test "$ssh_status" -eq 0 && return 0
    test "$attempt" -eq 3 && return "$ssh_status"
    sleep 2
  done
}

runpod_proxy_commands \
  'export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
  'df -hT' \
  'curl -fsS --max-time 5 http://127.0.0.1:8188/queue'
```

- SSH 成功后先只读核对 `df -hT`、ComfyUI `/queue`、`/system_stats`、Agent/relay 进程和目标目录占用；任何清理、重启、停用或 provider 操作仍须遵守主技能的生产授权与单 slot 边界。
- 代理通道不支持 SCP/SFTP。直连 TCP 若被拒绝，记录为网络/Pod 运行态信号；不要反复尝试错误私钥，也不要为了恢复 SSH 重启或释放 Pod。

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
