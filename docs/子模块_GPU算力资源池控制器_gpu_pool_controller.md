# 子模块: GPU 算力资源池控制器 (GPU Pool Controller)

## 1. 目标与范围
本模块记录 AllBot 第一阶段 GPU 算力资源池方案：不用 K8s/K3s，先以 `SSH + Docker + 本地文件模型仓库 + registry:2 + dry-run Controller` 管理本地 4 台局域网 GPU 服务器，并以 RunPod Pods provider v0 承接云测试弹性 worker canary。

当前实现入口：
- 控制器包：`ops/gpu_pool_controller/`
- 默认配置：`ops/gpu_pool_controller/config/`
- CLI：`scripts/gpu_pool_controller.py`
- 本地镜像仓库 compose：`deploy/docker-compose-local-registry.yml`
- 本地镜像仓库管理脚本：`scripts/manage_local_registry.sh`
- RunPod provider：`ops/gpu_pool_controller/providers/runpod.py`
- RunPod worker 镜像入口：`remote_workers/Dockerfile.runpod`、`remote_workers/scripts/runpod_entrypoint.sh`
- RunPod 云测试 bootstrap：`remote_workers/scripts/runpod_bootstrap_from_git.sh`

第一阶段默认不批量接管生产 worker，不自动重启 GPU 节点或 ComfyUI，不自动同步大模型。所有危险动作都应先 dry-run。

RunPod Provider v0 当前只服务云测试前置闭环：用 1 个 RunPod Pod 替补 `cloud_prod_worker_04` 缺失的 `img2img,img2img_lora` 能力。它不属于局域网 SSH 资源池，不会出现在 `LanSshProvider.inventory_from_config()` 结果里，也不得触发本地 GPU 节点 SSH/Docker 操作。

## 2. 当前资源池口径
资源池只纳入可 SSH 管理的局域网 GPU 节点：
- `gpu-226` / `allbot-gpu-226` / `192.168.1.226`：1 x RTX 5090，宿主机 ComfyUI `8188`
- `gpu-177` / `allbot-gpu-177` / `192.168.1.177`：2 x RTX 5090，Docker ComfyUI `8188/8189`
- `gpu-252` / `allbot-gpu-252` / `192.168.1.252`：2 x RTX 4090 48G，Docker ComfyUI `8188/8189`
- `gpu-002` / `allbot-gpu-002` / `192.168.1.2`：2 x RTX 4090 48G，Docker ComfyUI `8188/8189`

无法 SSH 管理的 `remote_workers` 不属于本地动态 GPU 资源池；它们仍可作为外部静态 worker 存在。

资源池必须分清两层运行态，后续 planner、canary 和运维文档都按这个边界写：

| 层级 | 当前事实 | Controller v1 可做什么 |
| :--- | :--- | :--- |
| Worker Agent 层 | 本地主服务器上的 `cloud-prod-comfy-agent-*` 容器，负责 `pop/status/complete/heartbeat`、工作流 patch、上传回报 | 可通过 `enabled/draining/disabled` 控制接单，可重建 agent 容器，可上报 `node_id/gpu_index/runtime_profile` |
| ComfyUI Runtime 层 | 局域网 GPU 节点上的真实 ComfyUI。`gpu-226:8188` 是宿主机进程；`gpu-177/252/002` 是 `comfy0/comfy1` Docker 容器 | 第一阶段只盘点、canary、渲染计划；不默认重启、不默认替换、不把宿主机 runtime 当容器管理 |

因此，“GPU pool worker 新协议已生效”只表示 Worker Agent 层已支持 `agent_id`、控制键和 heartbeat 元数据，不表示所有 ComfyUI runtime 都已经容器化或可由 Controller 自动接管。尤其 `cloud_prod_worker_01` 对应 `gpu-226:8188` 的宿主机 ComfyUI，`POOL_IMAGE_REF` 只能作为期望 profile/镜像声明，不能当作当前 runtime 镜像事实。

## 3. 声明式配置
业务层后续主要改 `assignments.yml`：
- `nodes.yml`：节点、GPU、Comfy 实例、模型目录、worker 对应关系
- `task_profiles.yml`：任务类型、模型 bundle、workflow、custom node、最低显存、镜像引用
- `assignments.yml`：哪个 worker/节点支持哪些任务
- `model_bundles.yml`：已跑通模型包来源与版本，首版先记录 planned manifest

常用 dry-run：

```bash
python scripts/gpu_pool_controller.py inventory
python scripts/gpu_pool_controller.py plan
python scripts/gpu_pool_controller.py image-plan \
  --source-image workers_cloud-prod-comfy-agent-1:latest \
  --repository allbot/worker-agent \
  --tag "$(git rev-parse --short HEAD)"
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-plan \
  --assignment lan-002-8188-worker-06 \
  --profile video_basic \
  --host-port 8190
python scripts/gpu_pool_controller.py runtime-render \
  --assignment lan-002-8188-worker-06 \
  --profile video_basic \
  --host-port 8190
```

RunPod v0 dry-run / 只读命令：

```bash
python scripts/gpu_pool_controller.py runpod render-create \
  --task-type img2img_lora \
  --env cloud-test
python scripts/gpu_pool_controller.py runpod create-pod \
  --task-type img2img_lora \
  --env cloud-test
python scripts/gpu_pool_controller.py runpod validate-key
python scripts/gpu_pool_controller.py runpod list-pods
python scripts/gpu_pool_controller.py runpod reconcile-managed-pods
```

`render-create` 不需要 `RUNPOD_API_KEY`，只渲染 `POST /pods` 请求；`create-pod` 默认仍是 dry-run。真实 `create/start/stop/delete` 必须同时显式满足：

```dotenv
RUNPOD_DRY_RUN=false
RUNPOD_AUTOSCALER_ENABLED=true
RUNPOD_MAX_PODS_TOTAL=1
RUNPOD_MAX_PODS_PER_TYPE=1
```

并建议设置 `RUNPOD_PROJECTED_COST_PER_HR_IMG2IMG_LORA` 与 `RUNPOD_MAX_HOURLY_COST_USD` 形成小时成本门禁。所有 CLI 输出会脱敏 API key、agent token、R2 secret 和 presigned URL signature。

RunPod v0 创建 Pod 时默认不把本地 `.env.cloud.test` 中的 `AGENT_SECRET_TOKEN`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY` 明文写入 create JSON，而是引用 RunPod Secrets：

```dotenv
AGENT_SECRET_TOKEN={{ RUNPOD_SECRET_allbot_cloud_test_agent_secret_token }}
MINIO_ACCESS_KEY={{ RUNPOD_SECRET_allbot_cloud_test_r2_access_key }}
MINIO_SECRET_KEY={{ RUNPOD_SECRET_allbot_cloud_test_r2_secret_key }}
```

如未来 Secret 名称调整，可用 `RUNPOD_AGENT_SECRET_TOKEN_REF`、`RUNPOD_R2_ACCESS_KEY_REF`、`RUNPOD_R2_SECRET_KEY_REF` 覆盖引用字符串；`MINIO_ENDPOINT` 仍来自 `.env.cloud.test`，因为它不是密钥。2026-06-11 已同步 RunPod template `x750yt0uln` 的 `MINIO_ENDPOINT`，不再保留 UI 创建时的中文占位值。

RunPod REST `Pod` schema 没有 `uptimeSeconds` 字段，不要把字段缺失当作 `uptime=0` 作为 readiness 结论。排查 Pod 初始化时以 RunPod UI Telemetry、REST `publicIp`、REST `portMappings` 和 `runpodctl ssh info` 为主；官方文档说明 `portMappings` 为空表示 Pod 仍在初始化，绿色 Running 点只表示 Pod 处于期望运行状态，不代表容器和服务已经 ready。AllBot worker 的业务 ready 仍以云测试 Central `/system/workers` 出现 `runpod_test_img2img_lora_*` healthy heartbeat 为准。

2026-06-11 已完成一次云测试真实 RunPod Pod 前置闭环验证：使用 `yanwk/comfyui-boot:cu128-slim` 作为基础镜像、`dockerStartCmd` 注入 `remote_workers/scripts/runpod_bootstrap_from_git.sh`，不使用 RunPod Network Volume，创建 1 个 RTX 4090 Pod 后自动完成 `ComfyUI /system_stats ready -> remote relay /health ready -> comfy_agent heartbeat`。Central `/system/workers` 可看到 `runpod_test_img2img_lora_*`，状态为 `idle`，能力为 `img2img,img2img_lora`；验证后已 stop/delete Pod，`runpod list-pods` 确认无 orphan managed Pod。

本轮排查得到的 RunPod v0 启动约束：
- `runpod_bootstrap_from_git.sh` 必须把 `remote_workers/` 根目录加入 `PYTHONPATH`，否则 `comfy_agent/workflow_patcher.py` 无法 import `src.workflow_mapping_validation`。
- RunPod 不会自动展开 env 中的 `AGENT_ID=runpod_test_img2img_lora_${RUNPOD_POD_ID:-pending}`；bootstrap 需检测字面量占位并用 `RUNPOD_POD_ID`、`POD_ID` 或 `hostname` 生成唯一 agent id。
- `remote_relay` 当前以 `/health` 作为可靠 ready probe；本地代码已兼容 `/ready`，bootstrap 默认等 `/health`。
- RunPod REST / runpodctl 当前不提供稳定容器日志读取接口；UI Logs 或 SSH proxy 是主要现场取证入口。`ports=22/tcp` 的 direct TCP 可能映射出来但仍连接拒绝，不能把 direct SSH 当成自动化依赖。
- 诊断 canary 可开启 `RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE=true` 保留失败现场；真实生产扩容应在镜像稳定后关闭或缩短保留策略。

当前 real task canary 尚未完成。原因是 `yanwk/comfyui-boot:cu128-slim` 基础镜像只提供可启动 ComfyUI，未包含 AllBot `img2img_lora` workflow 所需的真实模型文件；现场只发现 workflow JSON，没有 `Qwen-Rapid-AIO-NSFW-v23.safetensors`、`qwen/YARN_1.0.safetensors` 等模型。下一步真实 3 任务 canary 前，必须把必要 checkpoint/LoRA/custom nodes 固化到 RunPod 镜像，或从 Hugging Face/R2 做可控热缓存；不得从本地主服务器或局域网 registry 跨公网拉大模型。

Comfy canary 会检查 `/system_stats`、`/queue`、`/object_info` 和最低显存，默认不提交真实任务：

```bash
python scripts/gpu_pool_controller.py canary --assignment lan-252-8188-worker-04
```

Runtime dry-run 命令：
- `runtime-plan` 输出 runtime / image / model bundle / worker env diff；不连接远端、不修改 worker。
- `runtime-render` 渲染标准 ComfyUI runtime compose；当前只支持 `docker_container`。
- `runtime-plan` / `runtime-render` 支持备用端口 canary 覆盖：`--host-port 8190` 会渲染 `8190:8188`、默认派生 `allbot-comfy-gpu0-canary`，并在 plan 中把 `COMFY_API_URL` / `COMFY_WS_URL` 指向备用端口；也可显式传 `--container-name`、`--api-url`、`--ws-url` 覆盖。
- `runtime-apply`、`switch-profile`、`rollback-profile` 已保留 CLI 接口；默认只输出 dry-run，传 `--execute` 会明确拒绝执行，直到 Phase 1 canary 和维护窗口完成。
- `gpu-226` 属于 `host_service`，只能观测和手工 canary；Controller 不得为它生成 Docker pull/up/restart 操作。
- 对 `host_service` 使用 `runtime-render` 或带备用端口覆盖的 `runtime-plan` 必须失败；这用于防止把 `gpu-226` 当 Docker runtime 处理。

Runtime schema 已补充到 `nodes.yml` 的每个 Comfy 实例：
- `comfy_runtime_kind`：`host_service` 或 `docker_container`
- `comfy_runtime_managed`：是否允许进入后续受控接管流程；当前只有 `gpu-002` 试点为 `true`
- `container_name`、`container_port`、`input_dir`、`output_dir`、`temp_dir`
- `compose_template`、`rollback_state`、`health`

`gpu-177` 与 `gpu-252` 仍可生成 Docker runtime 计划，但未标记为 managed；正式接管必须在 `gpu-002` 云测试 canary 通过后另行推进。

## 4. 本地仓库
模型仓库默认根目录：

```text
/srv/allbot/model-registry
  blobs/sha256/<prefix>/<sha256>
  bundles/<bundle>/<version>/manifest.yml
```

模型文件导入命令示例：

```bash
python scripts/gpu_pool_controller.py workflow-model-check
python scripts/gpu_pool_controller.py model-import-plan
python scripts/gpu_pool_controller.py model-import-execute

python scripts/gpu_pool_controller.py model-import \
  --bundle tiny_bundle \
  --version v1 \
  --source /path/to/model.safetensors \
  --relative-path loras/model.safetensors \
  --source-node allbot-gpu-252 \
  --profile img2img_lora
```

首轮 `model-import-plan/execute` 只导入运行时 workflow、LoRA 菜单和 Wan22 profile 实际引用的模型，不做四台 GPU 节点模型目录全量冷备。模型以 sha256 内容寻址写入 `/srv/allbot/model-registry/blobs/sha256/...`，bundle manifest 只引用 blob；同一模型被多个 bundle 使用时不会在仓库内复制多份。

镜像仓库默认根目录：

```text
/srv/allbot/docker-registry
```

镜像仓库同时绑定本机 loopback 和局域网地址：主服务器本机 push/pull 使用 `localhost:5000` 或 `127.0.0.1:5000`，GPU 节点后续 pull 使用 `192.168.1.115:5000`：

```bash
scripts/manage_local_registry.sh --dry-run
scripts/manage_local_registry.sh --execute
```

GPU 节点在拉取本地镜像前，仍需人工在维护窗口配置 Docker daemon 信任 `192.168.1.115:5000`。主服务器本机已可通过 loopback 推送镜像，不需要把 `192.168.1.115:5000` 加入本机 Docker daemon 的 insecure registry。

## 5. Central / Worker 控制协议
worker heartbeat 现在可选携带 GPU pool 元数据：
- `node_id`
- `provider`
- `gpu_index`
- `runtime_profile`
- `image_ref`
- `model_bundle_versions`
- `pool_managed`
- `worker_agent_managed`
- `comfy_runtime_kind`：`host_service` 或 `docker_container`
- `comfy_runtime_managed`：第一阶段 `gpu-226` 必须为 `false`；Docker Comfy 也只有在明确维护窗口内才允许执行变更

新 worker 在 `/api/agent/task/pop` 时会带 `agent_id`。Central 会读取 Redis 控制键判断该 worker 是否可接新单：
- `enabled`：可正常 pop
- `draining`：不再 pop 新任务，等待当前任务自然结束
- `disabled`：禁止接新任务

内部接口：
- `POST /api/agent/task/control/{agent_id}`：设置 `enabled/draining/disabled`
- `GET /api/agent/task/control/{agent_id}`：读取控制状态

这些接口使用现有 `AGENT_SECRET_TOKEN` 鉴权。旧 worker 不传 `agent_id` 时仍按旧逻辑取任务，保证灰度兼容。

2026-06-10 已在云测试环境验证该控制链路：Central API 支持 control route，测试 worker 重建后真实 `/pop` 会携带 `agent_id=cloud_worker_test_*`，`disabled` worker 不会接新任务。随后用 `cloud_worker_test_06/07` 验证了多 worker 控制与任务类型声明切换：两个 worker 可通过 compose 环境覆盖临时交换 `SUPPORTED_TASK_TYPES`，heartbeat 会同步上报 `node_id/gpu_index/runtime_profile/pool_managed`，控制态仍能拦截新 `/pop`。云正式后续更新必须同时升级 `cloud-central-api-prod` 与本地 `cloud-prod-comfy-agent-*` worker 镜像；正式 SOP 见 `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md` 的 “Agent control 正式灰度更新指南”。

## 6. 运维边界
- Controller v1 只负责声明、盘点、计划、canary 和命令渲染；不默认重启 worker、ComfyUI 或 GPU 节点。
- 切换任务类型的第一阶段对象是 Worker Agent 的 `SUPPORTED_TASK_TYPES` 与模型/工作流可用性声明；是否重建或替换 ComfyUI runtime 必须由 `comfy_runtime_kind` 决定。
- 对 `host_service` runtime 只允许生成人工操作建议，不生成 `docker restart/pull/up` 计划；`gpu-226` 不存在 `comfy0/comfy1`。
- 同步模型只允许写目标共享 `models` 目录，不碰 `input/output/temp/custom_nodes/workflows`。
- 双卡节点只操作目标实例；不要整机 reboot、无 service 名 `docker compose down/up` 或批量删除容器。
- RunPod 作为 `RunPodProvider v0` 接入同一 provider 边界，不把远程 Pod 加入本地 SSH 节点池；当前只允许云测试 `img2img_lora` canary，生产自动扩容不开启。
