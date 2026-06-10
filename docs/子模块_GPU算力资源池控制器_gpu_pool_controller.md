# 子模块: GPU 算力资源池控制器 (GPU Pool Controller)

## 1. 目标与范围
本模块记录 AllBot 第一阶段 GPU 算力资源池方案：不用 K8s/K3s，先以 `SSH + Docker + 本地文件模型仓库 + registry:2 + dry-run Controller` 管理本地 4 台局域网 GPU 服务器，并为后续 RunPod provider 预留边界。

当前实现入口：
- 控制器包：`ops/gpu_pool_controller/`
- 默认配置：`ops/gpu_pool_controller/config/`
- CLI：`scripts/gpu_pool_controller.py`
- 本地镜像仓库 compose：`deploy/docker-compose-local-registry.yml`
- 本地镜像仓库管理脚本：`scripts/manage_local_registry.sh`

第一阶段默认不批量接管生产 worker，不自动重启 GPU 节点或 ComfyUI，不自动同步大模型。所有危险动作都应先 dry-run。

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
```

Comfy canary 会检查 `/system_stats`、`/queue`、`/object_info` 和最低显存，默认不提交真实任务：

```bash
python scripts/gpu_pool_controller.py canary --assignment lan-252-8188-worker-04
```

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
- RunPod 后续作为 `RunPodProvider` 接入同一 planner/provider 边界，不把远程 Pod 加入本地 SSH 节点池。
