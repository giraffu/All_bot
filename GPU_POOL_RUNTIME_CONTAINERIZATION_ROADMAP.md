# AllBot GPU Pool Runtime 容器化接管路线图

更新时间：2026-06-12
当前口径：Worker Agent 新协议、模型仓库、镜像仓库、Controller Phase 0 dry-run 能力、Phase 1A 备用端口 canary 渲染能力、Phase 1B 只读预检均已完成；RunPod Provider v0、云测试 worker Central 入口、RunPod 启动前 R2 模型同步、`allbot-model-cache` 模型缓存桶、Phase 1R RunPod 云测试真实 `img2img/img2img_lora` canary，以及 GHCR 公网 baked profile 镜像 canary 均已完成。尚未执行 `gpu-002` live canary。底层 ComfyUI Runtime 仍未全量纳入 Controller 自动接管。`POOL_IMAGE_REF`、本地 GPU profile 镜像、bundle 版本、`runtime-plan`、`runtime-render --host-port` 与 `runpod render-create` 输出均是目标声明或 dry-run / render 计划，不等于当前 ComfyUI Runtime 已经由对应镜像实际运行。

本文是后续更新的执行指南。任何实现者继续推进时，先按本文确认当前阶段、允许动作和验收条件，再修改代码或执行运维。

## 1. 当前状态快照

### 1.1 已完成

- Worker Agent 新协议已上线到 7 个正式 `cloud-prod-comfy-agent-*`：
  - `/api/agent/task/pop` 携带 `agent_id`
  - Central 支持 `enabled / draining / disabled`
  - heartbeat 上报 `node_id`、`gpu_index`、`runtime_profile`、`pool_managed`
  - relay `/ready` 可用于深度健康检查
- 云测试 `cloud_worker_test_06/07` 已验证 agent control 与任务类型声明切换。
- 本地模型仓库已建立在 `/srv/allbot/model-registry`，首轮 5 个 bundle manifest 已生成。
- 本地 Docker registry 已建立在 `/srv/allbot/docker-registry`，监听 `127.0.0.1:5000` 与 `192.168.1.115:5000`。
  - 2026-06-11 预检确认 registry 可访问。
  - 但 `allbot/comfy-cu130-video-basic:baseline` 与 `allbot/comfy-cu128-img2img:baseline` 当前未发布到 registry，仍是 Phase 1B live canary 阻断项。
- Controller Phase 0 已完成：
  - runtime schema 已落到 `ops/gpu_pool_controller/config/nodes.yml`
  - 新增 `ops/gpu_pool_controller/runtime.py`
  - 新增 CLI：`runtime-plan`、`runtime-render`、`runtime-apply`、`switch-profile`、`rollback-profile`
  - `gpu-226` 被识别为 `host_service`，禁止生成 Docker runtime 操作
  - `gpu-002` 标记为 Phase 1 试点 managed runtime
  - `runtime-apply/switch-profile/rollback-profile --execute` 当前会明确拒绝执行
  - focused tests：`python -m pytest tests/ops/test_gpu_pool_controller.py -q` 已覆盖 schema、diff、render、rollback 和 host_service guard
- 云测试 worker 6/7 已支持临时覆盖：
  - `CLOUD_TEST_WORKER_06/07_TASK_TYPES`
  - `CLOUD_TEST_WORKER_06/07_RUNTIME_PROFILE`
  - `CLOUD_TEST_WORKER_06/07_COMFY_API_URL`
  - `CLOUD_TEST_WORKER_06/07_COMFY_WS_URL`
- Controller Phase 1A 已完成：
  - `runtime-plan` / `runtime-render` 支持 `--host-port`、`--container-name`、`--api-url`、`--ws-url`
  - `--host-port` 与配置端口不同时进入 canary render 模式，默认派生 `*-canary` 容器名和 `canary-<port>` compose project 后缀
  - canary compose 会渲染备用 host port，例如 `8190:8188`，并在 labels / `x-allbot-runtime` 标记 `render_mode=canary`、`production_port_unchanged=true`
  - canary `runtime-plan` 会把 worker env 的 `COMFY_API_URL` / `COMFY_WS_URL` 默认指向 `http://<node.ip>:<host_port>` 与 `ws://<node.ip>:<host_port>/ws`
  - `host_service` 对 `runtime-render` 或带端口覆盖的 `runtime-plan` 一律失败，防止误操作 `gpu-226`
- Phase 1B 只读预检已完成：
  - focused tests 通过：`16 passed`
  - `gpu-002` worker 06 可生成 `video_basic` 的 `8190:8188` canary plan / compose
  - `gpu-002` worker 07 可生成 `img2img_lora` 的 `8191:8188` canary plan / compose
  - `gpu-226` host_service render guard 按预期失败
  - `gpu-002` 磁盘充足，生产 `8188/8189` 当前健康，备用 `8190/8191` 未监听
  - 预检时生产 `8188/8189` 队列非空，因此不得进入 live canary
- RunPod Provider v0 已完成：
  - CLI 入口：`python scripts/gpu_pool_controller.py runpod ...`
  - 支持 `validate-key`、`list-pods`、`get-pod`、`pod-readiness`、`render-create`、`reconcile-managed-pods`、`create-pod`、`start-pod`、`stop-pod`、`delete-pod`、`canary`
  - 默认 dry-run；真实 create/start/stop/delete 必须同时满足 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、`RUNPOD_MAX_PODS_TOTAL=1`、`RUNPOD_MAX_PODS_PER_TYPE=1` 和命令级 `--execute`
  - v0 只允许云测试 `img2img/img2img_lora` profile，总 Pod 与单类型 Pod 上限均为 1
  - `runpod` provider 不进入 LAN SSH inventory，不生成局域网 SSH/Docker 操作
  - 日志和 CLI JSON 输出会脱敏 API key、agent token、R2 secret、presigned URL signature
  - `runpod canary` 默认只做 dry-run 预检；真实执行会串起单 Pod 创建、readiness、RunPod worker heartbeat、临时禁用测试 worker、上传测试 PNG、三任务真实闭环、恢复 worker、删除 Pod 和 orphan 核验
- RunPod 云测试入口已准备：
  - worker Central hostname：`https://worker-central-test.aivison.it.com`
  - `task_types=img2img,img2img_lora`
  - `agent_id=runpod_test_img2img_lora_<pod_id>`
  - `POOL_PROVIDER=runpod`
  - `POOL_RUNTIME_PROFILE=img2img_lora`
  - `PIPELINE_MAX_RUNNING_TASKS=1`
  - `COMFY_API_URL=http://127.0.0.1:8188`
  - 结果/输入/模板测试桶仍固定为 R2 `user-data-test`
- RunPod 模型缓存前置已完成：
  - 正式可复用模型桶：`allbot-model-cache`
  - 当前 bundle prefix：`img2img_lora/2026-06-10`
  - manifest：`img2img_lora/2026-06-10/manifest.json`
  - 包含 Qwen Rapid AIO 主模型和当前图生图 qwen LoRA 全量清单
  - 主模型通过临时 RunPod transfer Pod 从 Hugging Face 链接云端转存到 R2，未占用本地主服务器上行带宽
  - LoRA 使用本地低带宽上传后统一发布 manifest
  - 临时 transfer Pod 已删除，最近一次 `runpod list-pods` 显示 `count=0`
- Phase 1R RunPod 云测试真实 canary 已完成：
  - 创建 1 个 RunPod Pod `if082v0w8eowow`，GPU 为 NVIDIA GeForce RTX 4090，镜像为 `yanwk/comfyui-boot:cu128-slim`，agent id 为 `runpod_test_img2img_lora_if082v0w8eowow`
  - R2 模型同步下载/校验 manifest 中 6 个文件，ComfyUI `/object_info` 可见主模型和 5 个 qwen LoRA
  - 云测试 Central 看到 RunPod worker healthy/idle，能力为 `img2img,img2img_lora`
  - 三个真实 Web 任务均由 RunPod worker pop、执行、上传到 `user-data-test`、Central `/complete` 成功、Web result 可读
  - canary 后已恢复临时禁用的云测试 worker，删除 RunPod Pod，`runpod list-pods count=0` 且 `reconcile-managed-pods managed_count=0`
- RunPod GHCR baked profile 镜像 canary 已完成：
  - 使用 `ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946` 作为公网可匿名 pull 的 RunPod image，镜像内 baked `ComfyUI-KJNodes`，Qwen checkpoint/LoRA 仍从 R2 manifest 热同步。
  - 创建 1 个 RunPod RTX 4090 Pod `ln61p9vk99sau7`，云测试 Central 注册 `runpod_test_img2img_lora_ln61p9vk99sau7`。
  - 关闭启动期 custom node runtime install：`RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false`、`RUNPOD_COMFY_KJNODES_ENABLED=false`；保持 `RUNPOD_MODEL_SYNC_ENABLED=true`。
  - 三个真实 Web 任务再次闭环成功，完成后删除 Pod，`runpod list-pods count=0` 且 `reconcile-managed-pods managed_count=0`。

### 1.2 当前 GPU 节点事实

| 节点 | GPU | 当前 Runtime | Controller 状态 | 当前 worker / profile |
| :--- | :--- | :--- | :--- | :--- |
| `gpu-226` / `192.168.1.226` | 1 x RTX 5090 32G | 宿主机进程 `8188` | `host_service`，`managed=false` | `cloud_prod_worker_01` / `face_i2i_t2i` |
| `gpu-177` / `192.168.1.177` | 2 x RTX 5090 32G | Docker `comfy0/comfy1`，`8188/8189` | `docker_container`，`managed=false` | worker 02=`video_basic`，worker 03=`ltx_video` |
| `gpu-252` / `192.168.1.252` | 原规划 2 x RTX 4090；当前只识别/可用 1 张 | Docker `comfy0/comfy1`，但 `comfy0`/`8188` 不通，`comfy1`/`8189` 正常 | `docker_container`，`managed=false`；worker 04 当前视为本地容量缺口 | worker 04=`img2img_lora` 不可执行，worker 05=`wan22_video_v2` 仍可用且不得改 |
| `gpu-002` / `192.168.1.2` | 2 x RTX 4090 48G | Docker `comfy0/comfy1`，`8188/8189` | `docker_container`，`managed=true` Phase 1 试点 | worker 06=`img2img_lora`，worker 07=`video_basic` |

关键边界：

- `gpu-226` 是最后迁移对象，不得对它执行 `docker restart comfy0` 或任何假设 Docker Comfy 存在的命令。
- `gpu-177/252` 可生成 dry-run 计划，但未标记为可执行接管；Phase 1 通过前不要推进。
- `gpu-252` 当前现场必须保护：不自动恢复 `comfy0`，不重启 `gpu-252`，不改 `comfy1` 或 `cloud_prod_worker_05`；保留 `worker_05` 临时状态 `POOL_GPU_INDEX=0`、`PIPELINE_MAX_RUNNING_TASKS=1`。
- Controller 和 RunPod 调度只把 `cloud_prod_worker_04` 视为 `img2img/img2img_lora` 本地容量缺口，不把它当可执行 runtime。
- `remote_workers` 不纳入本地动态 GPU 资源池。

### 1.3 2026-06-12 RunPod / R2 交接快照

本轮目标是先用 RunPod 云测试 Pod 替补 `cloud_prod_worker_04` 缺失的 `img2img,img2img_lora` 能力；生产自动扩容仍关闭。

已落地代码：

- `ops/gpu_pool_controller/providers/runpod.py`
  - RunPod Pods Provider v0。
  - create payload 会注入云测试 worker、R2 测试桶和 R2 模型缓存环境变量。
  - 模型缓存密钥使用 RunPod secret reference，不把本地 `.env.cloud.test` 里的明文写入 Pod env 渲染输出。
- `remote_workers/scripts/runpod_bootstrap_from_git.sh`
  - 启动顺序固定为：必要时启 SSH 诊断 -> 拉取/使用 remote worker bundle -> 安装依赖 -> R2 模型同步 -> 安装 ComfyUI custom nodes -> ComfyUI ready -> remote relay ready -> comfy agent。
  - 当前会在启动 ComfyUI 前默认安装 `ComfyUI-KJNodes`，用于提供 `img2img_lora` workflow 依赖的 `GetImageSizeAndCount` 等节点；可用 `RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false` 或 `RUNPOD_COMFY_KJNODES_ENABLED=false` 关闭。
- `remote_workers/scripts/runpod_sync_models_from_r2.py`
  - 从 R2 manifest 下载模型到 ComfyUI `models` 目录。
  - 校验 `size_bytes` 和 `sha256`，已有且校验通过的文件会跳过。
- `scripts/upload_model_bundle_to_r2.py`
  - 支持 `--include-pattern`、`--exclude-pattern`、`--skip-manifest`、`--max-concurrency`、`--max-bandwidth-mbps`。
  - 用于低带宽上传 LoRA，并在所有对象到位后发布 manifest。
- `scripts/transfer_url_to_r2.py`
  - 在云端把外部模型 URL 流式转存到 R2，不需要先落本地主服务器磁盘。
- `scripts/create_runpod_model_transfer_pod.py`
  - 创建一次性 RunPod transfer Pod，把 Hugging Face 主模型转存到 R2。
  - 使用 RunPod Secrets 引用 R2 模型桶凭据，不输出明文。
- `tests/ops/test_runpod_provider.py`
  - 覆盖 auth header、list/reconcile、create payload、dry-run gate、成本门禁、模型缓存 env 注入、脱敏、LAN SSH inventory 隔离。
- `tests/ops/test_runpod_bootstrap.py`
  - 覆盖 RunPod bootstrap Bash 语法，以及 `ComfyUI-KJNodes` 安装发生在 ComfyUI 启动前。

R2 模型缓存事实：

| 项 | 值 |
| :--- | :--- |
| bucket | `allbot-model-cache` |
| prefix | `img2img_lora/2026-06-10` |
| manifest | `img2img_lora/2026-06-10/manifest.json` |
| manifest size | `1969` bytes |
| multipart residue | `0` |
| 主模型对象 | `models/checkpoints/Qwen-Rapid-AIO-NSFW-v23.safetensors` |
| 主模型大小 | `28431840023` bytes |
| 主模型 sha256 | `fdb919fc81bea63f13759967fc92c9118142e5c70d4e6795199233a35eefa233` |

manifest 当前包含 6 个文件：

- `models/checkpoints/Qwen-Rapid-AIO-NSFW-v23.safetensors`
- `models/loras/qwen/YARN_1.0.safetensors`
- `models/loras/qwen/adjust_pussy_anus.safetensors`
- `models/loras/qwen/flat_chest_hairless.safetensors`
- `models/loras/qwen/penis.safetensors`
- `models/loras/qwen/realistic_texture.safetensors`

最近一次验证：

- `python -m py_compile scripts/create_runpod_model_transfer_pod.py scripts/upload_model_bundle_to_r2.py scripts/transfer_url_to_r2.py` 通过。
- `python -m pytest tests/ops/test_runpod_provider.py -q` 通过，结果为 `21 passed`。
- `python -m pytest tests/ops/test_runpod_provider.py tests/ops/test_runpod_bootstrap.py -q` 通过，结果为 `26 passed`。
- 临时 RunPod model-transfer Pod `btl8ae0ovggupf` 已删除；最近一次 `list-pods` 显示 `count=0`。
- R2 manifest 与主模型对象 metadata sha256 匹配，未发现 orphan multipart。
- 传输期间生产队列最高未超过用户给定的 `150` 中断阈值；完成后快照为 `queue_size=29`、`healthy_workers=8`、`error_workers=0`、`quarantined_workers=0`。
- 期间曾短暂出现 `cloud_prod_worker_02` ComfyUI WebSocket/health 抖动，后续恢复；不归因于 RunPod/R2 模型转存。

RunPod Secrets 当前应存在以下名字，文档和日志只记录名字，不记录值：

- `allbot_cloud_test_agent_secret_token`
- `allbot_cloud_test_r2_access_key`
- `allbot_cloud_test_r2_secret_key`
- `allbot_model_cache_r2_access_key`
- `allbot_model_cache_r2_secret_key`

下一窗口继续前先确认：

- `.env.cloud.test` 仍包含非明文输出的 RunPod/R2 配置引用。
- `.env.cloud.test` 默认使用 GHCR baked profile image：`RUNPOD_USE_TEMPLATE_IMG2IMG_LORA=false`、`RUNPOD_IMAGE_NAME_IMG2IMG_LORA=ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946`、`RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false`、`RUNPOD_COMFY_KJNODES_ENABLED=false`。
- `RUNPOD_MODEL_BUCKET=allbot-model-cache`
- `RUNPOD_MODEL_PREFIX=img2img_lora/2026-06-10`
- `RUNPOD_MODEL_MANIFEST_KEY=img2img_lora/2026-06-10/manifest.json`
- `RUNPOD_MODEL_SYNC_ENABLED=true`
- `RUNPOD_MODEL_ACCESS_KEY_REF={{ RUNPOD_SECRET_allbot_model_cache_r2_access_key }}`
- `RUNPOD_MODEL_SECRET_KEY_REF={{ RUNPOD_SECRET_allbot_model_cache_r2_secret_key }}`

### 1.4 2026-06-12 Phase 1R 真实 canary 结果

本轮只操作云测试和一次性 RunPod Pod；未改正式生产、未改 `gpu-252`、未执行 `gpu-002` live canary、未修改本地 GPU 节点 Docker/registry 信任。

预检结果：

- `python -m pytest tests/ops/test_runpod_provider.py -q`：`21 passed`
- `runpod validate-key`：通过
- `runpod list-pods`：创建前 `count=0`
- `runpod reconcile-managed-pods`：创建前 `managed_count=0`
- `runpod render-create --task-type img2img_lora --env cloud-test`：指向 `CENTRAL_API_URL=https://worker-central-test.aivison.it.com`、`MINIO_*_BUCKET=user-data-test`、`RUNPOD_MODEL_BUCKET=allbot-model-cache`、`RUNPOD_MODEL_PREFIX=img2img_lora/2026-06-10`、`RUNPOD_MODEL_MANIFEST_KEY=img2img_lora/2026-06-10/manifest.json`，secret 均为 RunPod secret reference / redacted。

Pod 与启动记录：

- Pod id：`if082v0w8eowow`
- Pod name：`allbot-runpod-test-img2img-lora`
- GPU：NVIDIA GeForce RTX 4090
- 镜像：`yanwk/comfyui-boot:cu128-slim`
- 创建时间：`2026-06-12 05:03:04 UTC`
- `pod-readiness`：基础设施 ready，network mapping confirmed
- 日志顺序：模型同步开始 -> 6 个 manifest 文件下载 -> `ComfyUI ready` -> `remote relay ready` -> `starting comfy agent`
- Central worker：`runpod_test_img2img_lora_if082v0w8eowow`，types 为 `img2img,img2img_lora`

现场发现与修复：

- 首个真实任务 `63e498eb-d7d1-4eda-9e10-cb3ddfd26394` 已由 RunPod pop，但 ComfyUI `/prompt` 400，错误为缺少 `GetImageSizeAndCount` 节点。
- 原因：RunPod 使用的是 `yanwk/comfyui-boot:cu128-slim` 基础镜像 + bootstrap + R2 模型同步；它不是本地 GPU 正式 ComfyUI runtime 镜像。R2 manifest 只同步模型文件，不同步 `custom_nodes/`。
- 现场确认 `GetImageSizeAndCount` 来自本地 GPU ComfyUI 已安装的 `ComfyUI-KJNodes`。
- 已在临时 Pod 内安装 `ComfyUI-KJNodes` 并重启 ComfyUI，`/object_info` 确认节点类和 6 个模型文件均可见。
- 已把 `ComfyUI-KJNodes` 安装步骤固化进 `remote_workers/scripts/runpod_bootstrap_from_git.sh`，并新增 `tests/ops/test_runpod_bootstrap.py` 防止回退。
- 对“生产已验证镜像能否直接用于 RunPod”做了只读/本地验证：`gpu-002` 生产 `comfy0` 实际 image 为 `yanwk/comfyui-boot:cu128-slim`，业务能力来自宿主机挂载的 `/data/comfy/inst0/custom_nodes`、`models`、`workflows` 等目录；本地 registry tag `localhost:5000/allbot/comfyui-boot:cu128-slim-gpu002-5daf3995` 与 `yanwk/comfyui-boot:cu128-slim` 是同一 image id，启动无挂载一次性容器检查得到 `KJNODES_PRESENT=false`。结论：当前没有可直接替代 RunPod 基础镜像的自包含 `img2img_lora` 生产镜像，后续需构建真正的 profile 镜像或继续在 bootstrap 中受控安装 custom nodes。

三任务结果：

| 用例 | registry_task_id | 任务类型 | LoRA | Central 终态 | Web result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| plain img2img | `744a6d0a-928f-438d-8644-4465fb64ecce` | `img2img` | 无 | `done` | `success`，`https://r2-test.aivison.it.com/history/744a6d0a-928f-438d-8644-4465fb64ecce/original.png` |
| YARN LoRA | `ae9ae529-b6be-44cb-8feb-999ec19a8448` | `img2img_lora` | `qwen/YARN_1.0.safetensors` | `done` | `success`，`https://r2-test.aivison.it.com/history/ae9ae529-b6be-44cb-8feb-999ec19a8448/original.png` |
| realistic texture LoRA | `52395689-9485-4f14-a2f5-5775d538842c` | `img2img_lora` | `qwen/realistic_texture.safetensors` | `done` | `success`，`https://r2-test.aivison.it.com/history/52395689-9485-4f14-a2f5-5775d538842c/original.png` |

收口结果：

- canary 期间曾临时将云测试 `cloud_worker_test_01..07` 置为 `disabled`，避免本地测试 worker 抢单；完成后已全部恢复 `enabled`。
- 删除 Pod 使用四重真实门禁：`RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、`RUNPOD_MAX_PODS_TOTAL=1`、`RUNPOD_MAX_PODS_PER_TYPE=1` 与 `--execute`。
- 删除后 `runpod list-pods` 显示 `count=0`，`reconcile-managed-pods` 显示 `managed_count=0`、无 orphan。
- 云测试 Central 队列归零；删除后短时间内 `/system/workers` 可能仍显示 RunPod 最后 heartbeat，属于观测 TTL，不代表 Pod 仍存在。

### 1.5 2026-06-12 GHCR baked profile 镜像 canary 结果

本轮验证“公网可拉取 profile 镜像 + R2 模型热同步”的 RunPod 路径；只操作云测试、GHCR 和一次性 RunPod Pod，未改正式生产、未改 `gpu-252`、未执行 `gpu-002` live canary、未修改本地 GPU 节点 Docker/registry 信任。

镜像构建与发布：

- 从 `allbot-gpu-002:/data/comfy/inst0/custom_nodes/ComfyUI-KJNodes` 只读复制 KJNodes 到 `/tmp/allbot-runpod-kjnodes`。
- KJNodes commit 校验为 `7967a946c296a74901606e6a8d1195aa2b6f9215`。
- 计划固定 tag `ghcr.io/giraffu/allbot-comfy-runpod-img2img-lora:20260612-kjnodes7967a946` 已 push，digest 为 `sha256:efe194eb2c88e5cc6e5e3231093bb21c49b95153f7405761dc0bb1460ea0e986`；但 GHCR 新 package 默认为 private，匿名 manifest 检查返回未授权。GitHub REST API 未能稳定切换 package visibility，因此未用该 private package 创建付费 Pod。
- 将同一 digest 作为 public alias 发布到已有 public package：`ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946`，匿名 manifest 检查通过。
- 镜像 smoke：存在 `/default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-KJNodes`，未包含 Qwen checkpoint/LoRA 业务模型文件；KJNodes 相比 base 只增加约 `56.3MB` 层，远端 linux/amd64 压缩 manifest 约 `5.96GiB`。

预检结果：

- `python -m pytest tests/ops/test_runpod_provider.py tests/ops/test_runpod_bootstrap.py -q`：`26 passed`
- `runpod validate-key`：通过
- `runpod list-pods`：创建前 `count=0`
- `runpod reconcile-managed-pods`：创建前 `managed_count=0`
- `runpod render-create --task-type img2img_lora --env cloud-test`：确认 imageName 为 GHCR public alias，`RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false`、`RUNPOD_COMFY_KJNODES_ENABLED=false`、`RUNPOD_MODEL_SYNC_ENABLED=true`，模型桶、prefix、manifest 和测试桶正确，secret 均为 RunPod secret reference / redacted。

Pod 与启动记录：

- Pod id：`ln61p9vk99sau7`
- Pod name：`allbot-runpod-test-img2img-lora`
- GPU：NVIDIA GeForce RTX 4090
- 数据中心：Secure Cloud `US-IL-1`
- 小时成本：`0.69/hr`
- 镜像：`ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946`
- 创建时间：`2026-06-12 08:08:40 UTC`
- `pod-readiness`：基础设施 ready，network mapping confirmed
- Central worker：`runpod_test_img2img_lora_ln61p9vk99sau7`，types 为 `img2img,img2img_lora`

三任务结果：

| 用例 | registry_task_id | 任务类型 | LoRA | Central 终态 | Web result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| plain img2img | `ad27719a-7efd-40e1-8f6a-cf1b2b435577` | `img2img` | 无 | `done` | `success`，`/history/ad27719a-7efd-40e1-8f6a-cf1b2b435577/original.png` |
| YARN LoRA | `ceb16956-069d-44b5-a7e0-b6e8b768e8f1` | `img2img_lora` | `qwen/YARN_1.0.safetensors` | `done` | `success`，`/3/output_images/ceb16956-069d-44b5-a7e0-b6e8b768e8f1.png` |
| realistic texture LoRA | `dd6d3391-0076-412e-a059-b2998a717335` | `img2img_lora` | `qwen/realistic_texture.safetensors` | `done` | `success`，`/history/dd6d3391-0076-412e-a059-b2998a717335/original.png` |

收口结果：

- canary 期间临时将云测试 `cloud_worker_test_01..07` 置为 `disabled`，避免本地测试 worker 抢单；完成后已全部恢复 `enabled`。
- 测试输入图为新上传的无敏感 `512x512` PNG：`user-data-test/web_uploads/3/20260612_7255e635.png`。
- 删除 Pod 使用四重真实门禁：`RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、`RUNPOD_MAX_PODS_TOTAL=1`、`RUNPOD_MAX_PODS_PER_TYPE=1` 与 `--execute`。
- 删除后 `runpod list-pods` 显示 `count=0`，`reconcile-managed-pods` 显示 `managed_count=0`、无 orphan。

现场约束：

- GHCR 新 package 默认 private；若后续必须使用 `ghcr.io/giraffu/allbot-comfy-runpod-img2img-lora:*` 独立 package，需要先在 GitHub Packages UI 将 package 调为 public，再创建付费 Pod。
- 当前 openSUSE base path 未提供 `apt-get`，bootstrap 的 sshd 自动安装分支不会生效；direct TCP SSH 可能映射但连接拒绝。RunPod worker heartbeat、Central 状态和任务闭环已证明业务 ready，后续若要依赖 SSH 取证，需要在 profile 镜像内补 `sshd` 或适配 zypper 安装。
- RunPod SSH 远程调试需要人工从 RunPod UI 提供当次 proxy SSH 信息；知识库不保存某次临时 Pod 的 SSH 用户名/IP/端口。SSH 只作为云测试 canary 或失败现场的短时诊断入口，生产路径不需要 SSH，也不应把 SSH 暴露作为生产 readiness 或自动扩容依赖。

## 2. 安全契约

默认允许：

- 读取配置、代码、文档、日志。
- 运行本地 dry-run 命令和 focused tests。
- 渲染 compose 到 stdout 或临时审阅文件。
- 对 Comfy `/system_stats`、`/queue`、`/object_info` 做只读 canary。

必须显式确认维护窗口后才允许：

- 配置 GPU 节点 Docker daemon 信任 `192.168.1.115:5000` insecure registry。
- 在 GPU 节点 pull/build 镜像。
- 停止、替换、重启任何 ComfyUI runtime 容器。
- 重建或替换任何生产 worker。
- 执行真实 profile switch 或 rollback。

RunPod 真实变更额外门禁：

- 只允许云测试；不得把 RunPod v0 指向正式 Central 或正式任务。
- `validate-key`、`list-pods`、`render-create`、`pod-readiness` 允许执行。
- `create-pod/start-pod/stop-pod/delete-pod` 默认 dry-run；真实执行必须同时设置：
  - `RUNPOD_DRY_RUN=false`
  - `RUNPOD_AUTOSCALER_ENABLED=true`
  - `RUNPOD_MAX_PODS_TOTAL=1`
  - `RUNPOD_MAX_PODS_PER_TYPE=1`
  - 命令行 `--execute`
- 真实创建前必须先确认 `runpod list-pods` 中无活动 managed Pod；若有旧 Pod，先 stop/delete 或人工确认，不得绕过成本门禁。
- 创建后只验证 `runpod_test_img2img_lora_*` 云测试 worker，不提交正式生产任务。
- 推荐使用安全一键 canary 代替手工串命令。默认 dry-run：

```bash
python scripts/gpu_pool_controller.py runpod canary \
  --env-file .env.cloud.test \
  --quiet
```

真实执行仍必须显式打开四重门禁和 `--execute`：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod canary \
  --env-file .env.cloud.test \
  --execute
```

`runpod canary` 会强制校验 cloud-test、managed Pod 数为 0、GHCR public baked image、`user-data-test` 测试桶、`allbot-model-cache/img2img_lora/2026-06-10/manifest.json` 模型同步、custom node runtime install 关闭、secret reference 口径正确；真实阶段自动恢复 `cloud_worker_test_01..07`、删除 Pod、再跑 list/reconcile。摘要不得输出 JWT、agent token、RunPod/R2 key、presigned URL 或完整 create/env payload。

禁止：

- 用 `--remove-orphans` 清理 worker project。
- 无 service 名执行 `docker compose down/up`。
- 因一个 Comfy 容器异常整机 reboot。
- 在未 drain 的情况下用强制重启代替能力切换。
- 把 `POOL_IMAGE_REF` 当作当前 ComfyUI 实际镜像。
- 把 `runtime-render` 输出直接用于 `gpu-226` 或任何 `host_service` runtime。
- 把 RunPod API key、R2 access key、R2 secret key、agent token、presigned URL 写入文档、日志、issue、commit message 或聊天。

## 3. Controller 命令参考

### 3.1 现有 dry-run 命令

```bash
python scripts/gpu_pool_controller.py inventory
python scripts/gpu_pool_controller.py plan
python scripts/gpu_pool_controller.py runtime-plan
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8189-worker-07 --profile img2img_lora --host-port 8191
python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8189-worker-07 --profile img2img_lora --host-port 8191
python scripts/gpu_pool_controller.py canary --assignment lan-252-8188-worker-04
python scripts/gpu_pool_controller.py workflow-model-check
python scripts/gpu_pool_controller.py model-import-plan
python scripts/gpu_pool_controller.py model-import-execute
```

预期行为：

- `plan`：输出 7 个 assignment 的资源池 dry-run。`gpu-226` 只允许出现 host_service 警告，不得出现 Docker pull/up/restart。
- `runtime-plan`：输出 runtime / image / model bundle / worker env diff。
- `runtime-plan --host-port 8190`：输出备用端口 canary worker env，默认指向 `http://192.168.1.2:8190` / `ws://192.168.1.2:8190/ws`，只给测试 worker 审阅和后续手工覆盖使用。
- `runtime-plan --host-port 8191`：用于 `gpu-002` worker 07 canary，默认指向 `http://192.168.1.2:8191` / `ws://192.168.1.2:8191/ws`。
- `runtime-render`：仅支持 `docker_container`；对 `gpu-226` 应返回结构化错误并退出非 0。
- `runtime-render --host-port 8190`：渲染 `8190:8188` 的 canary compose，默认容器名为 `allbot-comfy-gpu0-canary`，不会覆盖生产 `8188`。
- `runtime-render --host-port 8191`：渲染 `8191:8188` 的 canary compose，默认容器名为 `allbot-comfy-gpu1-canary`，不会覆盖生产 `8189`。
- `canary`：只检查 Comfy HTTP 接口、queue、required nodes 和 VRAM；不会提交真实生成任务。

### 3.2 已保留但不执行的命令

```bash
python scripts/gpu_pool_controller.py runtime-apply --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py switch-profile --assignment lan-002-8188-worker-06 --profile video_basic
python scripts/gpu_pool_controller.py rollback-profile --assignment lan-002-8188-worker-06
```

这些命令默认 dry-run，只输出计划。传 `--execute` 时当前必须拒绝执行并返回失败，因为真实变更还未实现安全执行器。

后续实现真实执行器时，必须保持：

- 默认 dry-run。
- 一次只允许一个 assignment。
- `host_service` 永远不生成 Docker 操作。
- `--execute` 前必须检查 `comfy_runtime_managed=true`。
- 必须先设置 worker `draining`，再等待 Comfy queue 和目标 worker running 归零。

### 3.3 RunPod Provider v0 命令

加载云测试配置：

```bash
set -a
source .env.cloud.test
set +a
```

只读验证：

```bash
python scripts/gpu_pool_controller.py runpod validate-key
python scripts/gpu_pool_controller.py runpod list-pods
python scripts/gpu_pool_controller.py runpod render-create --task-type img2img_lora --env cloud-test
```

创建前 readiness / 成本检查：

```bash
python scripts/gpu_pool_controller.py runpod reconcile-managed-pods
python scripts/gpu_pool_controller.py runpod list-pods
```

真实创建 1 个云测试 Pod，只有在确认 `list-pods` 无活动 managed Pod 后执行：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod create-pod \
  --task-type img2img_lora \
  --env cloud-test \
  --execute
```

创建后检查 RunPod 基础设施是否 ready：

```bash
python scripts/gpu_pool_controller.py runpod get-pod --pod-id <pod_id>
python scripts/gpu_pool_controller.py runpod pod-readiness --pod-id <pod_id>
```

停止或删除测试 Pod：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod stop-pod \
  --pod-id <pod_id> \
  --task-type img2img_lora \
  --execute

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod delete-pod \
  --pod-id <pod_id> \
  --task-type img2img_lora \
  --execute
```

预期行为：

- `validate-key` 只验证 API 可用，不创建 Pod。
- `list-pods` 默认只列出 `RUNPOD_MANAGED=true` 或 `allbot-*` 命名 Pod。
- `render-create` 输出创建请求但不调用 POST；输出中的 secret reference 会显示为 `<redacted>`。
- `create-pod --execute` 会先 reconcile 现有 managed Pod，再检查总数/单类型/成本门禁。
- `pod-readiness` 只判断 RunPod 基础设施映射信号；业务 ready 仍以云测试 Central `/system/workers` 中 `runpod_test_img2img_lora_*` heartbeat 为准。

## 4. 标准 Runtime Schema

每个 ComfyUI Runtime 在 `nodes.yml` 中应具备以下字段：

```yaml
comfy_runtime_kind: docker_container
comfy_runtime_managed: true
container_name: allbot-comfy-gpu0
container_port: 8188
compose_template: standard_comfy_runtime_v1
rollback_state:
  image_ref: yanwk/comfyui-boot:cu128-slim
  task_types: img2img,img2img_lora
  runtime_profile: img2img_lora
  container_name: comfy0
model_dir: /data/comfy/models
instance_dir: /data/comfy/inst0
custom_nodes_dir: /data/comfy/inst0/custom_nodes
workflows_dir: /data/comfy/inst0/workflows
input_dir: /data/comfy/inst0/input
output_dir: /data/comfy/inst0/output
temp_dir: /data/comfy/inst0/temp
health:
  system_stats: /system_stats
  queue: /queue
  object_info: /object_info
```

挂载原则：

- `models` 按节点共享，所有模型同步只写目标共享 `models`。
- `input/output/temp/custom_nodes/workflows` 按 GPU 实例隔离。
- 清理脚本只碰 `input/output/temp`。
- custom nodes 和 workflows 应来自镜像/profile 或受控同步，不在业务运行中手改。

## 5. 后续实施路线

### Phase 0：Controller dry-run 完整化

状态：已完成。

已验收：

- `runtime-plan` 可输出 7 个 assignment。
- `gpu-226` 识别为 `host_service`，不生成 Docker 操作。
- Docker runtime 可输出 image/model/profile/worker env diff。
- `runtime-render` 可渲染 `gpu-002` 标准 compose。
- focused tests 通过。

后续维护要求：

- 修改 schema、CLI、planner 时同步更新 `tests/ops/test_gpu_pool_controller.py`。
- 修改公开 CLI 时同步更新本文和 `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`。

### Phase 1A：`gpu-002` 备用端口 canary 能力补齐

状态：已完成代码与文档；未执行 live canary，未启动或重启任何 GPU 节点容器。

目标：先在 `gpu-002` 用备用端口验证标准 runtime，不影响生产绑定的 `8188/8189`。

已完成能力：

1. `runtime-plan` / `runtime-render` 支持 canary 覆盖参数：
   - `--host-port 8190`
   - `--container-name allbot-comfy-gpu0-canary`
   - `--api-url` / `--ws-url`
2. `--host-port` 与配置端口不同时进入 canary render 模式：
   - compose ports 渲染为 `8190:8188`
   - 默认容器名从 `allbot-comfy-gpu0` 派生为 `allbot-comfy-gpu0-canary`
   - compose project name 增加 `canary-8190` 后缀，避免和生产 runtime 冲突
   - labels 与 `x-allbot-runtime` 标记 `render_mode=canary`、`production_port_unchanged=true`
3. `runtime-plan` 在 canary 模式下明确标识：
   - 不接管生产 `8188/8189`
   - worker env 默认指向备用端口
   - 可通过 `CLOUD_TEST_WORKER_06/07_COMFY_API_URL` 与 `CLOUD_TEST_WORKER_06/07_COMFY_WS_URL` 给测试 worker 临时覆盖

验收命令：

```bash
python -m pytest tests/ops/test_gpu_pool_controller.py -q
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
python scripts/gpu_pool_controller.py runtime-render --assignment lan-226-8188-worker-01 --host-port 8190
```

预期结果：

- 前 3 条通过；`runtime-render --host-port 8190` 输出 `8190:8188` 和 canary 元数据。
- `gpu-226` 这条应失败并返回 host_service 结构化错误。
- 不传 `--host-port` 时仍保持原默认行为，渲染当前配置端口，例如 `8188:8188`。

### Phase 1B：`gpu-002` 云测试 live canary

状态：只读预检已完成；live canary 尚未执行，当前被目标镜像缺失和队列非空阻断。

只允许在用户明确确认维护窗口后执行。当前不得启动备用 runtime，不得重建 worker，不得配置 GPU 节点 registry。

已完成的只读预检：

1. 本地测试通过：

   ```bash
   python -m pytest tests/ops/test_gpu_pool_controller.py -q
   ```

   结果：`16 passed`。

2. `gpu-002` worker 06 dry-run / render 通过：

   ```bash
   python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
   python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
   ```

   结果：渲染 `allbot-comfy-gpu0-canary`，端口为 `8190:8188`，`x-allbot-runtime.render_mode=canary`，`production_port_unchanged=true`。

3. `gpu-002` worker 07 dry-run / render 通过：

   ```bash
   python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8189-worker-07 --profile img2img_lora --host-port 8191
   python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8189-worker-07 --profile img2img_lora --host-port 8191
   ```

   结果：渲染 `allbot-comfy-gpu1-canary`，端口为 `8191:8188`，`x-allbot-runtime.render_mode=canary`，`production_port_unchanged=true`。

4. `gpu-226` host_service 安全负例通过：

   ```bash
   python scripts/gpu_pool_controller.py runtime-render --assignment lan-226-8188-worker-01 --host-port 8190
   ```

   结果：结构化失败并退出 `2`。

5. `gpu-002` 只读环境检查：

   - `/` 和 `/data` 可用空间约 `675G`，使用率约 `25%`。
   - 当前生产容器为 `comfy0` / `comfy1`，镜像仍是 `yanwk/comfyui-boot:cu128-slim`。
   - `8188/8189` 正常监听，`8190/8191` 未监听。
   - `8188/8189` 的 `/system_stats`、`/queue`、`/object_info` 可读。
   - 预检时 `8188/8189` 队列非空，`python scripts/gpu_pool_controller.py canary --assignment lan-002-8188-worker-06` 与 `lan-002-8189-worker-07` 均因 `queue_empty=false` 返回失败；这不是接口不可用，而是维护条件未满足。

6. 本地 registry 只读检查：

   - `http://127.0.0.1:5000/v2/_catalog` 可读。
   - 当前 catalog 仅包含 `allbot/comfyui-boot`、`allbot/worker-agent`、`allbot/worker-relay`。
   - `allbot/comfy-cu130-video-basic:baseline` 与 `allbot/comfy-cu128-img2img:baseline` 当前返回 `404`，不能进入 live canary。

阻断项：

1. 目标 profile 镜像未发布：
   - `192.168.1.115:5000/allbot/comfy-cu130-video-basic:baseline`
   - `192.168.1.115:5000/allbot/comfy-cu128-img2img:baseline`
2. `gpu-002` 生产 `8188/8189` 队列在预检时非空。
3. 维护窗口尚未确认。

解除阻断后的执行顺序：

1. 运行 dry-run：

   ```bash
   python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
   python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
   python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8189-worker-07 --profile img2img_lora --host-port 8191
   python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8189-worker-07 --profile img2img_lora --host-port 8191
   ```

2. 只读检查 `gpu-002`：

   ```bash
   ssh allbot-gpu-002 'df -hT / /data || true; docker ps --format "{{.Names}} {{.Image}} {{.Status}}"'
   ```

3. 确认本地 registry 和镜像：

   ```bash
   curl -fsS http://127.0.0.1:5000/v2/_catalog
   curl -fsS http://127.0.0.1:5000/v2/allbot/comfy-cu130-video-basic/tags/list
   curl -fsS http://127.0.0.1:5000/v2/allbot/comfy-cu128-img2img/tags/list
   ```

4. 检查生产队列已达到维护条件：

   ```bash
   curl --noproxy '*' -fsS http://192.168.1.2:8188/queue
   curl --noproxy '*' -fsS http://192.168.1.2:8189/queue
   ```

   注意：当前本地主机存在 `http_proxy/https_proxy/all_proxy`，访问局域网 Comfy 端口时建议显式使用 `--noproxy '*'`，避免空端口被代理误报为 502。

5. 若 GPU 节点尚未信任 `192.168.1.115:5000`，在维护窗口内配置 Docker daemon insecure registry。
6. 在 `gpu-002` 启动备用端口 runtime，不碰现有 `comfy0/comfy1`。
7. 对备用端口运行：

   ```bash
   curl --noproxy '*' -fsS http://192.168.1.2:8190/system_stats
   curl --noproxy '*' -fsS http://192.168.1.2:8190/queue
   curl --noproxy '*' -fsS http://192.168.1.2:8190/object_info
   curl --noproxy '*' -fsS http://192.168.1.2:8191/system_stats
   curl --noproxy '*' -fsS http://192.168.1.2:8191/queue
   curl --noproxy '*' -fsS http://192.168.1.2:8191/object_info
   ```

8. 用云测试 worker 6/7 指向备用端口：

   ```bash
   set -a
   source .env.cloud.test
   set +a

   CLOUD_TEST_WORKER_06_TASK_TYPES='video_insert,image_to_video' \
   CLOUD_TEST_WORKER_06_RUNTIME_PROFILE='video_basic_canary' \
   CLOUD_TEST_WORKER_06_COMFY_API_URL='http://192.168.1.2:8190' \
   CLOUD_TEST_WORKER_06_COMFY_WS_URL='ws://192.168.1.2:8190/ws' \
   CLOUD_TEST_WORKER_07_TASK_TYPES='img2img,img2img_lora' \
   CLOUD_TEST_WORKER_07_RUNTIME_PROFILE='img2img_lora_canary' \
   CLOUD_TEST_WORKER_07_COMFY_API_URL='http://192.168.1.2:8191' \
   CLOUD_TEST_WORKER_07_COMFY_WS_URL='ws://192.168.1.2:8191/ws' \
   docker-compose --env-file .env.cloud.test -f workers/docker-compose-cloud-worker-test.yml \
     up -d --no-deps cloud-comfy-agent-test-6 cloud-comfy-agent-test-7
   ```

9. 验证 `/system/workers` 中 `cloud_worker_test_06/07` 的 task types、runtime profile、node/gpu 元数据和 healthy 状态。
10. 提交真实测试任务 canary，确认结果上传到 R2 `user-data-test`。
11. 恢复测试 worker 默认配置，并停止备用端口 runtime。

验收：

- 备用 runtime `/system_stats`、`/queue`、`/object_info` 正常。
- required nodes 全部存在。
- 测试任务完成并上传到测试 R2。
- `cloud_worker_test_06/07` 可恢复默认类型。
- 不影响正式 worker 6/7 的默认生产 `8188/8189`。

### Phase 1R：RunPod 云测试 `img2img_lora` canary

状态：已完成。2026-06-12 已创建 1 个 RunPod RTX 4090 云测试 Pod，完成 R2 模型同步、ComfyUI/relay/agent 启动、`img2img/img2img_lora` 三任务真实闭环，并删除 Pod 确认无 orphan。

目标：在不碰正式任务、不碰 `gpu-252` 现场的前提下，创建 1 个 RunPod GPU Pod，让它作为 `runpod_test_img2img_lora_*` 接入云测试 Central，并完成真实 `img2img/img2img_lora` 任务闭环。

执行结论：

- Pod：`if082v0w8eowow`，NVIDIA GeForce RTX 4090，`yanwk/comfyui-boot:cu128-slim`
- 发现基础镜像缺少 `ComfyUI-KJNodes`，导致首个任务缺 `GetImageSizeAndCount`；已现场修复并固化到 bootstrap
- 成功任务：`744a6d0a-928f-438d-8644-4465fb64ecce`、`ae9ae529-b6be-44cb-8feb-999ec19a8448`、`52395689-9485-4f14-a2f5-5775d538842c`
- 清理：云测试 worker 已恢复 enabled，RunPod `list-pods count=0`，`reconcile-managed-pods managed_count=0`

以下命令保留为后续复跑或回归 playbook。

准入条件：

1. `python -m pytest tests/ops/test_runpod_provider.py -q` 通过。
2. `python scripts/gpu_pool_controller.py runpod validate-key` 通过。
3. `python scripts/gpu_pool_controller.py runpod list-pods` 显示无活动 managed Pod。
4. `python scripts/gpu_pool_controller.py runpod render-create --task-type img2img_lora --env cloud-test` 中：
   - `RUNPOD_MODEL_SYNC_ENABLED=true`
   - `RUNPOD_MODEL_BUCKET=allbot-model-cache`
   - `RUNPOD_MODEL_PREFIX=img2img_lora/2026-06-10`
   - `RUNPOD_MODEL_MANIFEST_KEY=img2img_lora/2026-06-10/manifest.json`
   - `RUNPOD_MODEL_ACCESS_KEY=<redacted>`
   - `RUNPOD_MODEL_SECRET_KEY=<redacted>`
   - `MINIO_RESULT_BUCKET=user-data-test`
   - 不包含任何明文 secret。
5. 成本门禁保持总数 1 Pod、单类型 1 Pod。

执行顺序：

1. 打开真实创建门禁，创建 1 个 Pod：

   ```bash
   set -a
   source .env.cloud.test
   set +a

   RUNPOD_DRY_RUN=false \
   RUNPOD_AUTOSCALER_ENABLED=true \
   RUNPOD_MAX_PODS_TOTAL=1 \
   RUNPOD_MAX_PODS_PER_TYPE=1 \
   python scripts/gpu_pool_controller.py runpod create-pod \
     --task-type img2img_lora \
     --env cloud-test \
     --execute
   ```

2. 记录返回的 `pod_id`，轮询基础设施 readiness：

   ```bash
   python scripts/gpu_pool_controller.py runpod pod-readiness --pod-id <pod_id>
   ```

3. RunPod 日志预期顺序：
   - `syncing RunPod model bundle`
   - 主模型和 5 个 LoRA 下载/跳过校验
   - `ComfyUI ready`
   - `remote relay ready`
   - `starting comfy agent`
4. 云测试 Central 预期看到 `runpod_test_img2img_lora_<pod_id>` healthy，task types 为 `img2img,img2img_lora`。
5. 提交 3 个云测试任务：
   - 至少 1 个无 LoRA `img2img`
   - 至少 1 个 `qwen/YARN_1.0.safetensors`
   - 至少 1 个 `qwen/realistic_texture.safetensors` 或其它 manifest 中的 qwen LoRA
6. 验证：
   - worker 能 pop 任务
   - ComfyUI prompt 不再报 LoRA `value_not_in_list`
   - 结果上传到 R2 `user-data-test`
   - Central `/complete` 成功
   - Web result 可读
7. canary 完成后 drain/stop/delete Pod，确认 RunPod 无 orphan Pod：

   ```bash
   RUNPOD_DRY_RUN=false \
   RUNPOD_AUTOSCALER_ENABLED=true \
   RUNPOD_MAX_PODS_TOTAL=1 \
   RUNPOD_MAX_PODS_PER_TYPE=1 \
   python scripts/gpu_pool_controller.py runpod delete-pod \
     --pod-id <pod_id> \
     --task-type img2img_lora \
     --execute
   ```

失败判定与处理：

- 如果 Pod 长时间没有基础设施 readiness，优先换可用 GPU/区域，不改生产 worker。
- 如果 ComfyUI ready 前失败，保留 Pod 进入 SSH 诊断；只检查模型同步、ComfyUI 路径、Python 依赖和启动命令。
- 如果出现 LoRA `value_not_in_list`，先核对 R2 manifest、RunPod Pod 内 `models/loras/qwen/*`、ComfyUI `/object_info`，不要直接改 workflow。
- 如果结果上传失败，先核对 Pod env 中 R2 测试桶 secret reference、`MINIO_ENDPOINT`、`MINIO_*_BUCKET=user-data-test` 和 relay/sidecar 日志。
- 如果云测试 Central 未见 heartbeat，先查 `AGENT_SECRET_TOKEN` RunPod secret reference、`CENTRAL_API_URL=https://worker-central-test.aivison.it.com` 和 Cloudflare Tunnel。

验收：

- 只创建过 1 个 RunPod Pod，canary 后已删除或停止。
- `runpod_test_img2img_lora_*` 在云测试 Central healthy 期间能接任务。
- 3 个测试任务均完成，结果对象在 `user-data-test` 可读。
- `allbot-model-cache` 无 multipart 残留。
- 正式生产队列、`cloud_prod_worker_05`、`gpu-252` 未被改动。

### Phase 1C：`gpu-002` 受控切换执行器

状态：Phase 1B 通过后再做。

目标：把当前拒绝执行的 `runtime-apply` / `switch-profile --execute` 做成安全执行器。

实现要求：

- 只支持 `comfy_runtime_managed=true` 的单 assignment。
- 先写 runtime state 快照，再做变更。
- 先 `draining`，等待目标 worker 不再接单、Comfy queue 清空、task heartbeat 无目标 worker running。
- 同步模型 bundle 时只写共享 `models`。
- pull 镜像前检查磁盘。
- 只替换目标 runtime 容器。
- 成功后恢复 worker `enabled` 并跑 canary。
- 失败自动进入 rollback dry-run，真实 rollback 仍需显式确认或清晰策略。

新增测试至少覆盖：

- `--execute` 对 unmanaged runtime 拒绝。
- `--execute` 对 host_service 拒绝。
- drain 未完成时拒绝继续。
- rollback_state 缺失时拒绝自动 rollback。

### Phase 2：`gpu-252` 48G 正式候选

状态：暂缓。`gpu-252` 当前只识别/可用 1 张 4090，`cloud_prod_worker_04` / `gpu-252:8188` 不通；`cloud_prod_worker_05` / `gpu-252:8189` 正常且受保护。Phase 2 不再作为当前补 `img2img_lora` 容量的首选路径；短期补容量优先沿用已通过 Phase 1R 的 RunPod v0 云测试回归路径，生产自动扩容仍需另行开关和验收。

目标：

- 在硬件/驱动/GPU 可见性恢复后，再将 `gpu-252` 的 `img2img_lora` 与 `wan22_video_v2` 标准化为 Controller managed runtime。
- 验证 profile、共享模型目录去重和回滚速度。

准入条件：

- Phase 1B 至少完成一次备用端口真实 canary。
- Phase 1C 执行器有 focused tests。
- `gpu-252` 物理 GPU/驱动问题已人工修复，`comfy0` 恢复方案已单独审批。
- `cloud_prod_worker_05` 保护状态解除或有明确替代容量。
- `wan22_video_v2` profile 镜像已在 registry 可 pull。

验收：

- `wan22_video_v2` canary 成功。
- `img2img_lora` canary 成功。
- 只操作 `comfy0` 不影响 `comfy1`，反之亦然。
- 失败时能恢复原镜像和 worker task types。

### Phase 3：`gpu-177` 5090 cu130 profile

目标：

- 标准化 `video_basic` 与 `ltx_video`。
- 补齐 cu130 profile 镜像矩阵。
- 验证 LTX custom nodes、RIFE、VHS、rgthree LoRA loader。

验收：

- `ltx_video` canary 成功。
- `video_basic` canary 成功。
- `FL_RIFE` 不再依赖人工在容器里补依赖。

### Phase 4：`gpu-226` 宿主机 ComfyUI 迁移

最后执行，风险最高。

迁移方式：

1. 不直接替换 `8188`。
2. 先在 `gpu-226` 起新容器到 `8190`。
3. 复用或同步 `/home/ubantu/comfyui/models`。
4. 对 `8190` 跑 `/system_stats`、`/queue`、`/object_info`。
5. 测试 worker 先指向 `8190` 做 face/i2i/t2i canary。
6. 成功后再考虑正式 worker 01 从 `8188` 切到容器端口。
7. 保留宿主机 ComfyUI 作为短期回滚。

回滚优先方式：把 worker 01 的 `COMFY_API_URL` 指回 `http://192.168.1.226:8188`。

### Phase 5：正式环境灰度接管

顺序：

1. 测试 worker。
2. 正式低风险 worker。
3. 视频长任务 worker。
4. `worker_01 / gpu-226`。

每次正式接管必须：

- 开启维护或等价门禁。
- 等待目标 worker 或全局队列达到维护条件。
- 一次只切一个 assignment。
- canary 成功后关闭维护。
- 观察 Central `/system/workers`、Comfy `/queue`、R2 上传和任务完成回调。

### Phase 6：RunPod Provider 扩展

状态：Provider v0 已实现，Phase 1R 云测试真实任务 canary 已完成；尚未开启生产自动扩容。

RunPod 不进入本地 SSH 节点池，而是接入 provider 抽象：

```text
RunPodProvider:
  create pod
  attach network volume / warm cache
  pull image
  sync or mount model bundle
  start Comfy runtime
  start Worker Agent
  canary
  drain / stop / delete
```

RunPod 侧优先从云端模型仓库、Hugging Face、R2 或 S3 热缓存拉模型，不从本地主服务器跨公网拉大模型。

当前 v0 固定策略：

- 只使用 Pods Provider，不切 Serverless。
- 只支持云测试 `img2img/img2img_lora`。
- 总 Pod 上限 1，单类型 Pod 上限 1。
- 创建请求来自 `runpod render-create/create-pod`，不走 LAN SSH inventory。
- 模型来自 R2 `allbot-model-cache`，结果写入 R2 `user-data-test`。
- Pod 不默认开放 ComfyUI 公网端口；只有 SSH 诊断端口可按 RunPod 配置临时使用。
- RunPod SSH 仅作为人工诊断通道；需要调试时由用户提供 RunPod UI 当次 proxy SSH 信息，direct TCP SSH 只作为备用。生产自动扩容不依赖 SSH，ready 判定依赖 `pod-readiness`、Central heartbeat 和真实任务 canary。
- v0 不自动修复 `gpu-252`，不改变生产 task routing。
- `img2img_lora` profile 镜像构建入口已新增：`remote_workers/docker/runpod_profiles/img2img_lora/Dockerfile`、`Dockerfile.local-kjnodes` 与 `scripts/build_runpod_profile_image.sh`。镜像只包含 ComfyUI 基础环境、系统依赖和 custom nodes，不包含 Qwen checkpoint/LoRA 模型；模型仍从 R2 manifest 热同步。
- 2026-06-12 本机已构建并 smoke test 本地 tag `allbot/comfy-runpod-img2img-lora:local-20260612`，镜像内 `ComfyUI-KJNodes` commit 为 `7967a946c296a74901606e6a8d1195aa2b6f9215`，未包含业务模型文件。
- 2026-06-12 GHCR public alias `ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946` 已完成匿名 manifest 检查和 RunPod 三任务 canary；固定独立 package tag `ghcr.io/giraffu/allbot-comfy-runpod-img2img-lora:20260612-kjnodes7967a946` 已 push 但 package 当前 private，付费 Pod 不使用该 private tag。

后续扩展到生产前必须新增：

- 真实 drain 策略：RunPod worker 先 `draining`，等待 running 归零，再 stop/delete。
- orphan Pod watchdog：定期 list managed Pod 并对非预期 Pod 报警。
- 成本预算策略：从固定 1 Pod 扩展到按类型/单价/余额/队列压力计算。
- 多模型 profile：`img2img_lora` 之外的模型包必须有独立 prefix/manifest 和 canary。
- 生产开关：生产自动扩容必须另设显式开关，不能复用云测试 `RUNPOD_AUTOSCALER_ENABLED`。

## 6. Profile 镜像矩阵

目标镜像命名：

```text
192.168.1.115:5000/allbot/comfy-cu130-face-i2i:baseline
192.168.1.115:5000/allbot/comfy-cu130-video-basic:baseline
192.168.1.115:5000/allbot/comfy-cu130-ltx:baseline
192.168.1.115:5000/allbot/comfy-cu128-img2img:baseline
192.168.1.115:5000/allbot/comfy-cu128-wan22:baseline
192.168.1.115:5000/allbot/worker-agent:<git_sha>
```

RunPod v0 镜像/template 口径：

```text
RUNPOD_TEMPLATE_ID_IMG2IMG_LORA=<RunPod template id>
RUNPOD_IMAGE_NAME_IMG2IMG_LORA=<public registry image, when not using template>
RUNPOD_DOCKER_START_SCRIPT_FILE_IMG2IMG_LORA=remote_workers/scripts/runpod_bootstrap_from_git.sh
RUNPOD_CONTAINER_DISK_GB=80
RUNPOD_VOLUME_GB=0
RUNPOD_MODEL_BUCKET=allbot-model-cache
RUNPOD_MODEL_PREFIX=img2img_lora/2026-06-10
```

`img2img_lora` RunPod profile 镜像构建：

```bash
scripts/build_runpod_profile_image.sh \
  --image-ref ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946
```

如果 GitHub 在构建时不可用，可使用已验证的本地/导出 KJNodes 目录：

```bash
scripts/build_runpod_profile_image.sh \
  --image-ref ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946 \
  --kjnodes-source /path/to/ComfyUI-KJNodes
```

发布到公网 registry 需要先确认 namespace 和 `docker login`，然后显式传 `--push`：

```bash
scripts/build_runpod_profile_image.sh \
  --image-ref ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946 \
  --kjnodes-source /path/to/ComfyUI-KJNodes \
  --push
```

使用 baked profile 镜像复跑 RunPod canary 时，应关闭启动期 custom node 安装，但保持 R2 模型同步：

```bash
RUNPOD_USE_TEMPLATE_IMG2IMG_LORA=false \
RUNPOD_IMAGE_NAME_IMG2IMG_LORA=ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946 \
RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false \
RUNPOD_COMFY_KJNODES_ENABLED=false \
python scripts/gpu_pool_controller.py runpod render-create \
  --task-type img2img_lora \
  --env cloud-test
```

镜像原则：

- 镜像包含 ComfyUI、Python 环境、custom nodes、系统依赖和启动脚本。
- 模型不默认打进镜像。
- 按 profile 拆分，不做一个无限膨胀的大一统镜像。
- 保留 debug/base 镜像用于人工排障。
- 任何 profile 镜像进入 live canary 前，必须能被 `runtime-render` 引用并从目标 GPU 节点 pull。
- RunPod 镜像/template 不依赖本地 `192.168.1.115:5000` registry；必须使用 RunPod 可拉取的公网 registry/template，或使用官方/基础镜像 + bootstrap 脚本。
- RunPod 模型不从本地主服务器或局域网 registry 跨公网拉取，统一从 R2/Hugging Face/云端热缓存获取。

## 7. 回滚策略

每次真实切换前必须保存上一版 runtime state：

```yaml
previous:
  image_ref: ...
  task_types: ...
  runtime_profile: ...
  model_bundle_versions: ...
  compose_render_hash: ...
  container_id: ...
  container_name: ...
  host_port: ...
  comfy_api_url: ...
```

标准回滚：

1. 设置目标 worker `disabled`。
2. 停止新 runtime 容器。
3. 恢复上一版 image 和 compose。
4. 恢复 worker task types 和 runtime metadata。
5. 验证 `/system_stats`、`/queue`、`/object_info`。
6. 跑原 profile canary。
7. 恢复 `enabled`。

回滚验收：

- Central `/system/workers` 显示目标 worker healthy。
- 目标 Comfy queue 正常。
- 原 profile 真实 canary 成功。
- 失败可在 5-10 分钟内回到原入口。

## 8. 单次更新通用检查清单

开发前：

- 读本文、`docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`、`docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`。
- 确认目标阶段和允许动作。
- 运行：

  ```bash
  python scripts/gpu_pool_controller.py plan
  python scripts/gpu_pool_controller.py runtime-plan --assignment <assignment>
  python -m pytest tests/ops/test_gpu_pool_controller.py -q
  ```

代码更新时：

- 新增公开 CLI 必须有 tests。
- 新增执行能力必须默认 dry-run。
- 涉及 worker control 时必须保留 drain 语义。
- 涉及 runtime 操作时必须区分 `host_service` 与 `docker_container`。

运维执行前：

- 重新检查目标 GPU 节点磁盘：`df -hT`。
- 检查目标 Comfy `/queue`。
- 检查 Central `/system/workers`。
- 确认 R2 测试桶或生产桶目标。
- 确认没有使用 `--remove-orphans`。

RunPod 执行前：

- 确认 `runpod list-pods` 无活动 managed Pod。
- 确认 `.env.cloud.test` 中 RunPod 真实执行开关仍默认关闭。
- 确认 `render-create` 里的 `RUNPOD_MODEL_*` 指向 `allbot-model-cache/img2img_lora/2026-06-10`。
- 确认 RunPod Secrets 只以 `{{ RUNPOD_SECRET_* }}` reference 形式进入 Pod。
- 确认 `MINIO_*_BUCKET=user-data-test`，避免测试 Pod 写入正式结果桶。
- 确认本轮最高成本仍是 1 个 Pod，canary 后必须 stop/delete。

交付前：

- focused tests 通过。
- dry-run 输出已保存或总结。
- 文档和 skill 已同步。
- 明确说明是否执行了 live canary；默认没有执行。

## 9. 当前未完成事项

- Phase 1B 只读预检已完成，尚未执行 `gpu-002` 备用端口 live canary。
- `allbot/comfy-cu130-video-basic:baseline` 与 `allbot/comfy-cu128-img2img:baseline` 尚未发布到本地 registry。
- `gpu-002` 生产 `8188/8189` 队列预检时非空，live canary 前必须等待维护条件满足。
- `gpu-252` 当前不适合作为 `img2img_lora` 恢复入口：`worker_04` / `8188` 不通，`worker_05` / `8189` 仍可用且不得碰。
- `runtime-apply/switch-profile/rollback-profile --execute` 尚未实现真实执行器。
- profile 专用镜像矩阵尚未全部构建和验证。
- `runtime-plan` 尚未做远端磁盘/swap/registry 信任状态采集。
- 本地 GPU 模型 bundle sync 仍未接入安全执行器。
- RunPod v0 已完成真实业务 Pod 的 ComfyUI `/object_info` 与三任务验证；后续扩展到其它 profile 前仍需为每个 profile 单独准备 manifest/custom nodes/canary。
- Comfy real task canary 尚未自动化；当前本地 `canary` 只做 HTTP/object_info 级验证。
- Central Redis 偶发写连接 reset 是独立 P1 生产观察项，应另起修复，不要混入 runtime 接管。

## 10. 下一窗口推荐

下一窗口最小闭环：RunPod Phase 1R 与 GHCR baked profile canary 已通过，回到本地 GPU 容器化路线；先补齐 Phase 1B profile 镜像，再等待 `gpu-002` 维护条件执行备用端口 live canary。

如需复跑 RunPod 云测试 canary，使用以下回归 playbook。

1. 先确认没有遗留上传或 transfer Pod：

   ```bash
   set -a
   source .env.cloud.test
   set +a

   python scripts/gpu_pool_controller.py runpod list-pods
   ```

   预期：无活动 managed Pod；若有旧 `allbot-*` Pod，先确认用途再 stop/delete。

2. 运行本地 focused tests 和 dry-run：

   ```bash
   python -m pytest tests/ops/test_runpod_provider.py -q
   python scripts/gpu_pool_controller.py runpod validate-key
   python scripts/gpu_pool_controller.py runpod render-create --task-type img2img_lora --env cloud-test
   ```

   重点检查：`RUNPOD_MODEL_SYNC_ENABLED=true`、`allbot-model-cache`、`img2img_lora/2026-06-10`、`user-data-test`、无明文 secret。

3. 创建 1 个 RunPod 云测试 Pod：

   ```bash
   RUNPOD_DRY_RUN=false \
   RUNPOD_AUTOSCALER_ENABLED=true \
   RUNPOD_MAX_PODS_TOTAL=1 \
   RUNPOD_MAX_PODS_PER_TYPE=1 \
   python scripts/gpu_pool_controller.py runpod create-pod \
     --task-type img2img_lora \
     --env cloud-test \
     --execute
   ```

   `.env.cloud.test` 已默认固定 GHCR baked image、关闭启动期 custom node install，并保持 R2 模型同步；临时覆盖这些变量前必须先跑 `render-create` 核对。

4. 拿返回的 `pod_id` 做 readiness 与日志观察：

   ```bash
   python scripts/gpu_pool_controller.py runpod pod-readiness --pod-id <pod_id>
   ```

   观察 RunPod 日志直到出现 `ComfyUI ready`、`remote relay ready`、`starting comfy agent`。

5. 在云测试 Central 验证 `runpod_test_img2img_lora_<pod_id>` healthy，再提交 3 个云测试任务：
   - `img2img` 无 LoRA。
   - `img2img_lora` 使用 `qwen/YARN_1.0.safetensors`。
   - `img2img_lora` 使用 `qwen/adjust_pussy_anus.safetensors`、`qwen/flat_chest_hairless.safetensors`、`qwen/penis.safetensors` 或 `qwen/realistic_texture.safetensors` 中至少一个，确保不是只测两类常用 LoRA。

6. 验证闭环：
   - worker pop 成功。
   - ComfyUI 执行成功。
   - R2 `user-data-test` 上传成功。
   - Central `/complete` 成功。
   - Web result 可读。

7. canary 完成后删除 Pod：

   ```bash
   RUNPOD_DRY_RUN=false \
   RUNPOD_AUTOSCALER_ENABLED=true \
   RUNPOD_MAX_PODS_TOTAL=1 \
   RUNPOD_MAX_PODS_PER_TYPE=1 \
   python scripts/gpu_pool_controller.py runpod delete-pod \
     --pod-id <pod_id> \
     --task-type img2img_lora \
     --execute
   ```

8. 记录交付结果：
   - Pod ID、GPU 类型、镜像/template。
   - 模型同步耗时与是否命中 skip existing。
   - 3 个任务 ID 和结果 URL 可读结论。
   - RunPod 删除后 `list-pods count=0`。
   - 正式生产队列与 `cloud_prod_worker_05` 未受影响。

RunPod canary 通过后，再回到本地路线：补齐 Phase 1B profile 镜像、等待 `gpu-002` 维护条件、执行备用端口 live canary，最后才做 `runtime-apply --execute` 的安全执行器。
