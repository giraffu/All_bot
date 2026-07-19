# 子模块: GPU 算力资源池控制器 (GPU Pool Controller)

> 2026-07-18 不可变执行面契约：LAN AIO/RunPod profile 属于独立 `gpu-execution` track。镜像烘焙 agent/workflow/remote_workers，写 OCI/agent/workflow revision，并由 model manifest key + size + SHA256 固定外置模型；启动时禁止 clone 或主机源码覆盖。强制 artifact attestation 与可选业务 canary 分层：direct 可用 attested artifact，standard 仍需 canary-verified。main 的 GPU 输入变化必须先发布同 SHA 完整 OCI profile manifest，LAN registry 只允许保 digest 复制，不得现场重建。

## 1. 目标与范围

本模块记录 AllBot 第一阶段 GPU 算力资源池方案。当前不是 K8s/K3s，也不是自动生产弹性伸缩系统；它是一个以声明式配置、dry-run 计划、canary 和受控 RunPod provider 为主的运维控制器。

当前实现入口：

- 控制器包：`ops/gpu_pool_controller/`
- CLI：`scripts/gpu_pool_controller.py`
- 默认配置：`ops/gpu_pool_controller/config/`
- 本地镜像仓库：`deploy/docker-compose-local-registry.yml`、`scripts/manage_local_registry.sh`
- LAN 模型缓存：`deploy/docker-compose-model-cache-lan.yml`、`scripts/manage_lan_model_cache.sh`
- LAN RunPod 化一体容器云测试 canary：`scripts/lan_runpod_aio_canary.sh`
- LAN RunPod 化一体容器生产灰度：`scripts/lan_runpod_aio_prod_canary.sh`
- gpu-002 LAN AIO 正式日常入口：`scripts/lan_aio_prod_ops.sh`
- gpu-002 SCAIL-2 LAN AIO 正式 slot0 入口：`scripts/lan_scail2_aio_prod.sh`
- LAN AIO fleet 泛化配置：`ops/gpu_pool_controller/config/lan_aio_prod_slots.yml`
- LAN AIO fleet 本地运行态：`${XDG_STATE_HOME:-~/.local/state}/allbot/lan-aio/current.yml`
- LAN AIO operation 审计：`${XDG_STATE_HOME:-~/.local/state}/allbot/lan-aio/history/<operation-id>.json`
- LAN AIO fleet 泛化入口：`scripts/lan_aio_fleet_prod_ops.py`
- RunPod public provider facade：`ops/gpu_pool_controller/providers/runpod.py`
- RunPod profile/catalog 事实源：`ops/gpu_pool_controller/runpod_profile_catalog.py`
- RunPod create pod request 渲染 seam：`ops/gpu_pool_controller/runpod_pod_request.py`
- RunPod 通用 HTTP seam：`ops/gpu_pool_controller/runpod_http.py`
- RunPod 通用 auth/control seam：`ops/gpu_pool_controller/runpod_control.py`
- RunPod 云测试 canary lifecycle coordinator：`ops/gpu_pool_controller/runpod_canary.py`、`ops/gpu_pool_controller/runpod_split_video_canary.py`
- RunPod 云测试 canary case/executor seam：`ops/gpu_pool_controller/runpod_cloud_test_canary.py`
- RunPod 云测试 worker scale：`ops/gpu_pool_controller/runpod_workers.py`
- RunPod 手动正式备用 worker coordinator：`ops/gpu_pool_controller/runpod_prod_worker.py`
- RunPod 手动正式备用 worker 计划 seam：`ops/gpu_pool_controller/runpod_prod_worker_planner.py`
- RunPod 手动正式备用 worker HTTP seam：`ops/gpu_pool_controller/runpod_prod_worker_http.py`
- RunPod 手动正式备用 worker auth/control seam：`ops/gpu_pool_controller/runpod_prod_worker_control.py`
- RunPod 手动正式备用 worker canary case/executor seam：`ops/gpu_pool_controller/runpod_prod_worker_canary.py`
- RunPod 手动正式备用池日常入口：`scripts/runpod_prod_ops.sh`
- GPU release digest/证据解析：`scripts/gpu_release_rollout.py`
- RunPod split video manifest：`ops/gpu_pool_controller/runpod_video_manifests.py`
- RunPod bootstrap/model sync：`remote_workers/scripts/runpod_bootstrap_from_git.sh`、`remote_workers/scripts/runpod_sync_models_from_r2.py`

默认边界：

- 本地 GPU 资源池只纳入可 SSH 管理的局域网 GPU 节点。
- RunPod 不属于局域网 SSH 资源池，不会出现在 `LanSshProvider.inventory_from_config()` 中。
- Controller v1 默认只做盘点、计划、渲染和 canary；不自动重启 GPU 节点、不自动替换 ComfyUI、不自动按生产队列扩容。
- 所有真实 RunPod create/start/stop/delete/scale 都必须同时满足门禁环境变量和 `--execute`。

## 2. 当前资源池口径

可 SSH 管理的局域网 GPU 节点：

| 节点 | Host alias / IP | GPU | ComfyUI 口径 |
| :--- | :--- | :--- | :--- |
| `gpu-226` | `allbot-gpu-226` / `192.168.1.226` | 1 x RTX 5090 | 正式 LAN AIO `8190` 承接 `image_to_video` / `video_insert` / `video_edit`；`pornmaster_flux2_edit_bf16` 为同卡已缓存回切候选，宿主机 ComfyUI `8188` / `cloud_prod_worker_01` 仅作手工回滚元数据 |
| `gpu-177` | `allbot-gpu-177` / `192.168.1.177` | 2 x RTX 5090 | 正式 LAN AIO `8190/8191` only；旧 `comfy0/comfy1` 与本地主 agent 2/3 已退役删除 |
| `gpu-252` | `allbot-gpu-252` / `192.168.1.252` | 2 x RTX 4090 48G visible，2 x production active | 当前实时能力仍以 `lan_aio_fleet_state.yml` 与 Central 心跳为准；本次不可变发布候选会把 i2i_pro LAN AIO 的图片换脸声明从 `face_swap` 切到 `face_swap_v2`，不代表文档更新时已部署。GPU0 `8192` 与 RMA replacement GPU1 `8191` 分别固定 UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666` 与 `GPU-8153a439-e3f6-8922-039d-dc13e97da6d7`；旧返修 UUID 对应的 PornMaster/SCAIL-2/Wan22 槽位保持 maintenance disabled |
| `gpu-002` | `allbot-gpu-002` / `192.168.1.2` | 2 x RTX 4090 48G | 正式 LAN AIO slot0 SCAIL-2 `8190` + slot1 PornMaster Flux2 edit `8191`；image_to_video AIO stopped rollback，旧 `comfy0/comfy1` stopped rollback |

必须分清两层运行态：

| 层级 | 当前事实 | Controller v1 边界 |
| :--- | :--- | :--- |
| Worker Agent 层 | 本地主服务器上的 `cloud-prod-comfy-agent-*` / `cloud-comfy-agent-test-*` 容器，负责 `pop/status/complete/heartbeat`、workflow patch、上传回报 | 可通过 agent control 置为 `enabled/draining/disabled`；可重建 agent 容器；可上报 GPU pool metadata |
| ComfyUI Runtime 层 | 局域网 GPU 节点上的真实 ComfyUI。`gpu-226:8190` 当前为 image_to_video LAN AIO，`gpu-226:8188` 是保留的宿主机回滚服务；其它节点以 LAN AIO 容器为准 | 只按声明的 slot 做单物理 GPU 操作；不得把宿主机进程当 Docker 容器 |

`POOL_IMAGE_REF` 只是期望 profile/镜像声明，不能当作底层 ComfyUI runtime 的实际镜像事实。

## 3. 声明式配置与本地命令

主要配置文件：

- `nodes.yml`：节点、GPU、Comfy 实例、模型目录、worker 对应关系
- `task_profiles.yml`：任务类型、模型 bundle、workflow、custom node、最低显存、镜像引用
- `assignments.yml`：worker/节点支持哪些任务
- `model_bundles.yml`：模型 bundle manifest 计划与版本
- `lan_aio_prod_slots.yml`：LAN AIO helper 可管理的 slot/catalog，不代表每张卡的最新 live 当前态
- XDG `current.yml`：本地主 helper 原子维护的 last-known current/cache/验证时间；`history/<operation-id>.json` 记录成功、失败和回滚，未完成 operation 阻止下一次 mutation
- `lan_aio_fleet_state.legacy.yml`：冻结的一次性迁移种子，不再是运行态事实源，也不得在普通运维后更新

常用只读 / dry-run 命令：

```bash
python scripts/gpu_pool_controller.py inventory
python scripts/gpu_pool_controller.py plan
python scripts/gpu_pool_controller.py workflow-model-check
python scripts/gpu_pool_controller.py model-import-plan
python scripts/gpu_pool_controller.py image-plan \
  --source-image workers_cloud-prod-comfy-agent-1:latest \
  --repository allbot/worker-agent \
  --tag "$(git rev-parse --short HEAD)"
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06
```

模型导入器以 `workers/comfy_agent/workflows` 为事实源生成
`/srv/allbot/model-registry/bundles/<bundle>/<version>/manifest.yml`。若目标
worker 通过 `TASK_TYPE_WORKFLOW_OVERRIDES` 替换实际执行 workflow，
`BundleImportSpec.workflow_overrides` 必须同步写入同一映射；否则
`model-import-plan` 会按 legacy 默认 workflow 拉取已经不接单的旧模型。
新 `face_swap_v2` 使用 `face_swap_v2.json`，`t2i-pornmaster-turbo` 使用
`txt2img_from_i2i_pro.json`，二者与 `i2i_pro.json` 共享
`i2i_pro_baseline` 的六个 Flux2/Z-Image 模型。

Runtime dry-run 说明：

- `runtime-plan` 输出 runtime/image/model/worker-env diff，不连接远端、不修改 worker。
- `runtime-render` 渲染标准 ComfyUI runtime compose；只适用于 `docker_container`。
- `runtime-plan` / `runtime-render` 支持 `--host-port`、`--container-name`、`--api-url`、`--ws-url` 做备用端口 canary 覆盖。
- `runtime-plan` / `runtime-render` 支持显式 `--runtime-shape runpod_all_in_one`，用于渲染 LAN RunPod 化一体容器；默认仍是 `standard_comfy_runtime`，不会改既有 ComfyUI compose。
- all-in-one 模式支持 `--environment cloud-test|cloud-prod`；默认 `cloud-test`，生产灰度必须显式使用 `cloud-prod`，并验收 `RUNPOD_ENVIRONMENT=cloud-prod`、`CENTRAL_API_URL=https://worker-central.aivison.it.com`、`MINIO_*_BUCKET=user-data-prod`。
- `runtime-apply`、`switch-profile`、`rollback-profile --execute` 当前会明确拒绝真实执行。
- `gpu-226:8188` 旧宿主机 ComfyUI 仍是 `host_service`，不得对它生成 Docker pull/up/restart 操作；当前 `gpu-226-gpu0-image_to_video` 是独立 LAN AIO slot，操作必须走 `scripts/lan_aio_fleet_prod_ops.py`。

### 3.1 LAN RunPod 化一体容器 canary

第一轮只允许 `gpu-002` slot0 / `img2img_lora`，临时 agent 固定为 `lan_aio_test_gpu002_gpu0_img2img_lora_01`，canary host port 固定为 `8190`。该路径服务于云测试闭环，不接管旧生产 agent，不修改用户侧 task type，不创建 RunPod Pod。

运行态形态：

- `runtime_shape=runpod_all_in_one`
- runtime root：`/srv/allbot/runpod-runtime`
- workspace mount：`/workspace`
- 容器内 relay：`http://127.0.0.1:8013`
- 容器内 ComfyUI：`http://127.0.0.1:8188`
- Central：`https://worker-central-test.aivison.it.com`
- LAN 模型缓存：`http://192.168.1.115:9010`，bucket 固定 `allbot-model-cache`
- LAN registry：`192.168.1.115:5000`

模型缓存和镜像入口：

```bash
scripts/manage_lan_model_cache.sh --dry-run
python scripts/upload_all_task_models_to_lan_cache.py --env-file .env.lan.model-cache
```

LAN registry 缓存已验证 GHCR RunPod 镜像，也保存 SCAIL-2 这类本地构建的测试 profile 镜像；不要把未验证的一次性本地构建 tag 当作长期事实源。当前 LAN AIO 镜像关系：

- `ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946` -> `192.168.1.115:5000/allbot/comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946`
- `ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh` -> `192.168.1.115:5000/allbot/comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh`
- `ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:v2-47c1219f-i2ipro` -> `192.168.1.115:5000/allbot/comfy-runpod-i2i-pro:v2-47c1219f-i2ipro`，两端 manifest digest 均为 `sha256:a56620158da13c561e077511ebd310eb93de8821218da92c908df63f040b6495`；它是新候选/后续单槽切换的 profile catalog 默认值，不自动重启仍运行旧 digest 的槽位。
- `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd` -> `192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd`
- `remote_workers/docker/runpod_profiles/scail2/Dockerfile` -> `192.168.1.115:5000/allbot/comfy-runpod-scail2:20260617-scail2-cu128-a492b2b-proddeps1`
- `remote_workers/docker/runpod_profiles/pornmaster_flux2_edit/Dockerfile` -> `192.168.1.115:5000/allbot/comfy-runpod-pornmaster-flux2-edit-baked:20260716-pornmaster-flux2-edit-baked-runtime-v1`，该镜像 baked `/opt/allbot/runtime/remote_workers`，但不 baked 模型权重；模型由 `pornmaster_flux2_edit/2026-06-27/manifest.json` 在启动时同步。LAN tag 由 canonical GHCR digest `sha256:0fb2d8d9779e38fea72830a33a2d21099deada8dd4664ef25f8ca7d0900fe24a` 保 digest 复制。

注意：旧 `20260613-wan22aio-lanbase-ab9b7ea` Wan22 镜像不能被假定已 baked `rife49.pth`，只应作为回滚/热缓存场景。当前稳定新 tag `20260619-wan22aio-rife-bcf3ebd` 已 baked `rife49.pth`、`runpod_bootstrap_from_git.sh`，并通过构建 smoke 检查 `ComfyUI_Fill-Nodes` 与 `ComfyUI-Frame-Interpolation` 两处缓存路径。

GPU 节点 Docker daemon 必须信任 HTTP registry `192.168.1.115:5000` 后才能直接 `docker pull 192.168.1.115:5000/...`；未配置 insecure registry 时会被 Docker 强制按 HTTPS 访问并报 `HTTP response to HTTPS client`。修改 `/etc/docker/daemon.json` 并 restart Docker 会影响节点容器运行态，只能放在明确的节点维护窗口执行。若目标 SSH 用户没有免密 sudo，优先在本地主服务器 runner 执行 `docker save <lan-registry-image> | ssh <gpu-host> docker load` 预置镜像，避免为了镜像分发重启 Docker daemon；fleet `preflight` 会接受“registry 已配置”、“目标镜像已存在”或“runner 本地已有目标镜像可流式加载”任一条件，`pull-image --execute` 在远端 pull 失败且 runner 本地有镜像时会自动走 save/load 兜底。

`wan22_aio_video`、`image_to_video`、`wan22_video_v2` 三个 LAN AIO profile 共用同一个 Wan22 AIO 镜像；差异只在 runtime profile、`SUPPORTED_TASK_TYPES` 与模型 manifest。LAN AIO 的 `image_to_video` / `wan22_video_v2` split profile 由 runtime-render 自动在 `COMFY_EXTRA_ARGS` 追加 `--disable-dynamic-vram`，用于规避 cu128 ComfyUI DynamicVRAM 在 32G 5090 上的概率性 OOM。Wan22 V82 的 `FL_RIFE` 后处理还需要 `rife49.pth`，它不是大模型 manifest 的主权重；新镜像要 baked，旧镜像要用热缓存/启动 helper 补齐，不能依赖任务运行时访问 HuggingFace。

`pornmaster_flux2_edit` 是 2026-06-27 新增的 Flux2 edit profile，面向 `pornmaster_flux2_single_edit` 与 `pornmaster_flux2_multi_edit` 两个执行面 task type。它复用 i2i_pro 的 ComfyUI Flux2 core 节点能力，新增 workflow/API 映射、专用 LAN AIO 镜像和正式手动 RunPod profile；当前承载节点以 XDG fleet state 与 live 为准，RunPod 正式手动池使用 `runpod_prod_pornmaster_flux2_edit_manual_NN` / `allbot-runpod-prod-pornmaster-flux2-edit-manual-NN`，Dashboard 可手动新增，也已接入 Dashboard RunPod autoscaler 自动 add/down。autoscaler 默认按 `pornmaster_flux2_single_edit` / `pornmaster_flux2_multi_edit` 单任务 30 秒、profile 清空阈值 30 分钟估算，Dashboard 可按实测覆盖。模型 bundle `pornmaster_flux2_edit_baseline/2026-06-27` 需要三个文件：`diffusion_models/flux2/PornMaster_flux2_klein_9b_turbo_fp8_V4.safetensors`、`text_encoders/flux2/qwen_3_8b_fp8mixed.safetensors`、`vae/flux2/full_encoder_small_decoder.safetensors`。云端模型仓库准备优先使用临时 RunPod transfer Pod：`scripts/create_runpod_model_transfer_pod.py --pornmaster-flux2-edit` 先 dry-run，execute 时从源链接流式写入 `allbot-model-cache/pornmaster_flux2_edit/2026-06-27/models/...`，再用 `scripts/publish_pornmaster_flux2_model_manifest.py` HEAD 校验 size/sha256 metadata 后发布 manifest；本地不上传大模型。Civitai token 只能通过 RunPod secret 或一次性下载 URL 注入，不得写入文档、batch 明文、日志或 git。当前 `20260716-pornmaster-flux2-edit-baked-runtime-v1` 同时包含 FLUX.2 small-decoder VAE 兼容补丁与 baked worker runtime；fp8 已在 RTX 4090 / 24GB 上完成 1 图与 2 图 smoke，bf16 只作为 48GB 级显存 canary 候选。

2026-07-12 为 gpu-226 GPU0 新增 cache-only `pornmaster_flux2_edit_bf16` 候选：LAN 镜像复用 `20260716-pornmaster-flux2-edit-baked-runtime-v1`，独立 manifest 为 `pornmaster_flux2_edit_bf16/2026-07-12/manifest.json`，主权重是 Civitai V4 turbo BF16（SHA-256 `5085c05fa34b2455245a75f393885780b41e80a7517265b4b53da2e5044b004e`），并复用现有 Qwen fp8 text encoder 与 small-decoder VAE。该候选现声明 `pornmaster_flux2_edit_bf16` 与 `pornmaster_flux2_multi_edit_bf16` 两个内部执行类型：单图复用 single workflow 并切换 UNet 节点 100，双图复用 multiple workflow 的输入节点 17/29 并切换 UNet 节点 9；不会承接现有 fp8 的 `pornmaster_flux2_single_edit` / `pornmaster_flux2_multi_edit` 队列。镜像和三文件缓存已通过 fleet `pull-image` / `warm-cache` 准备完成；是否启用仍由单卡 operator 流程决定。

LAN AIO 与 RunPod 的单卡切换、缓存、recover/restart 是独立 GPU 执行面事务，不与 control-plane/test-train 发布绑定，也不为此部署无关服务。已有 canonical digest 的选择和复制由 GPU operator 直接执行；代码/catalog 变更继续留 Git 审计，但运行态是否可变更只由当次单卡 live/ledger/catalog、digest、健康、队列和 Xid 门禁决定。

同日 14:10 Asia/Shanghai，用户明确批准后已把 gpu-226 GPU0 从 `image_to_video` 切换为 `pornmaster_flux2_edit_bf16` 正式接单。helper 等待在途视频任务自然完成，通过 Docker health、disabled heartbeat、旧 GPU 进程清空和 enable gate；当前 worker 唯一声明类型为 `pornmaster_flux2_edit_bf16`，共享 runtime metadata `pornmaster_flux2_edit`，ComfyUI `/queue` 为空。未运行生成 canary；现有 fp8 single/multi 队列与 worker 未受影响。

同日 15:45 Asia/Shanghai，用户明确要求后又通过单卡 takeover helper 把 gpu-226 GPU0 回切为 `image_to_video`。切换前 BF16 worker 为 idle；镜像、21 个模型文件缓存、RIFE 热缓存、Docker health、disabled heartbeat 和旧 GPU 进程门禁全部通过，之后只启用 `video_insert` / `video_edit` / `image_to_video`。新 worker 放开接单后立即承接了队列中的正式视频任务；BF16 容器已停止，但镜像与三文件模型缓存保留 ready。

同日晚间又增加了与 LAN 独立的 RunPod profile `pornmaster_flux2_edit_bf16`：仅允许 `NVIDIA GeForce RTX 4090`，现同时声明单图 `pornmaster_flux2_edit_bf16` 与双图 `pornmaster_flux2_multi_edit_bf16`，使用 120GB container disk、`--lowvram`、独立 agent/pod 命名空间与 `pornmaster_flux2_edit_bf16/2026-07-12/manifest.json`。2026-07-15 已纳入 Dashboard autoscaler，两个队列都按默认单任务 30 秒聚合估算，清空阈值 30 分钟；BF16 canary 串行提交单图与双图。BF16 UNet 从 Civitai 下载链接在云控制机直接流式写入 R2，Qwen/VAE 从已有 R2 对象做 server-side multipart copy，未经本地上传；三文件总计 `27,071,581,434` bytes，manifest HEAD/size/SHA metadata 校验通过。2026-07-13 的单图 Central canary 已成功，双图需在对应 main bundle 的专项验收中按黄金路径补充执行证据；本轮代码交付不创建或修改正式 Pod。

`scail2` LAN AIO 泛化 fleet 渲染必须内置正式四任务 workflow override：动作迁移 audio workflow、长动作迁移 Context Windows workflow、视频换人 replacement workflow、视频换脸 v10 first-frame face-swap replacement workflow。所有 `runtime_profile=scail2` 的 LAN AIO 候选还必须带 `SCAIL2_FACE_SWAP_V10_ENABLED=true`、正式图片换脸预处理 Comfy API 和 `face_swap_v2.json`；否则 `scail2_face_swap_v2` 会跳过首帧换脸预处理，把用户人脸图直接作为 SCAIL-2 reference image，表现为“原视频没了、人脸图开始动”。2026-07-03 已把该规则固化到 `ops/gpu_pool_controller/runtime.py`，不再只依赖 `scripts/lan_scail2_aio_prod.sh` 的专用 patch。

all-in-one compose 渲染：

```bash
python scripts/gpu_pool_controller.py runtime-render \
  --assignment lan-002-8188-worker-06 \
  --profile img2img_lora \
  --host-port 8190 \
  --runtime-shape runpod_all_in_one \
  --agent-id lan_aio_test_gpu002_gpu0_img2img_lora_01
```

验收时必须看到：

- `x-allbot-runtime.production_port_unchanged=true`
- `host_port=8190`、`container_port=8188`
- `runtime_shape=runpod_all_in_one`
- `model_target_dir=/workspace/ComfyUI/models`
- `model_write_scope` 只包含 `/workspace/ComfyUI/models`
- `CENTRAL_API_URL=https://worker-central-test.aivison.it.com`
- `MASTER_API_URL=http://127.0.0.1:8013`
- `PIPELINE_MAX_RUNNING_TASKS=1`
- `NO_PROXY=*`

受控 canary helper：

```bash
scripts/lan_runpod_aio_canary.sh --action preflight --dry-run
scripts/lan_runpod_aio_canary.sh --action start-heartbeat --dry-run
scripts/lan_runpod_aio_canary.sh --action enable-canary --dry-run
scripts/lan_runpod_aio_canary.sh --action restore --dry-run
```

`start-heartbeat --execute` 会先把临时 agent control 设为 `disabled`，再把 compose/env 推到 `allbot-gpu-002` 并启动 canary 容器；不会放开接单。`enable-canary --execute` 只允许在真实 Web canary 窗口内临时 disable `cloud_worker_test_06` 并 enable 临时 agent；结束后必须执行 `restore --execute`，恢复旧 worker 并停止 canary 容器。失败现场需要保留容器和日志时，`restore --execute --keep-container` 只恢复 control，不停止容器。

gpu-002 早期 AIO 正式日常入口是 `scripts/lan_aio_prod_ops.sh`。它只管理原固定生产接管范围：slot0 `img2img/img2img_lora` 与 slot1 `image_to_video/video_insert/video_edit`，默认 dry-run，真实动作必须显式加 `--execute`。2026-06-18 后 slot0/`8190` 已由 `scripts/lan_scail2_aio_prod.sh` 接管为正式 SCAIL-2 AIO；slot1/`8191` 经 PornMaster 与 image_to_video 多次同卡切换后，于 2026-07-17 通过 fleet helper 切到 `gpu-002-gpu1-i2i_pro`，`gpu-002-gpu1-image_to_video` 与 `gpu-002-gpu1-pornmaster_flux2_edit` 当前只作为同卡回切候选。旧 `lan_aio_prod_ops.sh` 只能作为 slot1 image_to_video 历史观测/恢复参考，不能代表 gpu-002 slot0 的 SCAIL-2 或 slot1 当前全局现状。

| 日常动作 | 命令 | 语义 |
| :--- | :--- | :--- |
| 状态汇总 | `scripts/lan_aio_prod_ops.sh status` | 汇总 AIO agent control/status、8190/8191 health、旧 worker 06/07、旧 `comfy0/comfy1` 与旧 agent 6/7 状态 |
| AIO 接新单 | `scripts/lan_aio_prod_ops.sh enable-aio --execute` | 校验 AIO healthy，drain/wait idle 旧 worker，再 disable legacy 并 enable 两个 AIO agent |
| AIO 停接 | `scripts/lan_aio_prod_ops.sh disable-aio --execute` | drain 两个 AIO agent，等待当前 AIO 任务完成，再保持 AIO disabled |
| 回滚旧链路 | `scripts/lan_aio_prod_ops.sh rollback --execute` | 启动旧 `comfy0/comfy1`，验证 8188/8189，启动旧 agent 6/7，restore legacy worker 并 disable AIO |
| 停旧容器 | `scripts/lan_aio_prod_ops.sh stop-old --execute` | 仅在 AIO healthy 且 legacy worker disabled 时停止旧 ComfyUI/agent 容器；不删除 |

生产灰度 helper：

```bash
scripts/lan_runpod_aio_prod_canary.sh --action preflight --slot both --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action drain --slot both --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action configure-registry --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action start-heartbeat --slot slot0 --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action enable-canary --slot slot0 --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action drain-temp --slot slot0 --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action restore --slot slot0 --dry-run
```

生产灰度只允许 `gpu-002` 两个固定映射：slot0 `cloud_prod_worker_06 -> lan_aio_prod_gpu002_gpu0_img2img_lora_01`，端口 `8190`，profile `img2img_lora`；slot1 `cloud_prod_worker_07 -> lan_aio_prod_gpu002_gpu1_image_to_video_01`，端口 `8191`，profile `image_to_video`。生产执行必须先将目标 legacy worker 置为 `draining` 并等待当前任务自然完成；不要用强制重启代替 drain。生产 helper 会拒绝 test Central URL，并在启动前校验 compose 不含 `cloud-test` / `user-data-test`。slot1 `start-heartbeat --execute` 会从 gpu-002 宿主机旧 `inst1` 缓存预置 `rife49.pth` 到 AIO 内两个 RIFE 查找路径；缺失该热缓存时应停止放量，不让 FL_RIFE 后处理回退到 HuggingFace。

`start-heartbeat --execute` 必须在 Central 看到临时 agent 的 disabled heartbeat 后才算成功：临时 agent 不得是 `running`，不得有 `current_task_type`，heartbeat 必须携带 `node_id=gpu-002`、`provider=lan_ssh`、对应 `runtime_profile` 与 `pool_managed=true`。如果镜像内 remote_workers bundle 过旧，`/pop` 未携带 `agent_id` 或 heartbeat 缺少这些 GPU pool 元数据，必须停止灰度并从新 release index 选择重建后的 digest；生产禁止挂载宿主机源码修补。

旧 helper 的 repo `remote_workers` 同步/host mount 方式已废止。正式 LAN AIO compose 固定使用镜像内 `/opt/allbot/runtime/remote_workers`；模型仍由镜像内同步脚本按 manifest 写入 workspace。若 baked revision 不满足 release attestation，必须重建 canonical image，禁止用主机文件覆盖修补。

GPU profile Dockerfile 在复制 `remote_workers` 后必须设置 `PYTHONPATH=/opt/allbot/runtime/remote_workers` 并真实导入 `comfy_agent.workflow_task_patchers`，把 remote compatibility module 缺符号等闭包漂移提前阻断在镜像构建阶段。仓库根目录测试能导入主 `src`、或镜像中相关文件存在，都不能替代这个 baked bundle import smoke。

Central 可能在 worker 已回到 `idle` 后保留上一单的 `current_task_id`。生产 helper 的等待空闲逻辑以 `status == running` 或存在 `current_task_type` 作为忙碌信号；单独的陈旧 `current_task_id` 不应阻断 drain/restore 后续步骤。

gpu-002 进入 AIO 接管时仍使用同一 helper：先 `drain --slot both --execute`，再 `wait-idle --slot both --execute`，确认 legacy worker 与原 `8188/8189` 队列自然清空后，分别对 slot0/slot1 执行 `enable-canary --execute`。这会把 `cloud_prod_worker_06/07` 置为 disabled，并 enable `lan_aio_prod_gpu002_gpu0_img2img_lora_01` / `lan_aio_prod_gpu002_gpu1_image_to_video_01` 接新单。原 gpu-002 `comfy0/comfy1` 和本地主服务器 `cloud-prod-comfy-agent-6/7` 默认继续运行作为热回滚基线，不删除、不重建；AIO 稳定并完成验收后，如需释放资源只执行 `docker stop comfy0 comfy1` 与 `docker stop cloud-prod-comfy-agent-6 cloud-prod-comfy-agent-7`。回滚时先 `docker start comfy0 comfy1`，再启动 `cloud-prod-comfy-agent-6/7`，最后执行 `restore --slot slot0|slot1 --execute` 恢复 legacy worker。

gpu-002 首次生产灰度前还必须在维护窗口配置 Docker daemon `insecure-registries=["192.168.1.115:5000"]`；这会短暂重启 Docker 并影响 `comfy0/comfy1`，因此必须先 drain `cloud_prod_worker_06/07` 并确认 `8188/8189` 队列为空。配置完成后只拉取 LAN mirror 镜像，不创建 RunPod Pod，不修改生产 Web task type。
如当前 SSH 用户无免密 sudo，可只在当次命令环境传入 `LAN_AIO_GPU_SUDO_PASSWORD`；该变量不得写入 `.env`、compose、日志或文档。

### 3.2 LAN AIO fleet 泛化接管

gpu-002 专用 helper 已证明 all-in-one runtime 可以在正式 Central 下以 `disabled heartbeat -> 小窗口 enable -> drain/restore` 的方式安全接管。`gpu-177` 已用 fleet 入口整机接管，后续把 `gpu-252` 纳入 AIO 时继续使用同一套 fleet 配置和统一入口，不再复制 gpu-002 专用脚本：

- 配置事实源：`ops/gpu_pool_controller/config/lan_aio_prod_slots.yml`
- 编排入口：`scripts/lan_aio_fleet_prod_ops.py`
- 渲染事实源仍是 `python scripts/gpu_pool_controller.py runtime-render --runtime-shape runpod_all_in_one --environment cloud-prod`
- 真实密钥仍只从 `.env.cloud.prod`、`.env.lan.model-cache`、`.env.lan-aio-prod` 的 allowlist 读取；不得打印 env、compose config 展开值或 presigned URL

LAN AIO 当前态不在 Git 或本文维护静态大表。先读 XDG `current.yml`，再运行 `status --include-disabled`；普通 mutation 只有 `state.status=passed` 才允许。live 是观测现实、ledger 是 last-known、catalog 是允许集合，三者不是静默覆盖关系：任一不一致、live 不可达、catalog revision 改变或存在未完成 operation 都 fail closed。确认现场后通常只能显式执行 `state-reconcile --reason ... --execute` 收口并留下审计；若目标物理槽没有任何 running catalog container，`state-reconcile` 无法建立明确 current，此时仅允许精确单槽 `recover` 处理 `live_current_missing`（可同时收口 catalog revision），SSH 不可达、槽位错配和未完成 operation 仍阻断。

首次启用 ledger 时运行 `state-init --legacy-state-file <frozen-or-operator-copy> --execute` 并检查 status。冻结 seed 已包含 2026-07-17 的交接事实：`gpu-252` GPU0/GPU1 分别以 `8192`/`8191` 承载 `i2i_pro` 并绑定各自 UUID，`gpu-002` GPU1 从 `image_to_video` 切到 `i2i_pro`，且 image_to_video/PornMaster 保留为同卡回切候选；这些值只用于首次迁移，不能替代当次 live 核对。普通 `takeover/recover/restart-aio/warm-cache/pull-image` 持有本地单实例锁，成功后再次 live 验证，再原子替换 `current.yml` 并完成 history；失败和自动回滚同样写 history，current 不会提前前移。`recover` 对 missing/stopped 候选先执行受控 `pull-image`，再统一调用 `start-disabled` 从当前 catalog 重渲染并清理安全 stale container；不直接 `docker start` 历史容器，避免沿用旧 GPU UUID/device request。

2026-06-18 阶段能力口径：

| 层级 | 已覆盖/候选能力 | 当前口径 |
| :--- | :--- | :--- |
| LAN AIO 正式接单 | `img2img`、`img2img_lora`、`image_to_video`（兼容 `video_insert` / `video_edit` alias）、`i2i_pro`、`t2i-pornmaster-turbo`、`face_swap_v2`、`ltx_video`、`scail2_action_transfer`、`scail2_action_transfer_long`、`scail2_video_replacement`、`scail2_face_swap_v2`、`pornmaster_flux2_single_edit`、`pornmaster_flux2_multi_edit` | 表中为 V2 候选契约；旧 `face_swap` V1 由 `worker_remote_02` 保留，不进入 i2i_pro LAN profile。当前容量必须以当次 XDG ledger、live helper 与 Central 心跳仲裁，不再从 Git catalog 或冻结 legacy seed 推断；blocked/maintenance slot 不计入容量 |
| LAN AIO disabled 候选 | `img2img_lora`、`image_to_video` 回切口径，以及未 blocked 的新增候选 | 候选 slot 不自动接单；AI operator/CLI takeover 必须指定或推断同服务器当前运行目标，且按 live runtime profile 拒绝同 profile 替换；`maintenance_disabled` / `blocked_*` slot 不允许 takeover |
| LAN AIO canary-ready | 暂无固定常驻候选 | 后续新增 slot 仍必须逐 slot 验收，不跨节点批量 enable |
| 有镜像但未作为 LAN AIO 正式容量 | 无固定口径 | `i2i_pro` 已由 `gpu-252` GPU0 LAN AIO 正式接单；新增 profile 仍按 slot/state/live 三方仲裁 |
| 暂缓 | `face_i2i_t2i` / `gpu-226` 旧综合能力 | 旧综合 host-service worker 已下线，若要恢复 face/i2i/t2i 综合能力，需要单独的容器化 profile 或手工回滚宿主机链路 |

常用 dry-run / 只读命令：

```bash
scripts/lan_aio_fleet_prod_ops.py list
scripts/lan_aio_fleet_prod_ops.py status --slot gpu-252-gpu0-img2img_lora
scripts/lan_aio_fleet_prod_ops.py state-init --legacy-state-file ops/gpu_pool_controller/config/lan_aio_fleet_state.legacy.yml --execute
scripts/lan_aio_fleet_prod_ops.py state-reconcile --reason '<confirmed drift reason>' --execute
scripts/lan_aio_fleet_prod_ops.py render --slot gpu-252-gpu0-img2img_lora
scripts/lan_aio_fleet_prod_ops.py preflight
scripts/lan_aio_fleet_prod_ops.py configure-registry --slot gpu-252-gpu0-img2img_lora
scripts/lan_aio_fleet_prod_ops.py pull-image --slot gpu-252-gpu0-img2img_lora
scripts/lan_aio_fleet_prod_ops.py warm-cache --slot gpu-252-gpu0-img2img_lora --include-disabled
scripts/lan_aio_fleet_prod_ops.py candidate-plan --node-id gpu-252 --profile img2img_lora --replace-slot gpu-252-gpu0-image_to_video
scripts/lan_aio_fleet_prod_ops.py takeover --slot gpu-002-gpu1-image_to_video --include-disabled
# gpu-177-gpu1-wan22_video_v2 is blocked_oom_32gb after the 2026-07-01 OOM test; do not run takeover for it.
scripts/lan_aio_fleet_prod_ops.py start-disabled --slot gpu-252-gpu0-img2img_lora
scripts/lan_aio_fleet_prod_ops.py restart-aio --slot gpu-177-gpu0-image_to_video
scripts/lan_aio_fleet_prod_ops.py recover --physical-slot gpu-252:gpu0 --prefer old
scripts/lan_aio_fleet_prod_ops.py recover --physical-slot gpu-252:gpu0 --slot gpu-252-gpu0-img2img_lora --prefer candidate
```

候选配置遵循“Git catalog + 本地 state ledger”的边界。新增候选、换卡/UUID、修改 digest/manifest、改变或解除稳定阻断时，先用 `candidate-plan` 生成并审阅 Git patch；普通 profile 切换只更新 XDG ledger/history，不修改 catalog、docs 或根分支。catalog v2 中旧 `enabled/prod_enabled/superseded_by/old_runtime` 仅作迁移兼容，current 与旧 runtime 从 ledger + live 推导。Dashboard 不提供自由写生产 YAML、自由镜像、自由 manifest 或 slot/candidate 管理入口。

真实接管顺序必须逐 slot 执行，不得一次替换整台或多台 GPU：

1. `preflight --execute` 只读确认正式 Central/Web、LAN registry、LAN model cache、目标旧 ComfyUI `/system_stats`/`/queue`、磁盘，以及目标节点已配置 Docker insecure registry、已预置目标镜像或 runner 本地已有目标镜像可流式加载；legacy `/system_stats` 和 `/queue` 对刚重启的 ComfyUI 有短重试，连续失败才阻断切换。
2. 在维护窗口内执行 `configure-registry --slot ... --execute`；该动作会重启目标 GPU 节点 Docker daemon，必须先确保目标 legacy worker drain 且队列为空。若目标用户无免密 sudo 或不想中断节点 Docker，改用 runner `docker save ... | ssh ... docker load` 预置镜像，跳过 daemon restart。
3. `pull-image --slot ... --execute` 预拉 LAN mirror 镜像；若目标节点未配置 insecure registry 而 runner 本地已有同 tag 镜像，helper 会自动用 save/load 把镜像加载到目标节点。
4. `warm-cache --slot ... --include-disabled --execute` 用候选 profile 的 AIO 镜像在目标 workspace 运行一次无端口、无 agent、无接单的模型同步，并写入 `model-cache-marker.json`；若模型 manifest 尚未进入 LAN model cache，应让该步骤失败暴露，不在后台临时导入任意模型。
5. `takeover` 内部 drain legacy，阻止旧 agent 接新单。
6. `takeover` 内部最多等待当前旧任务自然终态，不用强制重启替代 drain。
7. `takeover` 内部 stop-old，停目标旧 runtime 容器，释放同卡显存和端口但不删除容器。
8. `takeover` 内部 start-disabled，启动 AIO 容器并只等待 disabled heartbeat，不允许接单。启动前会 inspect 目标候选容器名；若同名容器处于 `exited/created/dead/removing` 且名称匹配当前 slot，会先安全 `docker rm` 后再 compose up；若同名容器仍 running、restarting 或 inspect 名称不匹配，直接失败，不误删。
9. 验收 compose 不含 `cloud-test` / `user-data-test`，Central heartbeat 必须带 `node_id`、`provider=lan_ssh`、`runtime_profile`、`pool_managed=true`；`image_to_video` / `wan22_video_v2` slot 的 `COMFY_EXTRA_ARGS` 必须包含 `--disable-dynamic-vram`。
10. `takeover` 内部 enable-aio 会先把 legacy worker 置为 disabled，并拒绝在 legacy 仍 running、AIO disabled heartbeat 不可见或旧 runtime 容器仍占 GPU 显存时放开 AIO，避免同卡双 ComfyUI 抢单。

AI operator/CLI 的 `takeover --slot ... --include-disabled --execute` 从 ledger 自动解析 current/old runtime，并按 `preflight -> pull-image -> warm-cache -> drain-legacy -> wait-idle -> stop-old -> start-disabled -> enable-aio -> post-live-verify -> ledger/history commit` 串联上述步骤，默认 `--failure-policy auto_rollback`。为避免留下无法审计的中间态，`drain-legacy/stop-old/start-disabled/rollback` 不再支持独立 `--execute`，异常现场统一走精确 `recover`。Dashboard 已移除 slot/candidate 切换 API，Worker 卡片只保留基础暂停/开启/重启；本地主 helper 会再次确认目标 agent 就是 ledger/live current。`render`、`preflight`、`pull-image`、`warm-cache` 和 `takeover` 可从 ledger 自动 retarget，也兼容显式 `--replace-slot` 但必须与 ledger 一致。`warm-cache` 对 root-owned workspace 保留 Docker root helper 兜底。保护窗口失败时 helper 自动恢复旧 runtime，并把 operation 记录为 failed/rolled_back；current 不提前前移。

失败现场手工恢复入口是 `recover --physical-slot <node>:gpuN --prefer old|candidate`，它只作用于单个物理 GPU，不跨节点、不批量操作；需要恢复到明确候选时可追加 `--slot <slot-id>`，脚本会校验 slot 必须属于该物理 GPU。恢复会先 disable/stop 同卡其它 AIO，再把目标 slot 置为 disabled、启动或在容器缺失时按 `start-disabled` 渲染重建，验证容器健康和 disabled heartbeat 后才 enable 目标 agent。`--operation-id` 只作为审计提示，实际恢复仍要求显式指定 `--physical-slot` 或能由 `--slot` 推导出唯一 physical slot，避免从历史 operation 推断出过宽恢复范围。生产执行仍必须显式 `--execute`，否则只输出 dry-run 操作计划。

LAN AIO compose 固定带 `restart: unless-stopped`。AIO bootstrap/entrypoint 会同时监管 ComfyUI、relay 与 agent；任一关键进程退出都会退出容器，由 Docker restart policy 重建干净 runtime，避免 ComfyUI 子进程 OOM 后只剩 agent 心跳继续存活。手动恢复某个已接管 AIO worker 时使用 `restart-aio --slot ... --execute` 或 Dashboard worker 卡片 `重启`：它先将目标 AIO agent control 置为 `disabled`，只对该 slot 的 all-in-one compose 执行原地 `restart`，等待容器健康和 disabled heartbeat，再把目标 agent 置回 `enabled`。该动作不重启整机 Docker daemon、不触碰旧 runtime、不跨 slot 操作；若当前 worker 正在执行任务，原地重启会中断该 worker 的当前任务，后续仍需按任务终态/僵尸清理链路收口。

`start-disabled` 支持在 slot 配置中声明 `legacy_hot_cache_copies`，用于把旧 ComfyUI 容器或 GPU 节点宿主机上由 custom node 运行期下载的热缓存文件预置进 AIO 容器。`gpu-177` 的旧 `comfy0` 来源已在 2026-06-20 退役删除，后续重建应使用带 RIFE 缓存的 `20260619-wan22aio-rife-bcf3ebd` 或模型缓存补齐，不得再从旧容器复制；`gpu-252-gpu1-wan22_video_v2` 仍声明从宿主机旧 `inst1` 路径复制同一文件。它们都是 `FL_RIFE` 后处理的运行依赖，不能依赖 AIO 容器运行时访问 HuggingFace；RunPod split video 也遵循同一红线，旧 Pod 需要 helper/模型目录补齐，新 Pod 应使用 baked RIFE 的新镜像 tag。

2026-06-18 `gpu-177` 进入整机 LAN AIO 接管，2026-06-20 已按用户确认退役本地旧链路：旧 `cloud_prod_worker_02/03` control 为 `disabled`，本地主 `cloud-prod-comfy-agent-2/3`、GPU 节点 `comfy0/comfy1`、旧 `/data/comfy` 和旧镜像已删除；gpu-177 不再提供本地旧链路回滚，恢复入口改为 AIO restart/recreate、同卡候选 takeover 或外部容量兜底。2026-07-02 operator 校准后，`gpu-177` GPU0 live/catalog/state 收敛为 `wan22_video_v2` 当前 slot，`gpu-177-gpu0-image_to_video` 为同卡回切候选；GPU1 曾切到 `image_to_video`，但真实任务多次触发 ComfyUI status 137 / restart，因此已回滚到 LTX，并把 `gpu-177-gpu1-image_to_video` 标为 `blocked_oom_32gb`。同日 GPU1 曾短暂切到 `gpu-177-gpu1-scail2`，验证 SCAIL-2 容器 healthy 与 cache ready 后，又按明确操作请求切回 `gpu-177-gpu1-ltx_video` 继续接 LTX 任务；`gpu-177-gpu1-scail2` 现在是同卡候选。2026-07-01 正确目标 `gpu-177-gpu1-ltx_video` 的 Wan22 takeover 曾成功完成，但第一笔真实 `wan22_video_v2` 任务在 RTX 5090 32GB 上 OOM kill ComfyUI（status 137），随后已恢复；`gpu-177-gpu1-wan22_video_v2` 因此标记为 `blocked_oom_32gb`、`retargetable=false`，不得作为 AI operator/CLI takeover 候选，直到有更小 profile 或 48GB+ LAN 容量验证。`scail2` profile catalog 仍偏向 48GB，gpu-177 GPU1 是 32GB，未来若再切 SCAIL-2 要重点观察 status 137/OOM。

2026-07-02 `gpu-226-gpu0-image_to_video` 已按 host-service 到 LAN AIO 的单卡迁移流程上线：新增独立 AIO slot / assignment，host `8190`，agent `lan_aio_prod_gpu226_gpu0_image_to_video_01`，镜像 `192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd`，模型 manifest `image_to_video/2026-06-13-test/manifest.json`。上线前先让旧 `cloud_prod_worker_01` drain/idle，拉取或导入镜像、warm-cache、补齐 RIFE 热缓存，并以 disabled heartbeat 验证 Comfy/模型/队列/内存/显存；随后用 5s `image_to_video` canary 与真实队列观察，未见 OOM/137，切换完成后 `cloud-prod-comfy-agent-1` 停止、`cloud_prod_worker_01` control 保持 disabled。旧 `/etc/systemd/system/comfyui.service` 仍 active/idle 且 `8188` 队列为空；缺少 sudo 维护窗口时不要强行停止，它只作为手工回滚元数据，不再作为当前接单 runtime。

2026-06-18 `gpu-252-gpu1-wan22_video_v2` 已替换 `cloud_prod_worker_05`：AIO agent `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` 连接正式 Central，host `8191`，只声明 `SUPPORTED_TASK_TYPES=wan22_video_v2`，不承接普通 `image_to_video` 或 `video_edit`。旧 `comfy1` 与 `cloud-prod-comfy-agent-5` 已停止保留为回滚基线。2026-06-19 重启后该 slot 配置改回 `gpu_index: 1`；实测第二个生产 wan22 任务仍让 GPU1/ComfyUI 进入 unhealthy 且 Docker 无法 stop/kill 的状态。2026-07-04 返修卡 UUID `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e` 已重新可见；`gpu-252-gpu1-scail2` 在 host `8191` 曾通过 preflight、镜像确认/拉取、warm-cache、start-disabled、`/system_stats`、`/object_info` 模型枚举、direct SCAIL-2 canary 与 `enable-aio`，但真实 SCAIL-2 face-swap workload 随后复现 Xid 119/154 / GPU Reset Required，ComfyUI 返回 CUDA unknown error 且容器无法正常 stop/kill。主机重启后该卡短 CUDA smoke 触碰约 20.5 GiB 并计算约 120 秒未再出现 Xid。随后 `gpu-252-gpu1-pornmaster_flux2_edit` 在同一返修 UUID 上完成 preflight、pull-image、warm-cache、start-disabled、`/system_stats`、`/object_info` 节点/模型验证与多笔正式 `pornmaster_flux2_single_edit` 任务，未见新 Xid/NVRM；这只证明低负载图片编辑可接单，`gpu-252-gpu1-scail2` 与 `gpu-252-gpu1-wan22_video_v2` 仍保持 maintenance-disabled，RunPod 和其它 SCAIL-2/Wan22 容量继续兜底。

2026-06-19 `gpu-252-gpu0-img2img_lora` 从 canary-ready 转入正式 LAN AIO 接流：AIO agent `lan_aio_prod_gpu252_gpu0_img2img_lora_01` 连接正式 Central，host `8190`，按 `img2img_lora` profile 承接 `img2img` 与 `img2img_lora`。2026-06-28 起该 slot 被 `gpu-252-gpu0-pornmaster_flux2_edit` 正式替换，新的 AIO agent `lan_aio_prod_gpu252_gpu0_pornmaster_flux2_edit_01` 监听 host `8192`，只接 `pornmaster_flux2_single_edit` 与 `pornmaster_flux2_multi_edit`。2026-07-03 `gpu-252` 按单卡 takeover 切到 `i2i_pro`；2026-07-04 返修卡回装导致 host GPU index 漂移后，所有 `gpu-252` GPU0 `8192` 候选和当前 i2i_pro slot 均改用 `gpu_device_id: GPU-09b7ea85-23df-a9b8-19d9-703534e47666` 固定健康卡，`restart-aio` 会 force-recreate 容器以应用 device request。`img2img_lora`、`image_to_video`、PornMaster Flux2 edit 与 SCAIL-2 均保留为同卡回切候选，不应与当前 AIO 同时 enabled 或同卡占用显存。

2026-06-28 `gpu-002-gpu1-pornmaster_flux2_edit` 曾通过 fleet 入口替换旧 slot1 `image_to_video` AIO，之后多次按单 slot 回切。2026-07-17，operator 为同卡新增并冷缓存 `gpu-002-gpu1-i2i_pro`，等待在途视频任务自然结束后通过 takeover 切换成功；当前 `lan_aio_prod_gpu002_gpu1_i2i_pro_01` 在 host `8191` 接 `i2i_pro` / `t2i-pornmaster-turbo` / `face_swap`，`image_to_video` 与 PornMaster 均为同卡回切候选。fleet 当前标签只认 live heartbeat / running container；无 live signal 的 `prod_enabled`、`maintenance_disabled`、`candidate`、`blocked_*`、`superseded_*` 都不得被标成 `runtime_current`。不得让两个 8191 容器或两个 GPU1 agent 同时 enabled。

后续优化方向：

- 配置阶段应区分 `prod_enabled`、`canary_ready`、`blocked_host_service_runtime`，避免已正式接管的 slot 仍被误读为 canary。
- `wan22_video_v2` 在 `gpu-252` GPU1 slot 和历史 `gpu-177` GPU1 blocked slot 都通过 slot-level `target_task_types` 收窄为只接 `wan22_video_v2`；后续新增共享镜像 slot 时也应优先显式声明目标 task type，避免 profile 默认 alias 误接单。`gpu-177` GPU0 当前配置、state 与 live runtime 都按 `wan22_video_v2` 判断；`gpu-177-gpu1-wan22_video_v2` 的 32GB OOM blocked 状态解除前不得作为候选容量。
- `preflight` / release rollout 必须检查 baked workflow/agent revision、模型 manifest、对象桶和 image digest，减少“容器健康但工作流资产缺失”的误启用。
- LAN registry 直拉仍依赖 GPU 节点 Docker insecure registry；配置会重启整机 Docker daemon。当前 fleet helper 已支持 runner 本地镜像 save/load 兜底，后续优先评估 TLS registry 或更标准的免 daemon 重启镜像分发路径。
- Dashboard `LAN AIO 管理` slot 面板和对应 public API 已移除；后续 LAN AIO 候选/切换/恢复能力只在本地 AI operator/CLI 中强化 image digest 与失败原因结构化归因。

SCAIL-2 LAN AIO runtime 已用于 Web/Bot 的视频生视频能力：正式 LAN SCAIL-2 slot 包含 `scail2_action_transfer`（动作迁移 5s/8s）、隐藏执行类型 `scail2_action_transfer_long`（动作迁移 10s/15s/20s）、`scail2_video_replacement`（视频换人）和 `scail2_face_swap_v2`（视频换脸 v10 two-stage）。它有测试 runtime、云测试 RunPod profile、云正式 LAN runtime 与云正式手动 RunPod profile 四条边界，不能混用测试/正式桶或 worker；正式 RunPod `scail2` profile 仍只声明动作迁移/视频换人两任务。

测试 LAN runtime 是独立于 Central 接单层的 ComfyUI runtime，不使用 `runtime-render`，入口为 `scripts/lan_scail2_aio_test.sh`。它在 gpu-002 GPU0 上临时替换原 slot0 AIO 的 `8190:8188`，容器名固定为 `allbot-lan-aio-gpu-002-gpu0-scail2-test`，workspace 为 `/srv/allbot/runpod-runtime/slots/gpu-002-gpu0/profiles/scail2/workspace`。`start --execute` 会先把 `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 置为 `draining`，等待当前 `img2img_lora` 任务和 8190 queue 自然空闲，再设为 `disabled` 并停止旧 `allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary`；`cloud_prod_worker_06` 保持 `disabled`，slot1 当前 AIO 不动。测试容器不设置 `AGENT_ID`、`CENTRAL_API_URL` 或 `SUPPORTED_TASK_TYPES`，只启动 ComfyUI UI、LAN model sync、Nomadoor UI workflow、业务 API workflow 和样例素材。

云正式 slot0 runtime 使用 `scripts/lan_scail2_aio_prod.sh`，同样占用 gpu-002 GPU0/`8190:8188`，但会注册正式 agent `lan_aio_prod_gpu002_gpu0_scail2_01`，容器名为 `allbot-lan-aio-gpu-002-gpu0-scail2-prod`，并由 runtime-render 的 `scail2` profile 生成 cloud-prod all-in-one compose 后在 helper 内覆盖为四任务正式 LAN 配置。该 helper 只触达旧 slot0 AIO agent `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 与旧 slot0 容器 `allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary`，不会重建 `cloud-prod-comfy-agent-1..7`，不会创建/启停 RunPod，不会操作 slot1/`8191`。`start-disabled --execute` 会 drain 旧 slot0 AIO 并等待自然空闲，停止旧 slot0 容器后启动 SCAIL-2 disabled heartbeat；已运行 SCAIL-2 AIO 的配置更新使用 `restart-disabled --execute` 原地重建并保持 disabled。验收 `/system_stats`、`/object_info` 必需节点、模型枚举、`RUNPOD_ENVIRONMENT=cloud-prod`、正式 Central、`user-data-prod`、四任务 `SUPPORTED_TASK_TYPES`、audio/context-window/v10 workflow override 与 `SCAIL2_FACE_SWAP_V10_*` 后，才执行 `enable --execute`。

SCAIL-2 镜像入口是 `remote_workers/docker/runpod_profiles/scail2/Dockerfile`，正式 AIO 当前固定 LAN tag 为 `192.168.1.115:5000/allbot/comfy-runpod-scail2:20260617-scail2-cu128-a492b2b-proddeps1`。该镜像基于 `yanwk/comfyui-boot:cu128-slim`，使用包含 ComfyUI PR `Comfy-Org/ComfyUI#14373` 后的版本，并 baked `remote_workers/requirements.txt` 中的 FastAPI/MinIO/uvicorn/websockets 等 worker 运行依赖。它必须在 `/object_info` 暴露 `WanSCAILToVideo`、`SCAIL2ColoredMask`、`SAM3_VideoTrack`、`WanContextWindowsManual`、`VHS_LoadVideo`、`VHS_VideoCombine`。模型从 `allbot-model-cache/scail2/2026-06-17-test/manifest.json` 同步到 `/workspace/ComfyUI/models`；runtime-render 会把 baked ComfyUI 的 `models` 目录链接到该同步目录，验收还要确认主模型、SAM、CLIP Vision、Wan VAE、UMT5 和 LightX2V LoRA 都在 `/object_info` 枚举中。LoRA 路径必须是 `loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors`，否则 Nomadoor workflow 的 LoRA dropdown 无法解析。

Web/Bot 测试业务接入不把测试 ComfyUI 容器本身注册成 worker：测试容器仍不设置 `AGENT_ID` / `CENTRAL_API_URL` / `SUPPORTED_TASK_TYPES`。接单层在本地主 `workers/docker-compose-cloud-worker-test.yml` 中新增 `cloud-comfy-agent-test-8` / `cloud_worker_test_08`，指向 `http://192.168.1.2:8190`，当前测试可声明 `SUPPORTED_TASK_TYPES=scail2_action_transfer,scail2_action_transfer_long,scail2_video_replacement,scail2_face_swap_v2` 与 GPU pool 元数据 `node_id=gpu-002`、`gpu_index=0`、`runtime_profile=scail2`，并用 audio/context-window workflow 做测试覆盖；其中 `scail2_action_transfer_long` 只承接动作迁移 10/15/20s 的隐藏执行路由，指向 `SCAIL-2_Animation_WAN-Context-Windows.api.json`，最长 321 帧，不代表无限长视频，也不作为独立用户入口；视频换脸当前指向 `SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json`，并通过 `CLOUD_TEST_WORKER_08_FACE_SWAP_V10_*` 先跨 runtime 调用 `face_swap_v2.json` 生成换脸首帧。云正式 LAN 业务接单层当前由 `lan_aio_prod_gpu002_gpu0_scail2_01` 承接四类 SCAIL-2 正式任务并写正式 Central 与 `user-data-prod`；`lan_aio_prod_gpu252_gpu1_scail2_01` 因返修卡真实 workload 复现 Xid 119/154 处于 maintenance disabled，`lan_aio_prod_gpu177_gpu1_scail2_01` 作为已验证但停止的同卡候选保留。手动正式 RunPod `runpod_prod_scail2_manual_NN` 仍只作为动作迁移/视频换人的两任务备用容量，不承接 `scail2_face_swap_v2` 或 `scail2_action_transfer_long`，不得复用 `cloud_worker_test_08` 或 `user-data-test`。

SCAIL-2 也支持独立 RunPod profile，不复用 `gpu-002/8190`。`RUNPOD_TASK_PROFILES["scail2"]` 渲染为 `SUPPORTED_TASK_TYPES=scail2_action_transfer,scail2_video_replacement`、`POOL_RUNTIME_PROFILE=scail2`、`containerDiskInGb=120`，模型桶固定 `allbot-model-cache`。cloud-test agent prefix 是 `runpod_test_scail2`，用户输入/结果桶是 `user-data-test`；cloud-prod 手动池 agent 是 `runpod_prod_scail2_manual_NN`，Pod 名称是 `allbot-runpod-prod-scail2-manual-NN`，用户输入/结果桶必须是 `user-data-prod`。镜像由 `.github/workflows/runpod_scail2_profile_image.yml` 构建 `ghcr.io/giraffu/allbot-comfy-runpod-scail2:<tag>`，Dockerfile 保留 LAN entrypoint 作为默认 CMD，但 RunPod create JSON 通过 `dockerStartCmd=["bash","-lc","exec bash /opt/allbot/runpod_bootstrap_from_git.sh"]` 启动 bootstrap。模型转存入口是 `scripts/prepare_scail2_model_r2_bundle.py --env-file .env.cloud.test --execute`，默认 dry-run，只写 `allbot-model-cache/scail2/2026-06-17-test/models/...` 与 manifest，不写 `user-data-test` 或 `user-data-prod`。

`runpod canary --task-type scail2` 是 SCAIL-2 cloud-test RunPod 验收入口。dry-run 会校验 GHCR image prefix、`allbot-model-cache`、`scail2/2026-06-17-test/manifest.json`、custom node env 关闭、bootstrap command 与 GPU 类型；真实执行会上传/复用 Nomadoor 样例参考图和 motion video，临时 disable 支持 SCAIL-2 的非 RunPod cloud-test worker（通常是 `cloud_worker_test_08`），串行提交 `scail2_action_transfer 5s` 与 `scail2_video_replacement 5s` 两个 Web 任务，要求 Central 接单 worker 为 `runpod_test_scail2_*`，结束后恢复 worker control 并删除本次 Pod。正式 RunPod 验收使用 `prod-worker canary --profile scail2` 或 `scripts/runpod_prod_ops.sh canary --profile scail2`，串行提交同样两类 5s 正式内部任务，要求 `pop_evidence.agent_id=runpod_prod_scail2_manual_NN`，结果写 `user-data-prod`，canary 结束后目标 RunPod 默认恢复 `disabled`；通过后可与 LAN slot0 `lan_aio_prod_gpu002_gpu0_scail2_01` 并行 enabled 接单。

常用命令：

```bash
scripts/lan_scail2_aio_test.sh preflight
scripts/lan_scail2_aio_test.sh build-image
scripts/lan_scail2_aio_test.sh push-image
scripts/lan_scail2_aio_test.sh start --execute
scripts/lan_scail2_aio_test.sh verify
scripts/lan_scail2_aio_test.sh run-sample
scripts/lan_scail2_aio_test.sh restore --execute
scripts/lan_scail2_aio_prod.sh preflight --execute
scripts/lan_scail2_aio_prod.sh start-disabled --execute
scripts/lan_scail2_aio_prod.sh verify --execute
scripts/lan_scail2_aio_prod.sh enable --execute
scripts/lan_scail2_aio_prod.sh rollback --execute
```

`run-sample` 只自动提交 `SCAIL-2_Animation.json`，使用 Nomadoor reference image 和 motion video；另外三个 workflow 只做 `/object_info` 节点、模型枚举与 API prompt 转换 dry-run。生成后的最新 `SCAIL-2*.mp4` 复制到 `gpu-002:/root/scail2-test-results/<timestamp>/`。测试容器默认保留运行，方便继续在 `http://192.168.1.2:8190/` 手工切换 workflow；恢复图生图 slot0 时执行 `restore --execute`，它会停测试容器、启动原 slot0 AIO 并将 `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 恢复为 `enabled`。

密钥边界：

- 真实密钥只放在 ignored env 文件，例如 `.env.lan.model-cache`、`.env.lan-aio-test` 和 `.env.lan-aio-prod`；生产 helper 也可用 allowlist 从 `.env.cloud.prod` 与 `.env.lan.model-cache` 读取必要变量，不直接 `source`。
- compose 模板只允许出现 `${LAN_AIO_*:?}` / `${LAN_MODEL_CACHE_*:?}` 占位符。
- 不要直接 `source .env.cloud.test`；RunPod dry-run 继续只使用 controller 的 `--env-file` loader。
- LAN 模型缓存 bucket 固定为 `allbot-model-cache`；截至 2026-06-22，`192.168.1.115:9010` 已缓存 `img2img_lora/2026-06-10/manifest.json`、`i2i_pro/2026-06-14-test/manifest.json`、`scail2/2026-06-17-test/manifest.json` 与 `ltx_video/2026-06-10/manifest.json`。LAN LTX 缓存可能仍有旧 v1 残留；云端 R2 `ltx_video/2026-06-10/manifest.json` 当前是 10Eros v1.2-only，正式 RunPod 不依赖旧 v1 回退。
- 全任务 LAN cache 入口为 `scripts/upload_all_task_models_to_lan_cache.py --env-file .env.lan.model-cache`，默认 dry-run；真实上传必须另行显式加 `--execute`。helper 复用共享对象池 `models/by-sha256/<sha[:2]>/<sha>`，并会复用已存在且 size/sha256 metadata 匹配的旧对象 key。
- canonical manifest 中 Wan22 AIO、`image_to_video`、`wan22_video_v2` 的下一不可变候选分别是各自独立的 `2026-07-18-lora5/manifest.json`，旧 6 月 key 不覆盖。本地 registry 的 `wan22_explicit_lora_library/2026-07-18` 已完成 49 High + 49 Low 下载和文件存在性核对；LAN/R2 组装入口会把该 bundle 合入 Wan22 AIO union，并把全部 98 个显式 LoRA 文件同时纳入旧图生视频和 v2 split。对象上传后须逐项核对 size/SHA metadata，三个 manifest 使用 SHA-256 metadata 锁定；任一对象或 checksum 不符时禁止发布/切换。
- `pornmaster_flux2_edit/2026-06-27/manifest.json` 是新增测试目标，不纳入全任务批量上传；本地 registry manifest 已完整缓存，后续用 `scripts/import_pornmaster_flux2_edit_models.py --download-unet --execute` 复核或更新，再用 `scripts/upload_pornmaster_flux2_edit_models_to_lan_cache.sh --execute` 单独上传到 LAN cache。若 PornMaster 9B UNET 缺失或未授权，导入脚本应返回 `pornmaster_unet_missing_or_unauthorized` 并拒绝写半截 manifest。
- 单 bundle 通用入口仍为 `scripts/upload_model_bundle_to_r2.py`，通过 `.env.lan.model-cache` 映射 `LAN_MODEL_CACHE_*` 到 `RUNPOD_MODEL_*` 后写入 LAN cache；脚本按对象 size 与 sha256 metadata 跳过已有对象，metadata key 需大小写不敏感处理以兼容 MinIO。

## 4. RunPod Provider v0

RunPod provider 当前覆盖五类路径：

| 路径 | 用途 | 当前状态 |
| :--- | :--- | :--- |
| 云测试图生图 canary | `img2img` / `img2img_lora` 真实 Web 闭环 | 已通过真实 canary；作为 RunPod 基础链路回归入口 |
| 云测试 split video canary | `image_to_video` 与 `wan22_video_v2` 分 profile 验证 | `wan22_video_v2` 已完成 Web 端真实闭环；后续以 `split-video-canary` 复验 |
| 云测试图生图 Pro canary | `i2i_pro` RunPod runtime profile，串行验证 `i2i_pro`、Web `txt2img`、`face_swap_v2` | V2 路由发布候选必须重新执行三任务 canary；由 `runpod canary --task-type i2i_pro` 承担，不能沿用旧共享 `face_swap` 路由的验收结论 |
| 云测试 SCAIL-2 canary | `scail2` RunPod runtime profile，串行验证动作迁移和视频换人 | 用于 cloud-test；会临时 disable 同环境非 RunPod SCAIL-2 worker |
| 手动云正式备用 worker / Dashboard 自动管理 | `img2img`、`image_to_video`、`wan22_video_v2`、`i2i_pro`、`scail2`、`ltx_video` | 底层 `prod-worker` 仍是手动安全入口；Dashboard 后端可按队列等待阈值自动调用 `add` / `down` |

RunPod 只读 / dry-run 命令：

```bash
python scripts/gpu_pool_controller.py runpod validate-key
python scripts/gpu_pool_controller.py runpod list-pods
python scripts/gpu_pool_controller.py runpod reconcile-managed-pods
python scripts/gpu_pool_controller.py runpod render-create --task-type img2img_lora --env cloud-test
python scripts/gpu_pool_controller.py runpod render-create --task-type i2i_pro --env cloud-test
python scripts/gpu_pool_controller.py runpod render-create --task-type scail2 --env cloud-test
python scripts/gpu_pool_controller.py runpod create-pod --task-type img2img_lora --env cloud-test
python scripts/gpu_pool_controller.py runpod canary --env-file .env.cloud.test --quiet
python scripts/gpu_pool_controller.py runpod canary --task-type i2i_pro --env-file .env.cloud.test --quiet
python scripts/gpu_pool_controller.py runpod canary --task-type scail2 --env-file .env.cloud.test --quiet
python scripts/gpu_pool_controller.py runpod prod-worker render --profile scail2 --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile scail2 --slot 01
```

`render-create` 不需要 `RUNPOD_API_KEY`；`create-pod` 默认 dry-run。

## 5. RunPod Profile 矩阵

云测试 profile：

| Profile | `SUPPORTED_TASK_TYPES` | `POOL_RUNTIME_PROFILE` | Agent prefix | 模型 manifest |
| :--- | :--- | :--- | :--- | :--- |
| `img2img_lora` / `img2img` | `img2img,img2img_lora` | `img2img_lora` | `runpod_test_img2img_lora` | `img2img_lora/2026-06-10/manifest.json` |
| `image_to_video` | `image_to_video` | `image_to_video` | `runpod_test_image_to_video` | `image_to_video/2026-07-18-lora5/manifest.json` |
| `wan22_video_v2` | `wan22_video_v2` | `wan22_video_v2` | `runpod_test_wan22_video_v2` | `wan22_video_v2/2026-07-18-lora5/manifest.json` |
| `i2i_pro` | `i2i_pro,t2i-pornmaster-turbo,face_swap_v2` | `i2i_pro` | `runpod_test_i2i_pro` | `i2i_pro/2026-06-14-test/manifest.json` |
| `scail2` | `scail2_action_transfer,scail2_video_replacement` | `scail2` | `runpod_test_scail2` | `scail2/2026-06-17-test/manifest.json` |
| `pornmaster_flux2_edit` | `pornmaster_flux2_single_edit,pornmaster_flux2_multi_edit` | `pornmaster_flux2_edit` | `runpod_test_pornmaster_flux2_edit` | `pornmaster_flux2_edit/2026-06-27/manifest.json` |
| `wan22_aio_video` | `image_to_video,wan22_video_v2` | `wan22_aio_video` | `runpod_test_wan22_aio_video` | `wan22_aio_video/2026-07-18-lora5/manifest.json` |

`wan22_aio_video` 只保留为兼容/回滚 profile；新测试、新扩容和正式接入都应优先使用 split profile。
`video_basic` 不再作为独立对外任务或主 manifest 口径；GPU Pool Controller 中新增 canonical `image_to_video` profile，`video_basic` profile 仅保留 legacy 兼容命名，实际 workflow 与模型 manifest 均对齐 `image_to_video`。
`i2i_pro` 是现有 ComfyUI runtime profile；其中 Web 文生图仍提交 `txt2img`，Central 执行面记录为 `t2i-pornmaster-turbo`，worker 通过 `TASK_TYPE_WORKFLOW_OVERRIDES` 读取 `txt2img_from_i2i_pro.json`。新版图片换脸提交独立执行类型 `face_swap_v2`，worker 通过 override 读取 `face_swap_v2.json`；旧 `face_swap` 不再进入该 profile，继续由 V1 Worker 读取 `face_swap.json`。
`wan22_video_v2` RunPod split profile 默认渲染 `COMFY_EXTRA_ARGS=--disable-dynamic-vram`，用于规避 cu128 ComfyUI 0.21.x 的 DynamicVRAM/comfy-aimdo 在 `WanTEModel` 动态加载阶段卡住；如需临时实验其它 Comfy 启动参数，可用 `RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS` 覆盖，并必须重新创建目标 Pod 才会生效。

手动正式 profile：

| `prod-worker --profile` | Agent id | `SUPPORTED_TASK_TYPES` | 模型 manifest | GPU |
| :--- | :--- | :--- | :--- | :--- |
| `img2img` | `runpod_prod_img2img_manual_NN` | `img2img,img2img_lora` | `img2img_lora/2026-06-10/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `image_to_video` | `runpod_prod_image_to_video_manual_NN` | `image_to_video` | `image_to_video/2026-07-18-lora5/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `wan22_video_v2` | `runpod_prod_wan22_video_v2_manual_NN` | `wan22_video_v2` | `wan22_video_v2/2026-07-18-lora5/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `i2i_pro` | `runpod_prod_i2i_pro_manual_NN` | `i2i_pro,t2i-pornmaster-turbo,face_swap_v2` | `i2i_pro/2026-06-14-test/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `scail2` | `runpod_prod_scail2_manual_NN` | `scail2_action_transfer,scail2_video_replacement` | `scail2/2026-06-17-test/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `ltx_video` | `runpod_prod_ltx_video_manual_NN` | `ltx_video,ltx_video_flf2v,ltx_video_v2v_audio` | `ltx_video/2026-06-10/manifest.json` | `NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090` |

正式 RunPod 更新使用 `scripts/runpod_prod_ops.sh rollout-release --release-index <index> --sha <sha> --profile <profile> --slot <NN> --strategy direct|standard`，镜像名必须是 release index 的 digest ref。每次只处理一个 slot：旧 image 先记录，新 Pod 保持 disabled，通过实际 image/worker/heartbeat 检查后 enable；失败删除目标 Pod、恢复旧 exact image 并停止。镜像默认 CMD 为 baked runtime entrypoint，不以 `bootstrap_from_git` 或 mutable tag 作为新发布入口。
若迁移前的 legacy Pod 仍只报告历史 tag，执行 rollout 时必须额外传入已独立核验、与 live image 同仓库的 `--rollback-ref <repo@sha256:...>`；wrapper 不自动把 tag 当作回滚证据，也不接受跨仓库或 mutable rollback ref。新建 Pod 仍只使用 release index 中的 digest ref。

同一 main SHA 的 profile 构建完成后，使用 `scripts/gpu_profile_release_v2.py` 逐项校验
digest、baked revision、模型 manifest checksum 与回滚 digest；最后一个 profile 传
`--publish-ref ghcr.io/giraffu/allbot-gpu-release-manifests:<full-sha>` 发布完整 OCI manifest。
main modular release 自动读取该 ref；任一本轮重建 profile 缺失或仍是旧 `source_sha` 都会在
release bundle 发布前阻断。`i2i_pro` 的 canonical task types 固定为
`i2i_pro,t2i-pornmaster-turbo,face_swap_v2`，旧 `face_swap` 只留在 V1 worker。

## 6. 真实执行门禁

任意真实 RunPod mutation 都必须显式满足：

```dotenv
RUNPOD_DRY_RUN=false
RUNPOD_AUTOSCALER_ENABLED=true
```

并带对应 CLI 的 `--execute`。

`RUNPOD_MAX_PODS_TOTAL`、`RUNPOD_MAX_PODS_PER_TYPE`、`RUNPOD_MAX_HOURLY_COST_USD`
不再作为 provider/Dashboard 的容量或成本门禁；不要依赖它们阻断创建。云正式手动池的
slot 命名空间由 `RUNPOD_PROD_MAX_MANUAL_SLOTS` 控制，默认 `100`，只用于生成
`manual_01..manual_100` agent/pod 名称。

云测试 split video canary：

- 默认同时测 `image_to_video` 与 `wan22_video_v2`，完成后必须恢复 worker control 并删除 Pod。
- 传 `--profile image_to_video` 或 `--profile wan22_video_v2` 时只创建 1 个 Pod。
- 若只允许 4090，可临时覆盖 `RUNPOD_GPU_TYPE_IDS_WAN22_VIDEO_V2='NVIDIA GeForce RTX 4090'`。
- 失败或中断后必须恢复 worker control、删除 Pod，并用 `list-pods` / `reconcile-managed-pods` 确认 managed count 为 0。

## 7. 云测试 canary

云测试 canary runner 仍有自己的单次测试安全门禁；这不适用于 Dashboard / cloud-prod
`prod-worker add`。图生图默认 canary：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod canary \
  --env-file .env.cloud.test \
  --download-results-dir /tmp/allbot_runpod_canary/results \
  --execute
```

split video manifest 与 canary：

```bash
python scripts/gpu_pool_controller.py runpod split-video-manifests \
  --env-file .env.cloud.test

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=2 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod split-video-canary \
  --env-file .env.cloud.test \
  --execute
```

分 profile scale dry-run：

```bash
python scripts/gpu_pool_controller.py runpod workers render-scale \
  --profile image_to_video \
  --desired 1 \
  --env cloud-test
python scripts/gpu_pool_controller.py runpod workers render-scale \
  --profile wan22_video_v2 \
  --desired 1 \
  --env cloud-test
python scripts/gpu_pool_controller.py runpod workers render-scale \
  --profile i2i_pro \
  --desired 1 \
  --env cloud-test
```

canary 摘要只允许记录脱敏后的 object key、task id、Central/Web 终态、下载后的本地路径和去掉 query string 的 result path；不要输出 JWT、agent token、presigned URL、完整 env 或完整 create payload。

内部代码边界：`runpod_canary.py` 与 `runpod_split_video_canary.py` 继续保留
CLI lifecycle、RunPod Pod 创建/等待/清理和旧私有方法兼容入口；HTTP JSON/raw、
URL 脱敏、Web JWT / bearer token、agent control、`/system/workers` 读取、任务
case payload、Central 终态等待、pop evidence、Web result 等待、R2 fallback 和
MP4/PNG/last-frame 下载校验已收口到 `runpod_http.py`、`runpod_control.py` 与
`runpod_cloud_test_canary.py`。新增 cloud-test canary profile 或调整任务 payload 时，
优先在 `runpod_cloud_test_canary.py` 增加 case/executor focused tests，再通过旧 runner
做集成回归，避免重新把 HTTP/control/下载逻辑写回 runner。

`i2i_pro` cloud-test canary 必须通过 Web API 创建真实任务，而不是只做 worker 直测。V2 路由 canary 会串行提交 `i2i_pro`、Web `txt2img` 和 `face_swap_v2` 三单。验收口径：

- RunPod worker heartbeat 出现为 `runpod_test_i2i_pro_*`。
- Central 任务类型分别为 `i2i_pro`、`t2i-pornmaster-turbo`、`face_swap_v2`，每单 `pop_evidence.agent_id` 都匹配该 RunPod worker；该 worker 不得声明或接走 `face_swap`。
- 三单 Web result 均为 `success`，最终状态均为 `done`，图片结果可下载。
- 验收结束后恢复临时禁用的非 RunPod cloud-test `i2i_pro/t2i-pornmaster-turbo/face_swap_v2` worker，删除 Pod，并确认 managed RunPod count 回到 0。

当测试服 canary 需要与现有云正式手动备用 Pod 共存时，必须显式传
`--allow-existing-prod-managed-pods` 或设置
`RUNPOD_CANARY_ALLOW_EXISTING_PROD_MANAGED_PODS=true`。该开关只忽略名称前缀为
`allbot-runpod-prod-img2img-manual-`、`allbot-runpod-prod-image-to-video-manual-`、
`allbot-runpod-prod-wan22-video-v2-manual-`、`allbot-runpod-prod-i2i-pro-manual-`
的既有 managed Pod；任何 cloud-test
残留 Pod 仍会阻止 `canary --execute`。开启后 `RUNPOD_MAX_PODS_TOTAL=1`
表示“本次 cloud-test canary 只允许创建 1 个非忽略 Pod”，cleanup 验收也按
非忽略 managed Pod 数量回到 0 计算。失败现场用 `--no-cleanup` 保留的新
`i2i_pro` Pod 可通过 `--reuse-pod-id i2i_pro=<pod_id>` 复跑 Web 任务，避免重复创建 Pod。

cloud-test 诊断 Pod 如需 SSH，`.env.cloud.test` 可设置
`RUNPOD_PUBLIC_KEY_FILE=~/.ssh/allbot_runpod_debug_20260613_ed25519.pub` 或
`RUNPOD_PUBLIC_KEY=<ssh public key>`。provider 会把它渲染为 Pod env `PUBLIC_KEY`，
bootstrap 启动 sshd 时写入 `/root/.ssh/authorized_keys`；不要写入私钥，也不要把该
能力扩展为生产 Pod 的长期 SSH 入口。`yanwk/comfyui-boot:cu128-slim` 是
openSUSE Tumbleweed 基线，镜像内必须安装 `openssh`，否则 RunPod proxy SSH 可用但
direct TCP `root@<public-ip> -p <mapped-port>` 会因容器内无 `sshd` 而拒绝连接。

## 8. 手动云正式备用 worker

正式 RunPod worker 只作为手动备用，不自动按生产队列扩容。

日常入口优先使用 `scripts/runpod_prod_ops.sh`。它不改变底层 `prod-worker` 语义，只把正式手动备用池的常见动作收窄成固定 SOP；所有 mutation 默认 dry-run，真实执行必须显式 `--execute`，且必须指定 `--profile`。

| 日常动作 | 命令 | 语义 |
| :--- | :--- | :--- |
| 状态汇总 | `scripts/runpod_prod_ops.sh status` | 按 profile 汇总 managed Pod、Central heartbeat 与 control state |
| 启动备用 Pod | `scripts/runpod_prod_ops.sh up --profile img2img --execute` | 创建/启动 Pod 并等待 disabled heartbeat，不自动接单 |
| 放开接单 | `scripts/runpod_prod_ops.sh enable --profile img2img --slot 01 --execute` | 仅修改 Central control 为 enabled |
| 停止接单 | `scripts/runpod_prod_ops.sh disable --profile img2img --slot 01 --execute` | 保留 Pod，设置 Central control 为 disabled |
| 原地重启 | `scripts/runpod_prod_ops.sh restart --profile img2img --slot 01 --execute` | 调用 RunPod 原生 restart，不使用 stop/start，等待 heartbeat 并恢复 enabled；若等待阶段失败但复查确认 Pod RUNNING、worker idle 且 control 仍是本次 restart disable，会安全补一次 enable |
| 删除 Pod | `scripts/runpod_prod_ops.sh down --profile img2img --slot 01 --execute` | disable 后等待 `current_task_id` 为空，再删除目标 Pod |
| 新增容量 | `scripts/runpod_prod_ops.sh add --profile img2img --count 1 --execute` | 只创建空闲 slot，不触碰已有 RunPod；新 slot ready 后自动 enable |
| 高级精确目标 | `scripts/runpod_prod_ops.sh scale --profile img2img --desired 1 --execute` | 会删除超出 desired 的 slot，Dashboard 禁止使用 |
| 业务 canary | `scripts/runpod_prod_ops.sh canary --profile img2img --slot 01 --execute` | 真实 Web canary，结束后保持目标 worker disabled |
| 回滚 | `scripts/runpod_prod_ops.sh rollback --profile img2img --keep-pod --execute` 或 `--delete-pod` | `--keep-pod` 等价 disable；`--delete-pod` 在指定 slot 时走 down，未指定 slot 时走 `scale --desired 0` |

RunPod 4090 库存不足或 create-pod 返回机器资源/稍后再试类 500 时，`up/add/scale`
可显式使用有界重试，不要开多条并发创建循环。日常新增模板：

```bash
scripts/runpod_prod_ops.sh add \
  --profile img2img \
  --count 2 \
  --retry-unavailable \
  --max-attempts 100 \
  --retry-interval 30 \
  --execute
```

`add --count N --execute` 对 RunPod create 的“半成功”有窄恢复：如果 create 返回失败，但复查目标 slot 的 Pod 已是 `RUNNING`、对应 worker 是 `idle` 且 Central control 仍是本次 create 写入的 `disabled`，控制器会继续等待/确认 disabled heartbeat 并 enable 该新 slot。若目标 Pod 不存在、worker 不健康、control 已被其它操作改动或 task type 不匹配，operation 仍保持失败，等待人工排障。

Dashboard 系统监控页也提供正式手动 RunPod 池的日常 Web 入口：

| Dashboard 动作 | 后端 API | 底层命令语义 |
| :--- | :--- | :--- |
| `RunPod 管理` 提交多 profile 新增数量 | `POST /api/runpod/scale` | 拆成 profile 级 `scripts/runpod_prod_ops.sh add --count N --retry-unavailable --execute` operation |
| Worker 卡片 `暂停/开启` (RunPod) | `POST /api/runpod/workers/{agent_id}/pause` / `POST /api/runpod/workers/{agent_id}/enable` | `disable\|enable --slot NN --execute`，只切换 Central control，不创建/删除 Pod |
| Worker 卡片 `暂停/开启` (LAN AIO) | `POST /api/runpod/lan-aio/workers/{agent_id}/pause` / `POST /api/runpod/lan-aio/workers/{agent_id}/enable` | `lan_aio_fleet_prod_ops.py disable-aio\|enable-aio --slot ... --execute`，只切换目标 AIO agent 是否接新单；enable 仍执行 AIO gate 校验 |
| Worker 卡片 `重启` (RunPod) | `POST /api/runpod/workers/{agent_id}/restart` | `restart --slot NN --execute`，先 disabled，调用 RunPod 原生 restart，等待 heartbeat 后 enable；若底层等待阶段失败但目标已健康 idle，会安全恢复 enabled；禁止用 stop/start 模拟重启 |
| Worker 卡片 `重启` (LAN AIO) | `POST /api/runpod/lan-aio/workers/{agent_id}/restart` | `lan_aio_fleet_prod_ops.py restart-aio --slot ... --execute`，只重启目标 AIO 容器，等待健康/heartbeat 后 enable |
| Worker 卡片 `删除` | `DELETE /api/runpod/workers/{agent_id}` | `down --slot NN --execute`，先停接并等待当前任务结束，再删除 Pod |
| LAN AIO slot/candidate 管理 | 无 Dashboard API | `GET /api/runpod/lan-aio/profiles`、`GET /api/runpod/lan-aio/slots`、`POST /api/runpod/lan-aio/slots/{slot_id}/{action}` 已移除；候选切换、缓存预热、takeover/recover 只由本地 AI operator/CLI 通过 `scripts/lan_aio_fleet_prod_ops.py` 执行 |
| 最近操作 | `GET /api/runpod/operations` | 读取 Redis 持久 operation 状态和脱敏日志尾部；Dashboard 多 worker 或容器重建后，会用 Central worker 快照收口已实际成功的 detached add |
| 最近操作 `终止` | `POST /api/runpod/operations/{operation_id}/terminate` | 仅用于运行中的 `add` operation；终止 Dashboard 子进程后，按该次新增日志记录到的 slot 逐个执行 `down --slot NN --execute` 释放 Pod |

Dashboard 入口不重写 RunPod provider 逻辑，只异步调用 `scripts/runpod_prod_ops.sh`。在启动 operation 子进程时，Dashboard 必须从 `runpod_profile_catalog.py` 强制注入已验收的 img2img 与 PornMaster baked 镜像 ref；`runpod_prod_worker.load_env_file_for_prod_worker()` 会保护已有 `RUNPOD_*`，因此 `/app/.env` 中的历史镜像值不能把它覆盖回旧产物。该 pin 同时覆盖手动新增和 autoscaler add/retry；目标 GHCR tag 尚未发布或未完成 baked entrypoint/revision smoke 时不得先部署 Dashboard。PornMaster FP8 与 BF16 继续共用同一个 runtime 镜像和既有 single/multiple workflow，差异只由 task type、模型 manifest、BF16 RTX 4090/`--lowvram` 与对应 UNet 节点替换表达。LAN AIO slot/candidate 管理已从 Dashboard 移除，不再提供 profile/slot 列表、一键切换、恢复、巡检或 warm-cache 操作；候选切换、缓存预热、takeover/recover、retarget 与本地服务巡检只由本地主 AI operator/CLI 通过 `scripts/lan_aio_fleet_prod_ops.py` 执行。Worker 卡片看到 `control_state=disabled|draining` 时显示 `暂停中`，接单控制按钮显示 `开启`；其它状态显示 `暂停`。LAN AIO Worker 卡片只保留状态、当前任务、`暂停/开启/重启`，后端只允许受限 `disable-aio|enable-aio|restart-aio`，不触碰候选切换、缓存预热、takeover/recover 或 retarget。

RunPod Worker 卡片提供 `锁定/解锁`，后端 API 为 `POST /api/runpod/workers/{agent_id}/lock|unlock`、`GET /api/runpod/workers/locks`；锁记录持久化在 operation store 的 `dashboard:runpod:locked_workers`，`/api/system/workers` 会标注 `runpod_locked` 并显示 `已锁定`。锁定后 Dashboard 手动 `DELETE /api/runpod/workers/{agent_id}` 返回 409，autoscaler 缩容与 add 失败/终止 cleanup 的 `down` 都会跳过该 worker，直到再次解锁。数量字段是新增数量；旧前端若仍发送 `desired_count`，后端也按新增数量解释，不会触发 `scale --desired` 或删除既有 slot。当前 Dashboard 手动 RunPod profile 列表包含 `img2img`、`image_to_video`、`wan22_video_v2`、`i2i_pro`、`scail2 / 视频生视频`、`ltx_video / 高级图生视频` 与 `pornmaster_flux2 / 自由P图 v2`；`scail2` 对应 `scail2_action_transfer,scail2_video_replacement` 两类正式任务，`ltx_video` 对应 `ltx_video,ltx_video_flf2v,ltx_video_v2v_audio`，`pornmaster_flux2_edit` 对应 `pornmaster_flux2_single_edit,pornmaster_flux2_multi_edit`。系统监控页的活跃 Worker 详情前端会基于 Dashboard `/api/system/status.runpod_profile_queue_details` 的 profile 列表和 `/api/system/status.queue_by_type_details` 的任务类型明细聚合活跃数/pending、最长 pending 等待和非低信任最长 pending 等待；其中活跃数不是 worker 数，真实 RunPod/本地 worker 数由 `/api/system/workers` 心跳另算。`scail2` 展示会额外折入 LAN 正式可承接的 `scail2_action_transfer_long` 与 `scail2_face_swap_v2`，但正式 RunPod `scail2` autoscaler、清空阈值和单任务耗时设置仍只按 `scail2_action_transfer,scail2_video_replacement` 生效，避免自动扩容误接不能承载的任务。`pornmaster_flux2_edit` 返回 `autoscaler_enabled=true` 并进入 Dashboard RunPod autoscaler 自动 add/down，默认按单任务 30 秒和 30 分钟清空阈值估算，也可手动新增/暂停/删除；`i2i_pro` 汇总 `i2i_pro,t2i-pornmaster-turbo,face_swap_v2`，旧 `face_swap` 只保留独立队列展示耗时，不触发 i2i_pro autoscaler。同一请求里同一 profile 只能出现一次；若同 profile 已有未结束的 `add` operation，Dashboard 后端会返回 409，禁止再次提交，避免并发新增抢到同一个 `manual_NN` slot。后台 operation 默认使用 30 秒间隔、100 次无库存重试，真实执行只打开 `RUNPOD_DRY_RUN=false` 与 `RUNPOD_AUTOSCALER_ENABLED=true`，并把 `RUNPOD_PROD_MAX_MANUAL_SLOTS` 设为 `100` 或请求指定值。运行中的新增 operation 可从最近操作点 `终止`，后端会先向该 operation 的进程组发送 SIGTERM；如果该次 operation 已记录 `runpod_create_pod_NN`，会继续提交对应 slot 的 `down` 清理；若对应 RunPod worker 已锁定则跳过 cleanup 并记录 `skipped_locked`/`partial_locked`。未记录到创建 slot 的终止只停止等待/重试进程，不推测删除其它 Pod。

Dashboard operation 由 Redis 跨 Gunicorn worker 和容器重建持久化。读取“最近操作”时，后端只对 `status=running`、已从日志确认 `runpod_create_pod_NN`、且对应所有 `runpod_prod_<profile>_manual_NN` worker 在 heartbeat 新鲜窗口内为 `idle|running`、`control_state=enabled` 的 detached add 自动写回 `succeeded`、`exit_code=0` 并释放 profile active-add 锁。没有创建 slot、worker 缺失、heartbeat 过期、未启用或 unhealthy 时继续保持 `running`，不得仅因 Pod 存在就误报成功。

云正式 Dashboard 后端默认优先把容器内 `/app/.env` 同时作为 `--runpod-env-file` 与 `--prod-env-file`；该文件由云正式 `.env.cloud.prod` 挂载，必须包含完整、shell-compatible 的 `RUNPOD_*` 手动池配置和可用 `RUNPOD_API_KEY`。云正式 v2 Compose 固定 `DASHBOARD_LAN_AIO_EXECUTION_MODE=ssh`，并要求生产 env 提供非空 `DASHBOARD_LAN_AIO_RUNNER_HOST` 与 `DASHBOARD_LAN_AIO_RUNNER_KEY_DIR`；后者只读挂载精确 `id_ed25519` 到 `/app/runtime/lan-aio-runner/id_ed25519`。本地主保留 Tailscale SSH 的 22 端口，Dashboard runner 由用户级 `allbot-lan-aio-dashboard-runner-sshd.service` 在 Tailscale 地址上独立监听 OpenSSH 2222 端口，可用 `DASHBOARD_LAN_AIO_RUNNER_SSH_PORT` 覆盖。发布器只读 preflight 会检查宿主 key 存在、可读、权限为 `600`，并实际连接 runner 核对 helper、正式 env 与模型缓存 env 可读；缺项在 env/Compose/preflight 阶段 fail closed，禁止回退到云容器内执行不存在的 `lan_aio_fleet_prod_ops.py`。受限的 `disable-aio|enable-aio|restart-aio` 必须落在本地主服务器 runner 上，避免把 LAN GPU SSH key 或 `192.168.1.0/24` 私网路由放进云控制面；即使 overlay 漂移，后端看到 `ALLBOT_ENV=prod` 也默认选择 SSH 并在 runner host 缺失时返回可读 503。`DASHBOARD_LAN_AIO_RUNNER_PROJECT_ROOT` 默认 `/home/hfy/APP/All_bot`，远端 runner 默认读取 `<runner-root>/.env.cloud.prod`、`<runner-root>/.env.lan-aio-prod`、`<runner-root>/.env.lan.model-cache`，可用 `DASHBOARD_LAN_AIO_RUNNER_PROD_ENV_FILE`、`DASHBOARD_LAN_AIO_RUNNER_AIO_ENV_FILE`、`DASHBOARD_LAN_AIO_RUNNER_MODEL_ENV_FILE` 覆盖。若本地主交互环境依赖本地代理访问正式公网域名，云端 runner 还应配置 `DASHBOARD_LAN_AIO_RUNNER_HTTP_PROXY`、`DASHBOARD_LAN_AIO_RUNNER_HTTPS_PROXY`、`DASHBOARD_LAN_AIO_RUNNER_ALL_PROXY` 和 `DASHBOARD_LAN_AIO_RUNNER_NO_PROXY`，后端会在远端命令中同时导出大小写 proxy 变量；`NO_PROXY` 至少覆盖 LAN registry/model-cache 和目标 GPU IP。更换 key 或 runner 用户时只改受限云正式 env/key 目录和本地主 `authorized_keys`，不要改代码；不得在 API 响应、operation 日志或文档中输出任何 env 内容或密钥。

Dashboard 后端的 RunPod autoscaler 只复用上述安全入口，不直接调用 RunPod API。`pornmaster_flux2_edit_bf16 / 自由P图 v3` 与其它正式 profile 一样进入 autoscaler，默认单任务耗时 30 秒、清空阈值 30 分钟，并复用自动 add/down/restart/enable、锁定跳过、最短生命周期、冷却和失败清理。正式启用时
`DASHBOARD_RUNPOD_AUTOSCALER_ENABLED=true`，后台循环默认每 60 秒读取
`/api/system/status.runpod_profile_queue_details` 与 `/api/system/workers`：某 profile
存在已知非低信任 pending，且预计非低信任用户清空时间超过该 profile 清空阈值时，若该 profile 当前 RunPod 数小于
`DASHBOARD_RUNPOD_AUTOSCALER_MAX_RUNPODS_PER_PROFILE`（默认 5）且没有同 profile 未完成 operation，
则每轮最多提交一次
`add --count 1 --retry-unavailable --max-attempts 100 --retry-interval 30 --worker-timeout 2400 --execute`。
预计非低信任用户清空时间按静态单任务耗时估算：先用 `non_low_trust_clear_pending_count_by_task_type`
统计 Central pending 队列中清到最后一个已知非低信任任务所需的同 profile 前缀任务数，再计算
`pending_work_seconds=sum(non_low_trust_clear_pending_count_by_task_type * task_duration_seconds)`，
再加 running worker 的预计剩余秒数后除以 RunPod + 本地健康 enabled 可接单 worker 数；总
`pending_count_by_task_type` 只保留为 `estimated_total_pending_work_seconds` 观测对照，不参与扩容判定。
若某 profile 只有低信任或未知用户 pending，则记录 `hold: no non-low-trust backlog`，不会因总 pending
或总预计清空时间扩容。有非低信任 backlog
但无可接单 worker 时标记 `capacity_status=no_accepting_workers`，允许扩容。清空阈值默认按 profile
生效：`img2img=20 分钟`、`scail2=40 分钟`，其它正式 profile
（`image_to_video`、`wan22_video_v2`、`i2i_pro`、`ltx_video`）为 `30 分钟`；
系统监控页“活跃 Worker 详情”的“清空阈值”列可保存 profile 级分钟数，后端写入 Redis
并由 `/api/runpod/autoscaler/settings` 合并到下一轮评估；同一表格的“自动管理”按钮通过
`profile_autoscaler_paused_by_profile` 保存 profile 级暂停状态，暂停后该 profile 决策直接
`hold: profile autoscaler paused`，不会再自动 add/down/restart/enable，不影响其它 profile，也不改变
已有 worker 接单状态。`DASHBOARD_RUNPOD_AUTOSCALER_SCALE_UP_WAIT_SECONDS`
仅作为未配置 profile 的 fallback。静态耗时可通过同一 settings API 的 `task_duration_seconds_by_type`
更新，允许 1-3600 秒；默认值为 `img2img/img2img_lora=13s`、`image_to_video/wan22_video_v2=60s`、
`i2i_pro/t2i-pornmaster-turbo/face_swap_v2=12s`；旧 `face_swap=12s` 只保留展示耗时，不纳入 i2i_pro autoscaler。`scail2_action_transfer/scail2_video_replacement=300s`、
`ltx_video/ltx_video_flf2v/ltx_video_v2v_audio=120s`、unknown `100s`。新增 operation 完成或失败后，
同 profile 默认冷却 600 秒；但 autoscaler add 若已创建 slot 且因
`DASHBOARD_RUNPOD_AUTOSCALER_BOOTSTRAP_TIMEOUT_SECONDS`（默认 2400）内没有健康 heartbeat 失败，会自动对记录到的
slot 执行 `down --slot NN --execute` 清理，清理成功后不进入 cooldown，下一轮可重新 add。同 profile 在
`DASHBOARD_RUNPOD_AUTOSCALER_BOOTSTRAP_REPLACEMENT_WINDOW_SECONDS`（默认 7200）内最多替换
`DASHBOARD_RUNPOD_AUTOSCALER_BOOTSTRAP_REPLACEMENT_LIMIT`（默认 2）次，超过后显示
`hold: bootstrap replacement limit reached`。缩容只在 `pending_count == 0` 时考虑，若 RunPod + 本地健康 enabled 可接单
worker 总数大于 1，则在未锁定的 idle RunPod 里选择该 profile 最高 slot 执行 `down --slot NN --execute`；若 idle RunPod 全部已锁定则记录
`hold: all idle runpod candidates are locked`。autoscaler
创建的 RunPod 未满 `DASHBOARD_RUNPOD_AUTOSCALER_MIN_RUNPOD_LIFETIME_SECONDS`（默认 1800）不会被缩容。
autoscaler 会优先自愈正式 RunPod worker：`status=error|quarantined` 且 `last_error_at` 已持续超过
`DASHBOARD_RUNPOD_AUTOSCALER_FAULT_RESTART_SECONDS`（默认 300）时，提交
`restart --slot NN --execute`；`control_state=disabled|draining` 且 worker 仍健康 `idle|running`
时，提交 `enable --slot NN --execute`。成功的 Dashboard `delete` operation 会按
`DASHBOARD_RUNPOD_AUTOSCALER_HEARTBEAT_MAX_AGE_SECONDS` 建立同 agent 的短期删除墓碑；墓碑有效期内即使
Central 仍返回新鲜的 `disabled + idle|running` 残留 heartbeat，也必须保持
`hold: deleted runpod worker heartbeat awaiting expiry`，不得自动 enable。其它未删除的暂停 RunPod
仍可正常进入恢复候选，手动或 autoscaler 删除都遵循该边界。RunPod `restart` 底层会先 disabled、调用 RunPod 原生
restart、等待健康 heartbeat，再恢复 enabled 接单。本地 worker 只参与容量保底，不会被 autoscaler
启停。autoscaler 必须拿到 Redis leader lease 才执行 mutation；拿不到 Redis/leader 或系统快照失败时
只记录 hold/error。管理弹窗的 `/api/runpod/autoscaler` 与 `/api/runpod/autoscaler/control`
可查看 `scale_up: estimated non-low-trust clear time ...`、`restart: runpod fault persisted ...`、
`enable: runpod paused worker available`、`replace: previous runpod bootstrap timed out ...`、
`hold: runpod add still bootstrapping Ns`、`hold: no non-low-trust backlog`、`hold: no backlog`、`hold: max runpod capacity reached`、
`hold: profile autoscaler paused`、`hold: minimum lifetime remaining Ns`、
`hold: deleted runpod worker heartbeat awaiting expiry` 等决策并紧急暂停/恢复。

`down` 删除已有 Pod 的 preflight 只做 RunPod key、Pod 列表、reconcile 与 Central health 检查，不渲染 create pod request，因此不会因缺少 `RUNPOD_IMAGE_NAME_I2I_PRO` / `RUNPOD_IMAGE_NAME_SCAIL2` / `RUNPOD_IMAGE_NAME_LTX_VIDEO` 这类创建镜像配置而阻断删除；`up` / `add` / `render` / `canary` 仍必须具备目标 profile 的正式镜像与模型配置。

不可变云正式 Dashboard overlay 必须显式注入
`RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT`；Dashboard operation 子进程使用
`/dev/null` env-file 时会继承该容器环境，缺失变量必须在 Compose 渲染阶段 fail closed，
不能依赖现场进入容器补值。`pornmaster_flux2_edit_bf16` 不使用独立的
`pornmaster_flux2_edit_bf16.json`，而是通过 mapping 分别复用 single/multiple-images workflow，
再由 BF16 patcher 切换 UNet 节点 100/9。PornMaster profile 镜像 smoke 必须同时验证两份 workflow、
两个 `mappings.json` 条目和 `workflow_mapping_validation.py` 解析表，避免旧镜像在创建后才暴露缺文件。

底层高级命令：

```bash
python scripts/gpu_pool_controller.py runpod prod-worker render
python scripts/gpu_pool_controller.py runpod prod-worker status
python scripts/gpu_pool_controller.py runpod prod-worker up --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker enable --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker disable --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker restart --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker down --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker add --profile img2img --count 1
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker scale --profile img2img --desired 1
python scripts/gpu_pool_controller.py runpod prod-worker render --profile i2i_pro --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile i2i_pro --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker render --profile scail2 --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile scail2 --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker render --profile ltx_video --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile ltx_video --slot 01
```

`prod-worker` 默认先加载 `.env.cloud.test` 中的 RunPod API/profile 默认值，再加载 `.env.cloud.prod` 覆盖正式 Central/Web/R2/JWT 变量；已在 shell 显式设置的 `RUNPOD_*` 执行开关和 slot 命名空间不会被 prod env 文件覆盖。
优先用 `prod-worker status` 查看正式手动 worker，因为它会按上述规则加载 env；裸
`runpod list-pods` / `pod-readiness` 只读取当前 shell env，未显式加载 `RUNPOD_API_KEY`
时会返回 `missing_RUNPOD_API_KEY`。

操作语义速查：

| 命令 | 是否触碰 Pod 生命周期 | 是否放开接单 | 主要用途 |
| :--- | :--- | :--- | :--- |
| `render` / `status` | 否 | 否 | 渲染/观测，适合 AI 运维先读状态 |
| `up --execute` | 创建并启动目标 Pod | 否，默认写 `disabled` | 新增手动正式备用 worker，等待模型同步和 heartbeat |
| `add --count N --execute` | 只创建空闲 slot | 是，新 slot ready 后自动 enable | 日常新增容量，不触碰已有 slot |
| `enable --execute` | 否 | 是，仅改 Central control | 放开已有 Pod 接正式队列 |
| `disable --execute` | 否 | 否，仅改 Central control | 保留 Pod 现场、停止接新单，用于排障或维护 |
| `restart --execute` | 同一个 Pod 原生 restart，不 stop/start | 是，恢复后自动 enable；失败兜底只在 Pod RUNNING、worker idle、control 仍是本次 restart disable 时执行 | OOM/error/disabled 后原地恢复手动 RunPod worker，避免 stop 释放 GPU；没有固定网络卷时尤其禁止用 stop/start |
| `canary --execute` | 不创建已存在的 prod Pod | 临时 enable，结束恢复 `disabled` | 提交真实 Web 任务验证目标 worker |
| `down --execute` | 删除目标 prod Pod | 否 | 下线手动备用 Pod，必须确认无 `current_task_id` |
| `scale --desired N --execute` | 按 slot 创建/删除/enable/disable | 取决于计划 | 高级精确目标数入口，会删除超出 slot |

判断“RunPod 已启动并可接单”不能只看 Pod `RUNNING`：还必须看到 Central worker heartbeat，
且 agent control 为 `enabled`。`up --execute` 后处于 ready 但 `disabled` 是预期行为；需要
`enable --execute` 才会接正式任务。

### 8.1 云正式手动 RunPod 按需新增容量

正式手动 RunPod 池的容量和 profile 组合不是固定事实，应按当次运维目标决定。某次实操的
Pod 数量、创建日期和 profile 组合只应进入运维日志或工单，不作为长期 SOP。当前
`prod-worker` 支持 `--profile img2img|image_to_video|wan22_video_v2|i2i_pro|scail2|ltx_video`；日常扩容只使用“新增容量”语义：
`scripts/runpod_prod_ops.sh add --count N` 只选择该 profile 的最低空闲 manual slot 创建新
Pod，不 enable、disable、drain、delete 或 recreate 任何已存在 slot。

| 参数 | 含义 | 设置口径 |
| :--- | :--- | :--- |
| `PROFILE` | 本轮要操作的 profile | 例如 `img2img`、`image_to_video`、`wan22_video_v2`、`i2i_pro`、`scail2`、`ltx_video` |
| `COUNT` | 本轮新增 Pod 数 | 必须是正整数；不是目标总数 |
| `MANUAL_SLOT_LIMIT` | manual slot 命名空间 | 默认 `100`，只用于生成 `manual_01..manual_100` agent/pod 名称，不是容量或成本上限 |

新增示例：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${COUNT:?set number of new RunPod Pods to add}"
: "${MANUAL_SLOT_LIMIT:=100}"

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_PROD_MAX_MANUAL_SLOTS="$MANUAL_SLOT_LIMIT" \
scripts/runpod_prod_ops.sh add \
  --profile "$PROFILE" \
  --count "$COUNT" \
  --execute
```

多 profile 共存时，对每个目标 profile 分别执行一次 `add`。Dashboard 的
`POST /api/runpod/scale` 也按新增语义执行，即旧字段 `desired_count` 仍会被解释为
新增数量，不会 scale down 既有 Pod。

`add --count N --execute` / `scale --desired N --execute` / `up --execute` / `down --execute`
会在 prod-worker 内按 profile 持有文件锁，默认锁目录为 `/tmp/allbot_runpod_locks`
（可用 `RUNPOD_PROD_OPERATION_LOCK_DIR` 覆盖），防止多个进程同时为同一 profile 规划或
删除 slot。创建路径还会在每个 slot create 前重新读取 RunPod managed Pod 列表；如果
目标 slot 已被其它操作占用，会在写 Central control 和创建 Pod 前中止。`add --count N --execute`
会先把新 slot 的 Central control 写为 `disabled`，创建 Pod，等待 RunPod readiness、模型同步、ComfyUI ready 和 Central
heartbeat；看到 disabled heartbeat 后才 enable 目标 slot。启动过程中如果 Pod 已
`RUNNING` 但 `worker_seen=false`、control 仍是 `disabled`，通常表示 bootstrap 或模型同步
还没完成，不要手动 enable。

4090 库存不足或 RunPod create-pod 临时失败时，RunPod 可能返回
`There are no instances currently available`、`This machine does not have the resources to deploy your pod`
或 `Please try again later`。优先用
`scripts/runpod_prod_ops.sh add --retry-unavailable` 对同一个 profile/count 做有界重试；
不要同时开多条相同 profile/count 的创建循环，避免重复抢同一批空闲 slot。推荐模板：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${COUNT:?set number of new RunPod Pods to add}"
: "${MANUAL_SLOT_LIMIT:=100}"

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_PROD_MAX_MANUAL_SLOTS="$MANUAL_SLOT_LIMIT" \
scripts/runpod_prod_ops.sh add \
  --profile "$PROFILE" \
  --count "$COUNT" \
  --retry-unavailable \
  --max-attempts 100 \
  --retry-interval 30 \
  --execute
```

最终验收每个目标 slot：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${SLOT:?set target manual slot, for example 01}"
: "${MANUAL_SLOT_LIMIT:?set manual slot limit if needed}"

RUNPOD_PROD_MAX_MANUAL_SLOTS="$MANUAL_SLOT_LIMIT" \
python scripts/gpu_pool_controller.py runpod prod-worker status \
  --profile "$PROFILE" \
  --slot "$SLOT"
```

验收口径：`list_pods.count` / `reconcile.managed_count` 比新增前增加 `COUNT`、
`orphans=[]`、每个新增 worker 有 heartbeat，且 `control.state=enabled`。`worker.status=running`
可能表示正在接单，不等于异常；重点看 `types`、`runtime_profile`、`image_ref` 与目标
profile 是否一致。

### 8.2 正式 RunPod 停接、关闭与缩容

保留 Pod 但停止接新单：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${SLOT:?set target manual slot, for example 01}"

python scripts/gpu_pool_controller.py runpod prod-worker disable \
  --profile "$PROFILE" \
  --slot "$SLOT" \
  --execute
```

删除单个 Pod 前，先 `status` 确认目标 `current_task_id` 为空；若正在运行任务，等待自然结束，
不要用 RunPod UI 强删。删除示例：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${SLOT:?set target manual slot, for example 01}"
: "${MANUAL_SLOT_LIMIT:=100}"

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_PROD_MAX_MANUAL_SLOTS="$MANUAL_SLOT_LIMIT" \
python scripts/gpu_pool_controller.py runpod prod-worker down \
  --profile "$PROFILE" \
  --slot "$SLOT" \
  --execute
```

按 profile 精确调整目标数属于高级运维入口。`scale --desired N --execute` 会按 slot
计算计划、enable 保留 slot、disable 待删 worker、等待 drain，并删除超出 desired 的 Pod；
Dashboard 禁止使用该语义。把某个 profile 缩到目标数量示例：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${DESIRED:?set desired pod count for this profile}"
: "${MANUAL_SLOT_LIMIT:=100}"

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_PROD_MAX_MANUAL_SLOTS="$MANUAL_SLOT_LIMIT" \
python scripts/gpu_pool_controller.py runpod prod-worker scale \
  --profile "$PROFILE" \
  --desired "$DESIRED" \
  --execute
```

全量关闭时，对当前实际启用/存在的每个 profile 分别执行 `scale --desired 0 --execute`。
每步结束后复核 `reconcile.managed_count` 按预期下降且 `orphans=[]`。`disable --execute`
不会停止计费；只有 `down --execute` 或 `scale --desired 0 --execute` 删除 Pod 后才释放
RunPod 资源。

SCAIL-2 属于显存/内存压力更高的视频生视频 profile。`scail2` 代码、镜像、模型 manifest 和
Dashboard 管理入口都已具备，但它不代表线上必须常驻一个 `runpod_prod_scail2_manual_NN`。
如果目标 slot unhealthy 或触发 OOM，标准恢复是先 `disable`，确认无当前任务后 `down` 删除
Pod 释放资源；需要再次接单时重新 `add`、等待 disabled heartbeat、跑
`canary --profile scail2` 两个 5s MP4 验收，再显式 `enable`。没有 heartbeat 或已删除的
`manual_NN` 不应计入正式 SCAIL-2 容量。

LTX 正式 RunPod 是 `ltx_video` profile，面向高级图生视频三种执行类型：
`ltx_video,ltx_video_flf2v,ltx_video_v2v_audio`。手动池 agent 前缀为
`runpod_prod_ltx_video_manual_`，Pod 前缀为
`allbot-runpod-prod-ltx-video-manual-`；GPU 优先 `NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090`，
`containerDiskInGb` 至少 `180`。它默认使用
`RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_LTX_VIDEO` 指向三份 10Eros v1.2 workflow，
模型从 `allbot-model-cache/ltx_video/2026-06-10/manifest.json` 同步，不把模型 baked
进镜像，也不改 LAN AIO 或老 `LTX 2.3 *.json` workflow。`canary --profile ltx_video`
只提交一单 5s I2V MP4 验收，完成后保持 worker `disabled`；确认产物后再手动
`enable --profile ltx_video --slot NN --execute` 放开接单。

单 profile 创建模板：

```bash
: "${PROFILE:?set target RunPod profile}"

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
python scripts/gpu_pool_controller.py runpod prod-worker up \
  --profile "$PROFILE" \
  --execute
```

正式流程红线：

- `up --execute` 固定为预检 -> 写目标 agent control `disabled` -> 创建 Pod -> 等 readiness -> 等 Central heartbeat；ready 后默认不抢正式订单。`prod-worker` 的 worker heartbeat 等待默认 `3600s`，用于覆盖 `i2i_pro` / `scail2` 首次同步大模型的启动窗口。
- `enable --execute` 才允许目标 worker 接单。
- `down --execute` 必须确认无 `current_task_id`，忙碌 worker 不提供隐式 force；删除已有 Pod 不渲染 create pod request，也不应因缺少某个 profile 的 `RUNPOD_IMAGE_NAME_*` 创建配置而失败。
- `canary --execute` 不禁用现有正式 worker；完成后恢复目标 RunPod worker 为 `disabled`。
- `prod-worker canary --profile i2i_pro --execute` 会串行提交 `i2i_pro`、Web `txt2img`、`face_swap_v2` 三单，要求三单均由 `runpod_prod_i2i_pro_manual_NN` 接单并产出可下载图片，同时确认它不声明旧 `face_swap`。
- `prod-worker canary --profile scail2 --execute` 会串行提交 `scail2_action_transfer` 与 `scail2_video_replacement` 两个 5s 正式内部任务，要求两单均由 `runpod_prod_scail2_manual_NN` 接单、结果 MP4 写入 `user-data-prod` 且可下载；若需要强制命中 RunPod，应先让 SCAIL-2 pending 清空并临时 disable LAN SCAIL-2 agent。
- `prod-worker canary --profile ltx_video --execute` 会提交一单 `ltx_video` 5s I2V 内部任务，要求由 `runpod_prod_ltx_video_manual_NN` 接单、结果 MP4 写入 `user-data-prod` 且可下载；完成后目标 worker 保持 `disabled`。
- 生产真实创建、启用、删除或 canary 任务必须由用户明确确认。

## 9. R2 / RunPod 变量分层

| 变量族 | 语义 | cloud-test | cloud-prod |
| :--- | :--- | :--- | :--- |
| `MINIO_*` / `R2_*` | 用户数据桶，包含用户上传、生成结果、历史/Gallery 媒体 | `user-data-test`、`https://r2-test.aivison.it.com` | `user-data-prod`、`https://r2.aivison.it.com` |
| `RUNPOD_MODEL_BUCKET` | RunPod 模型缓存桶 | `allbot-model-cache` | `allbot-model-cache` |
| `RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO` / `RUNPOD_USE_TEMPLATE_IMAGE_TO_VIDEO` | split `image_to_video` 镜像与 template 开关 | `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd` / `false` | 同 cloud-test；cloud-prod 渲染会拒绝旧 tag |
| `RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2` / `RUNPOD_USE_TEMPLATE_WAN22_VIDEO_V2` | split `wan22_video_v2` 镜像与 template 开关 | `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd` / `false` | 同 cloud-test；cloud-prod 渲染会拒绝旧 tag |
| `RUNPOD_IMAGE_NAME_LTX_VIDEO` / `RUNPOD_USE_TEMPLATE_LTX_VIDEO` | `ltx_video` 高级图生视频镜像与 template 开关 | `ghcr.io/giraffu/allbot-comfy-runpod-ltx-video-v2:<tag>` / `false` | 创建/render/canary 前必须显式配置正式 tag；不得使用 LAN registry |
| `RUNPOD_MODEL_PREFIX` / `RUNPOD_MODEL_MANIFEST_KEY` | 默认模型 manifest，主要给 `img2img_lora` | `img2img_lora/2026-06-10` | `img2img_lora/2026-06-10` |
| `RUNPOD_MODEL_PREFIX_IMAGE_TO_VIDEO` / `RUNPOD_MODEL_MANIFEST_KEY_IMAGE_TO_VIDEO` | split `image_to_video` 模型 manifest | `image_to_video/2026-07-18-lora5/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_WAN22_VIDEO_V2` / `RUNPOD_MODEL_MANIFEST_KEY_WAN22_VIDEO_V2` | split `wan22_video_v2` 模型 manifest | `wan22_video_v2/2026-07-18-lora5/manifest.json` | 含视频 LoRA，模型就绪后再发布/切换 |
| `RUNPOD_MODEL_PREFIX_I2I_PRO` / `RUNPOD_MODEL_MANIFEST_KEY_I2I_PRO` | `i2i_pro` 三任务模型 manifest | `i2i_pro/2026-06-14-test/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_SCAIL2` / `RUNPOD_MODEL_MANIFEST_KEY_SCAIL2` | `scail2` 视频生视频模型 manifest | `scail2/2026-06-17-test/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_LTX_VIDEO` / `RUNPOD_MODEL_MANIFEST_KEY_LTX_VIDEO` | `ltx_video` 高级图生视频模型 manifest | `ltx_video/2026-06-10/manifest.json` | 同 cloud-test manifest；云端 R2 manifest 当前为 10Eros v1.2-only，不保留旧 v1 正式回退 |
| `RUNPOD_MODEL_PREFIX_WAN22_AIO_VIDEO` / `RUNPOD_MODEL_MANIFEST_KEY_WAN22_AIO_VIDEO` | 兼容/回滚全集 manifest | `wan22_aio_video/2026-07-18-lora5/manifest.json` | 不作为正式 split 主路径；旧 6 月 key 保留回滚 |

RunPod secret reference 固定口径：

```dotenv
# cloud-test 用户数据桶与 Central token
AGENT_SECRET_TOKEN={{ RUNPOD_SECRET_allbot_cloud_test_agent_secret_token }}
MINIO_ACCESS_KEY={{ RUNPOD_SECRET_allbot_cloud_test_r2_access_key }}
MINIO_SECRET_KEY={{ RUNPOD_SECRET_allbot_cloud_test_r2_secret_key }}

# cloud-prod 用户数据桶与 Central token
AGENT_SECRET_TOKEN={{ RUNPOD_SECRET_allbot_cloud_prod_agent_secret_token }}
MINIO_ACCESS_KEY={{ RUNPOD_SECRET_allbot_cloud_prod_r2_access_key }}
MINIO_SECRET_KEY={{ RUNPOD_SECRET_allbot_cloud_prod_r2_secret_key }}

# 模型缓存桶
RUNPOD_MODEL_ACCESS_KEY={{ RUNPOD_SECRET_allbot_model_cache_r2_access_key }}
RUNPOD_MODEL_SECRET_KEY={{ RUNPOD_SECRET_allbot_model_cache_r2_secret_key }}
```

`RUNPOD_API_KEY` 只用于 RunPod REST API。GitHub/GHCR token 只用于 Docker CLI login、GHCR push 或 package 管理。Cloudflare `cfat_...` API token 不用于 S3 客户端、RunPod Pod env 或模型同步，不应写入 `.env.cloud.*`、日志或知识库。

## 10. 镜像、模型与 workflow 口径

- `workers/comfy_agent/workflows` 是 workflow 运行时事实源；Central API 不维护 workflow 副本。
- Wan22 共享 RunPod 镜像构建入口仍在 `remote_workers/docker/runpod_profiles/wan22_aio_video/`，这是镜像目录名，不表示运行时继续使用 AIO profile。
- 当前 split video profile 复用 Wan22 GHCR image，但 profile-specific env、agent prefix、`SUPPORTED_TASK_TYPES`、runtime profile 和模型 manifest 必须分开渲染。`image_to_video` / `wan22_video_v2` 不再继承 legacy `RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO` 或 `RUNPOD_USE_TEMPLATE_WAN22_AIO_VIDEO`；默认直接渲染带 RIFE 的 `imageName`，cloud-prod `prod-worker` 会拒绝旧 tag 或 template。
- Wan22 新镜像只 baked workflow 所需 custom nodes、`ffmpeg/ffprobe`、`rife49.pth` 后处理小权重、`runpod_bootstrap_from_git.sh` 和运行依赖；Wan22 high/low UNet、VAE、text encoder 与旧视频 LoRA 不 baked 进镜像，启动时从 `allbot-model-cache` 同步。`rife49.pth` 由 `FL_RIFE` 运行期读取，不属于可在线下载的普通缓存；RunPod bootstrap/entrypoint 会在启动 ComfyUI 前运行 `remote_workers/scripts/ensure_wan22_rife_cache.py`，缺失时 exit 75。
- `face_swap_v2.json` 使用 `i2i_pro` Flux2/edit 节点与模型，绑定独立执行类型 `face_swap_v2`。i2i_pro LAN/RunPod 候选只通过 `TASK_TYPE_WORKFLOW_OVERRIDES` 将 V2 指向该 workflow；旧 `face_swap` 使用 `face_swap.json`，正式启用容量只保留 `worker_remote_02`。候选配置进入 Git 不代表线上 Worker 已切换，发布前后都要以 Central 实时心跳核验。
- `i2i_pro` RunPod 镜像构建入口是 `remote_workers/docker/runpod_profiles/i2i_pro/`，默认 base 为 `yanwk/comfyui-boot:cu128-slim`，与现有图生图和 Wan22 RunPod 镜像基线保持一致；ComfyUI pin 到 `16cd8d8a8f5f16ce7e5f929fdba9f783990254ea`。不得使用 `cu130` 基线，否则在当前 RunPod 4090 宿主机上可能因 PyTorch CUDA 版本高于宿主机驱动能力而失败；`20260614-i2ipro-6b167aa-cu128-min4` 已在 `NVIDIA GeForce RTX 4090` cloud-test Web canary 中完成模型同步、ComfyUI CUDA 初始化、worker heartbeat 和 `i2i_pro` 真实任务出图；当前 `.env.cloud.test` 候选镜像为 `20260614-i2ipro-b75c6a9-cu128-min5-ssh`，在 min4 的可用基线上补齐 `openssh` 与 direct TCP SSH smoke。当前 workflow 只要求 ComfyUI/core `nodes` 与 `comfy_extras` 中的 `UNETLoader`、`CLIPLoader`、`VAELoader`、`ReferenceLatent`、`EmptyFlux2LatentImage`、`Flux2Scheduler`、`SamplerCustomAdvanced`，不 baked 自定义节点或业务模型。GitHub Actions smoke 在 CPU runner 上用静态源码检查确认这些节点存在，避免导入 ComfyUI 时触发 CUDA 初始化；GPU import 与真实执行以 cloud-test canary 为准。镜像 smoke 还必须检查 `ffmpeg`、`curl`、`git`、`ssh-keygen` 与 `sshd`，确保 direct TCP SSH 诊断可用。
- RunPod `i2i_pro` 三任务能力依赖 `remote_workers/src/workflow_mapping_validation.py` 支持 `TASK_TYPE_WORKFLOW_OVERRIDES`，并且 `remote_workers/comfy_agent/workflows/` 内存在 `txt2img_from_i2i_pro.json` 与 `face_swap_v2.json`。不可变镜像必须把 override 固定为 `face_swap_v2 -> face_swap_v2.json`；禁止再用覆盖默认 `face_swap.json` 的方式让 i2i worker 接 V1。旧 Pod 若仍声明 `face_swap`，应保持 disabled 并通过新 digest 重建，在 Central 确认 V2-only 后再 enable；不得现场热修改源码、env 或 workflow 规避发布门禁。
- `scail2` RunPod 镜像构建入口是 `remote_workers/docker/runpod_profiles/scail2/`，GHCR ref 必须为 `ghcr.io/giraffu/allbot-comfy-runpod-scail2:<tag>`。镜像必须包含 ComfyUI SCAIL-2 core 节点、VideoHelperSuite、KJNodes、rgthree、Frame-Interpolation、Fill-Nodes、ffmpeg、bootstrap/sshd 诊断依赖和 `remote_workers/requirements.txt`，不得 baked 任何 `.safetensors` 模型权重。模型 manifest 固定为 `allbot-model-cache/scail2/2026-06-17-test/manifest.json`，LoRA 相对路径必须保持 `loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors`。正式 RunPod `scail2` profile 只接 `scail2_action_transfer,scail2_video_replacement`，结果写 `user-data-prod`；cloud-test RunPod profile 结果写 `user-data-test`。
- `ltx_video` RunPod 镜像构建入口是 `remote_workers/docker/runpod_profiles/ltx_video/`，GHCR ref 必须为 `ghcr.io/giraffu/allbot-comfy-runpod-ltx-video-v2:<tag>`，发布 workflow 为 `.github/workflows/runpod_ltx_video_profile_image.yml`。旧无 `-v2` 包未授权当前仓库 Actions 写入，只能作为历史回滚来源，不能承接新 SHA。Dockerfile 默认从可公网拉取的 Wan22 GHCR 节点源复制所需 custom nodes，不依赖 LAN registry；镜像只 baked LTX custom nodes、shim、bootstrap 与运行依赖，不 baked `.safetensors`。模型 manifest 固定为 `allbot-model-cache/ltx_video/2026-06-10/manifest.json`，云端 R2 当前只包含 10Eros v1.2 所需权重，正式 RunPod profile 默认通过 `RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_LTX_VIDEO` 使用三份 10Eros v1.2 workflow；老 `LTX 2.3 *.json` 和 LAN AIO 默认行为仍保留为独立入口，但不作为新 RunPod 回退路径。默认与 10Eros 的 FLF2V workflow 都必须保持时空 VAE `last_frame_fix=true`，并在 `workers/remote_workers` 同步发布，避免 LAN AIO 与 RunPod 的首尾帧末端解码行为漂移。
- `i2i_pro_baseline` 模型包从 `gpu-226` / `192.168.1.226:8188` 同步到 R2 `allbot-model-cache/i2i_pro/2026-06-14-test/manifest.json`，包含 6 个文件，总计 `38,769,838,190` bytes（约 `36.11 GiB`）。这 6 个文件同时覆盖 `i2i_pro.json`、`txt2img_from_i2i_pro.json` 与 `face_swap_v2.json`；本地主模型 registry 的 import spec 已按这两个 runtime overrides 生成 manifest，不再把 legacy Pornmaster/t2i 或旧 `face_swap.json` 专属模型纳入 `i2i_pro_baseline`。首次 cloud-test canary 使用 `RUNPOD_CONTAINER_DISK_GB=120`，GPU 只请求 `NVIDIA GeForce RTX 4090`，模型同步只写 ComfyUI `models/`，不得写 `input/output/temp/custom_nodes/workflows`。

`i2i_pro_baseline` 模型清单：

| Relative path | Size bytes |
| :--- | ---: |
| `text_encoders/qwen_3_8b_fp8mixed.safetensors` | `8,664,848,742` |
| `vae/flux2-vae.safetensors` | `336,213,556` |
| `unet/DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors` | `9,078,610,848` |
| `text_encoders/z_image/qwen_3_4b.safetensors` | `8,044,982,048` |
| `vae/z_image/ae.safetensors` | `335,304,388` |
| `unet/DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors` | `12,309,878,608` |

- `remote_workers/scripts/runpod_sync_models_from_r2.py` 支持 `.partial` 断点续传、有限重试和进度日志；已经创建的 Pod 不会热更新 `dockerStartCmd`，需删除重建。Dashboard/CLI 新增 RunPod 前可先用 `prod-worker render` 核对 `docker_start_cmd`，避免创建出 `dockerStartCmd=null` 的旧入口 Pod。
- 不要直接 `docker commit` 局域网成功的 ComfyUI 容器作为发布镜像；成功内容主要来自 volume/bind mount，commit 会漏 custom nodes/models/workflows，且可能混入运行残留。
- `img2img_lora` public GHCR 镜像只有同时具备可执行 `/opt/allbot/runpod_baked_runtime_entrypoint.sh`、非空 OCI/agent/workflow revision 标签并完成真实任务 canary 才可进入 Dashboard pin；2026-06-12 legacy tag 的历史 canary 不能证明它满足后续 baked runtime 启动契约。新 profile 也不能继承 img2img 的结论，必须单独准备模型 manifest、custom nodes、系统依赖和真实 Web canary。

## 11. Central / Worker 控制协议

新版 worker 在 `/api/agent/task/pop` 携带 `agent_id`。Central 通过 agent control 键控制单个 worker 是否接新单：

- `enabled`：可正常 pop。
- `draining`：不再 pop 新任务，等待当前任务自然结束。
- `disabled`：禁止接新任务。

接口：

- `POST /api/agent/task/control/{agent_id}`
- `GET /api/agent/task/control/{agent_id}`

这些接口使用现有 `AGENT_SECRET_TOKEN` 鉴权。旧 worker 不传 `agent_id` 时保留兼容逻辑。

切换任务能力、同步模型或做单点 canary 前，先把目标 worker 置为 `draining` 或 `disabled`；不要用强制重启代替 drain。

## 12. 运维红线

- Controller v1 不默认重启 worker、ComfyUI 或 GPU 节点。
- RunPod provider 不得触发本地 GPU SSH/Docker 操作。
- RunPod SSH 只用于云测试/失败现场短时诊断，需人工从 RunPod UI 提供当次 proxy SSH 信息；生产路径不依赖 SSH，也不得要求生产 Pod 暴露永久 SSH。
- 对 `host_service` runtime 只能生成观测或人工操作建议，不生成 Docker 操作。
- 模型同步只允许写目标共享 `models` 目录，不碰 `input/output/temp/custom_nodes/workflows`。
- 双卡节点只操作目标实例；不要整机 reboot、无 service 名 `docker compose down/up` 或批量删除容器。
- GPU 节点模型下载、Docker pull/build 或大视频输出前必须重新检查磁盘。
- RunPod model-transfer Pod 默认只允许 1 个；只有用户明确要求并发转存不同批次大对象时，才可在 cloud-test 临时提高到 2，完成后必须删除 Pod 并核验无 orphan、R2 active multipart 为 0。
- PornMaster Flux2 edit 云端模型准备必须优先走临时 RunPod transfer：`scripts/create_runpod_model_transfer_pod.py --pornmaster-flux2-edit` 默认 dry-run 且脱敏 source URL，execute 需要 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、`RUNPOD_MAX_PODS_TOTAL=1|2`、`RUNPOD_API_KEY`、用户生产确认和 `--confirm-model-transfer`；transfer 完成后 Pod 默认退出，也可用 `--delete-pod-id <pod_id> --execute --confirm-model-transfer` 清理。manifest 发布使用 `scripts/publish_pornmaster_flux2_model_manifest.py`，先 HEAD 三个对象并校验 size/metadata sha256，再写 `pornmaster_flux2_edit/2026-06-27/manifest.json`。
