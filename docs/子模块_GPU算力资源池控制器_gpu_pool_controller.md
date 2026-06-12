# 子模块: GPU 算力资源池控制器 (GPU Pool Controller)

## 1. 目标与范围
本模块记录 AllBot 第一阶段 GPU 算力资源池方案：不用 K8s/K3s，先以 `SSH + Docker + 本地文件模型仓库 + registry:2 + dry-run Controller` 管理本地 4 台局域网 GPU 服务器，并以 RunPod Pods provider v0 承接云测试弹性 worker canary 和手动正式备用 worker。

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

RunPod Provider v0 当前有两条受控路径：云测试前置闭环用 1 个 RunPod Pod 验证 `img2img,img2img_lora`；正式环境仅支持手动脚本控制的备用 `img2img` worker，默认 `disabled`，不自动按队列扩容。RunPod 不属于局域网 SSH 资源池，不会出现在 `LanSshProvider.inventory_from_config()` 结果里，也不得触发本地 GPU 节点 SSH/Docker 操作。

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
python scripts/gpu_pool_controller.py runpod canary \
  --env-file .env.cloud.test \
  --quiet
```

`render-create` 不需要 `RUNPOD_API_KEY`，只渲染 `POST /pods` 请求；`create-pod` 默认仍是 dry-run。真实 `create/start/stop/delete` 必须同时显式满足：

```dotenv
RUNPOD_DRY_RUN=false
RUNPOD_AUTOSCALER_ENABLED=true
RUNPOD_MAX_PODS_TOTAL=1
RUNPOD_MAX_PODS_PER_TYPE=1
```

并建议设置 `RUNPOD_PROJECTED_COST_PER_HR_IMG2IMG_LORA` / `RUNPOD_PROJECTED_COST_PER_HR_WAN22_AIO_VIDEO` 与 `RUNPOD_MAX_HOURLY_COST_USD` 形成小时成本门禁。所有 CLI 输出会脱敏 API key、agent token、R2 secret 和 presigned URL signature。

`runpod canary` 是当前推荐的一键云测试 canary 编排命令。默认不创建 Pod，只执行 `validate-key`、`list-pods`、`reconcile-managed-pods` 和 `render-create` 预检，并校验 render 结果必须是 public GHCR baked image、`CENTRAL_API_URL=https://worker-central-test.aivison.it.com`、测试桶 `user-data-test`、模型桶 `allbot-model-cache`、`img2img_lora/2026-06-10/manifest.json`、custom node runtime install 关闭、secret 均为 RunPod secret reference。真实执行示例：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod canary \
  --env-file .env.cloud.test \
  --prompt "图片中出现一个黑人女性" \
  --download-results-dir /tmp/allbot_runpod_canary/results \
  --execute
```

真实 `runpod canary` 会按顺序完成：预检 RunPod managed Pod 为 0 -> Web/Central 测试入口健康检查 -> 创建 1 个 cloud-test Pod -> 等 Pod readiness 与 `runpod_test_img2img_lora_<pod_id>` heartbeat -> 临时禁用 `cloud_worker_test_01..07` -> 生成并上传一张无敏感 512x512 PNG，或用 `--input-object-key user-data-test/...` 复用测试桶已有图片 -> 串行提交 `img2img`、`img2img_lora + qwen/YARN_1.0.safetensors`、`img2img_lora + qwen/realistic_texture.safetensors` -> 等 Central `done` 与 Web result `success` -> 可选下载结果到 `--download-results-dir` -> 恢复测试 worker -> 删除 Pod -> 再跑 list/reconcile 确认无 orphan。命令只服务云测试；结果摘要只记录 object key、task id、Central/Web 终态、下载后的本地路径和去掉 query string 的 result path，不输出 JWT、agent token、presigned URL 或完整 create/env payload。

2026-06-12 已新增 `wan22_aio_video` RunPod cloud-test dry-run profile。该 profile 只服务 `render-create` 和 `runpod canary` 预检，不创建正式 Pod，不接 `prod-worker`。固定渲染口径为 `SUPPORTED_TASK_TYPES=image_to_video,wan22_video_v2`、`POOL_RUNTIME_PROFILE=wan22_aio_video`、`AGENT_ID_PREFIX=runpod_test_wan22_aio_video`、`gpuTypeIds=NVIDIA GeForce RTX 5090`、`MINIO_*_BUCKET=user-data-test`、`RUNPOD_MODEL_BUCKET=allbot-model-cache`、`RUNPOD_MODEL_PREFIX=wan22_aio_video/2026-06-12-test`、`RUNPOD_MODEL_MANIFEST_KEY=wan22_aio_video/2026-06-12-test/manifest.json`、`RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false` 和 `RUNPOD_COMFY_KJNODES_ENABLED=false`。dry-run 示例：

```bash
RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO=ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260612-wan22aio-test \
RUNPOD_MODEL_BUCKET=allbot-model-cache \
RUNPOD_MODEL_PREFIX=wan22_aio_video/2026-06-12-test \
RUNPOD_MODEL_MANIFEST_KEY=wan22_aio_video/2026-06-12-test/manifest.json \
python scripts/gpu_pool_controller.py runpod render-create \
  --task-type wan22_aio_video \
  --env cloud-test
```

`wan22_aio_video` canary dry-run 会校验 public GHCR Wan22 baked image 前缀、5090-only GPU、测试 Central、测试 bucket、模型 manifest 和 RunPod secret reference。未来真实 `--execute` 时，若未显式传 `--worker-id`，只会临时禁用云测试中支持 `image_to_video` 或 `wan22_video_v2` 的非 RunPod worker；任务 case 固定为 `image_to_video` preview/5s 单起始帧和 `wan22_video_v2` preview/5s 单起始帧，均要求 `extract_last_frame=true`。首尾帧、扩展生成、旧视频 LoRA、transfer/build Pod 和正式视频 worker 仍是后续阶段，不能从本 dry-run profile 推导为已验证。

2026-06-12 已补齐 `wan22_aio_video` 下一阶段工具入口，但默认仍只做 dry-run / 本地校验：

- `scripts/upload_model_bundle_to_r2.py` 支持重复传 `--bundle` 生成去重 union manifest，例如 `--bundle video_basic_baseline --bundle wan22_video_v2_baseline --prefix wan22_aio_video/2026-06-12-test --bucket allbot-model-cache`。脚本会对 R2 做 `HEAD`，输出已存在对象、待上传对象和本地 registry 缺失 blob；相同 `relative_path` 但 sha256/size 不一致会直接失败，避免 manifest 覆盖错模型。真实上传仍需 `--execute`，若缺本地 blob 只能先用 transfer Pod 补齐，不能上传包含缺失对象的 manifest。
- `scripts/create_runpod_model_transfer_pod.py` 支持 `--batch-file`，batch JSON 可为 `files` / `transfers` 列表，字段为 `source_url`、`key`、`relative_path`、`sha256`、`size_bytes`。默认 dry-run 会渲染单个 model-transfer Pod 请求并脱敏 URL；真实创建必须有 `RUNPOD_API_KEY` 且满足 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、`RUNPOD_MAX_PODS_TOTAL=1`，完成后必须删除 Pod 并核验无 orphan。
- `scripts/build_runpod_profile_image.sh --profile wan22_aio_video` 会构建 `remote_workers/docker/runpod_profiles/wan22_aio_video/Dockerfile`，镜像只 baked Wan22 workflow 所需 custom nodes、`ffmpeg/ffprobe` 和运行依赖，不 baked Wan22 high/low UNet、VAE、text encoder 或旧视频 LoRA；只有显式 `--push` 才推 GHCR，push 后需用空 `DOCKER_CONFIG` 匿名 pull/inspect 验证 package public。

GHCR / GitHub token 口径：

- `scripts/build_runpod_profile_image.sh` 不读取 GitHub token 变量；它只负责 `docker build`、smoke test 和可选 `docker push`。执行 `--push` 前必须先用 GitHub/GHCR token 对 Docker CLI 登录 `ghcr.io`，例如把密钥临时导出为 `GITHUB_TOKEN` 或 `GHCR_TOKEN` 后执行 `printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u <github_user> --password-stdin`。
- `.env.cloud.test` / `.env.cloud.prod` 中可保存 GitHub token 作为本机密钥来源，但真实 token 不得写入 docs、日志、compose config 或命令历史。当前环境文件里使用的 `all-github-token` 是人工记录用 key；因为包含中划线，不能被 `source .env.cloud.prod` 变成合法 shell 变量。需要推 GHCR 时，手工把它的值映射到当前 shell 的 `GHCR_TOKEN` / `GITHUB_TOKEN`，或后续另行补一个合法别名变量。
- GHCR token 只用于向 GitHub Container Registry push / package 管理，不是 `RUNPOD_API_KEY`、不是 R2 S3 key、也不是 RunPod Pod env。RunPod 拉镜像时应优先使用 public GHCR image；push 后必须用空 `DOCKER_CONFIG` 匿名 `docker manifest inspect` 或 `docker pull` 验证 package 已公开，否则 RunPod 付费 Pod 可能因无 registry 凭据拉取失败。
- `img2img_lora` 已验证 public image 为 `ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946`；Wan22 cloud-test 目标前缀为 `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:`，尚需 build、push、public 验证和真实 canary。

RunPod v0 创建 Pod 时默认不把本地 `.env.cloud.test` 中的 `AGENT_SECRET_TOKEN`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY` 明文写入 create JSON，而是引用 RunPod Secrets：

```dotenv
AGENT_SECRET_TOKEN={{ RUNPOD_SECRET_allbot_cloud_test_agent_secret_token }}
MINIO_ACCESS_KEY={{ RUNPOD_SECRET_allbot_cloud_test_r2_access_key }}
MINIO_SECRET_KEY={{ RUNPOD_SECRET_allbot_cloud_test_r2_secret_key }}
```

如未来 Secret 名称调整，可用 `RUNPOD_AGENT_SECRET_TOKEN_REF`、`RUNPOD_R2_ACCESS_KEY_REF`、`RUNPOD_R2_SECRET_KEY_REF` 覆盖引用字符串；`MINIO_ENDPOINT` 仍来自 `.env.cloud.test`，因为它不是密钥。2026-06-11 已同步 RunPod template `x750yt0uln` 的 `MINIO_ENDPOINT`，不再保留 UI 创建时的中文占位值。

RunPod / R2 环境变量字典：

| 变量族 | 含义 | cloud-test 固定口径 | cloud-prod 固定口径 |
| :--- | :--- | :--- | :--- |
| `MINIO_ENDPOINT` | 项目内 S3 兼容客户端 endpoint；名字保留 MinIO 兼容层，但当前云测试/云正式都指向 Cloudflare R2。 | `c7220eb751acc6f7ab8255b4a0394ef3.r2.cloudflarestorage.com` | `c7220eb751acc6f7ab8255b4a0394ef3.r2.cloudflarestorage.com` |
| `MINIO_BUCKET` / `MINIO_INPUT_BUCKET` / `MINIO_RESULT_BUCKET` / `MINIO_TEMPLATE_BUCKET` | 用户任务输入、结果、模板与 Web 媒体对象桶；worker 上传结果、Web 直传、历史/Gallery 读取都使用这一组。 | `user-data-test` | `user-data-prod` |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | 上面用户数据桶的 S3 key；本地/cloud-worker env 可持有真实值，RunPod Pod env 必须使用 Secret reference。 | RunPod 引用 `allbot_cloud_test_r2_access_key` / `allbot_cloud_test_r2_secret_key` | RunPod 引用 `allbot_cloud_prod_r2_access_key` / `allbot_cloud_prod_r2_secret_key` |
| `R2_BUCKET` | Web/API 层对当前用户数据桶的显式别名；不要用于模型缓存。 | `user-data-test` | `user-data-prod` |
| `R2_PUBLIC_DOMAIN` | 浏览器读取用户媒体的公网域名；为空会导致 owner 视频结果停在 `pending_result` 或历史预览 fallback 变慢。 | `https://r2-test.aivison.it.com` | `https://r2.aivison.it.com` |
| `RUNPOD_MODEL_BUCKET` | RunPod 模型缓存桶，只存模型 manifest 和模型文件，不存用户上传/生成媒体。 | `allbot-model-cache` | `allbot-model-cache` |
| `RUNPOD_MODEL_PREFIX` / `RUNPOD_MODEL_MANIFEST_KEY` | 目标 profile 的模型 bundle 前缀与 manifest key；不同 profile 必须独立。 | `img2img_lora/2026-06-10` 或 `wan22_aio_video/2026-06-12-test` | 当前手动正式 RunPod worker 固定 `img2img_lora/2026-06-10`；Wan22 未接正式 |
| `RUNPOD_MODEL_ENDPOINT` | 模型缓存桶的 S3 endpoint；本地模型上传/HEAD 脚本和 Pod 内模型同步都读取它，和用户数据桶 endpoint 可以相同但语义不同。 | `https://c7220eb751acc6f7ab8255b4a0394ef3.r2.cloudflarestorage.com` | 同 cloud-test，除非未来模型缓存迁到独立账号 |
| `RUNPOD_MODEL_ACCESS_KEY` / `RUNPOD_MODEL_SECRET_KEY` | `allbot-model-cache` 的真实 S3 key；本地 `upload_model_bundle_to_r2.py` dry-run/HEAD/upload 需要真实值，RunPod Pod 内由 Secret reference 展开后也叫这个名字。 | `.env.cloud.test` 可保存真实值，文件不得提交 | 正式 Pod 使用 RunPod secret 展开；不在文档记录真实值 |
| `RUNPOD_MODEL_ACCESS_KEY_REF` / `RUNPOD_MODEL_SECRET_KEY_REF` | 只是 create Pod env 中要渲染的 RunPod Secret reference 字符串，不是 S3 key 本身。 | `{{ RUNPOD_SECRET_allbot_model_cache_r2_access_key }}` / `{{ RUNPOD_SECRET_allbot_model_cache_r2_secret_key }}` | 同 cloud-test |
| `RUNPOD_AGENT_SECRET_TOKEN_REF` / `RUNPOD_R2_ACCESS_KEY_REF` / `RUNPOD_R2_SECRET_KEY_REF` | 云测试 Pod 的 Central 鉴权与用户数据桶 secret 引用。 | `allbot_cloud_test_agent_secret_token` / `allbot_cloud_test_r2_access_key` / `allbot_cloud_test_r2_secret_key` | 不用于正式 |
| `RUNPOD_PROD_AGENT_SECRET_TOKEN_REF` / `RUNPOD_PROD_R2_ACCESS_KEY_REF` / `RUNPOD_PROD_R2_SECRET_KEY_REF` | 正式 Pod 的 Central 鉴权与用户数据桶 secret 引用。 | 不用于云测试 canary | `allbot_cloud_prod_agent_secret_token` / `allbot_cloud_prod_r2_access_key` / `allbot_cloud_prod_r2_secret_key` |
| `RUNPOD_DRY_RUN` / `RUNPOD_AUTOSCALER_ENABLED` / `RUNPOD_MAX_PODS_TOTAL` / `RUNPOD_MAX_PODS_PER_TYPE` | mutation guard；任何真实 create/start/stop/delete 都必须同时显式打开，默认 dry-run。 | 默认 `RUNPOD_DRY_RUN=true`、`RUNPOD_AUTOSCALER_ENABLED=false`、Pod 上限 1 | 真实手动正式 worker 同样要求四重门禁和 `--execute` |
| `RUNPOD_PROD_MAX_MANUAL_SLOTS` | 正式手动 RunPod 图生图 slot 上限；默认 2，只限制 `runpod_prod_img2img_manual_01..NN` 这一组 prod img2img/img2img_lora worker。 | 通常不设置，默认 2 | 扩到 3 台及以上前必须显式设置为目标上限，并同步设置 `RUNPOD_MAX_PODS_TOTAL` / `RUNPOD_MAX_PODS_PER_TYPE` |
| `RUNPOD_IMAGE_NAME_*` / `RUNPOD_USE_TEMPLATE_*` / `RUNPOD_GPU_TYPE_IDS_*` | 每个 task profile 的镜像、template 开关和 GPU 限定；不要把 img2img 与 Wan22 混用。 | `img2img_lora` 使用已验证 public GHCR 4090/5090/L40S 口径；`wan22_aio_video` 固定 5090-only、GHCR Wan22 image 前缀 | 当前手动正式 worker 固定 public `img2img_lora` GHCR image 和 `NVIDIA GeForce RTX 4090` |
| `GITHUB_TOKEN` / `GHCR_TOKEN` / `all-github-token` | GitHub/GHCR package push 凭据；只给 Docker CLI login 或 GitHub API 使用，不进入 RunPod Pod env。 | 可存在 `.env.cloud.test`，但 `all-github-token` 需手工映射为合法 shell 变量后使用 | 可存在 `.env.cloud.prod`，不得随 compose config 输出或写入知识库真实值 |

`RUNPOD_API_KEY` 是 RunPod REST API token，只用于 `validate-key`、`list-pods` 和真实 Pod mutation，不是 Cloudflare/R2/GitHub 凭据。Cloudflare 控制台创建 R2 token 时显示的 `cfat_...` API token 不参与 S3 客户端、RunPod Pod env 或模型同步；GitHub/GHCR token 也只参与镜像 push/package 管理，不参与 R2 或 RunPod REST。知识库、日志和 `.env.cloud.*` 都不应保存 Cloudflare API token；所有 `*_ACCESS_KEY` / `*_SECRET_KEY` / GitHub token 的真实值只允许放在忽略文件、RunPod Secrets UI 或人工密钥管理系统中，文档只记录变量名、secret 名称和非敏感桶/前缀/域名。

RunPod REST `Pod` schema 没有 `uptimeSeconds` 字段，不要把字段缺失当作 `uptime=0` 作为 readiness 结论。排查 Pod 初始化时以 RunPod UI Telemetry、REST `publicIp`、REST `portMappings` 和 `runpodctl ssh info` 为主；官方文档说明 `portMappings` 为空表示 Pod 仍在初始化，绿色 Running 点只表示 Pod 处于期望运行状态，不代表容器和服务已经 ready。AllBot worker 的业务 ready 仍以云测试 Central `/system/workers` 出现 `runpod_test_img2img_lora_*` healthy heartbeat 为准。

RunPod SSH 远程调试口径：
- RunPod SSH 只用于云测试 canary 或失败现场的短时人工诊断，不是生产自动扩容、生产任务执行或 readiness 判定的依赖。
- 如需 Codex/运维侧进入 Pod 排查，需要由人工从 RunPod UI 的 Connect 面板提供当次有效的 SSH 信息，优先提供 RunPod proxy SSH 命令；direct TCP `root@<public_ip> -p <port>` 只作为备用，因为它依赖镜像内 `sshd` 实际存在并启动。
- RunPod Pod id、proxy 用户名、公网 IP、端口映射都可能随 Pod 重建变化，知识库不保存某次临时 SSH 地址或端口；只记录操作口径。
- SSH 排障只允许查看模型同步、ComfyUI 路径、Python/custom node 依赖、bootstrap 日志和 relay/agent 启动状态；不得把 RunPod API key、R2 key、agent token、presigned URL、完整 env 或完整 create payload 贴入文档/聊天。
- 若需要保留失败现场，可在云测试 canary 中临时设置 `RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE=true`，诊断完成后仍必须 stop/delete Pod 并跑 `list-pods` / `reconcile-managed-pods` 确认无 orphan。
- 生产路径不需要 SSH：生产自动扩容若未来开启，应依赖镜像、R2 manifest、`pod-readiness`、Central heartbeat、任务 canary、drain/delete 和 orphan watchdog；不得要求生产 Pod 暴露永久 SSH 入口。

RunPod 正式 worker Central 入口口径：
- 正式 RunPod Pod 不应访问 `api.aivison.it.com`，也不能访问仅 Tailscale 可达的 `100.107.220.127:8003`；应使用 worker 专用 Cloudflare Tunnel hostname。
- 当前已验证的正式 worker hostname 是 `https://worker-central.aivison.it.com`，回源正式 Central `http://100.107.220.127:8003`，`/health` 返回 Central OK。
- 2026-06-12 已在正式云机新增 `cloudflared-runpod-prod.service`，使用 root-only token file，回源同一个正式 Central，供 RunPod-Prod 独立 tunnel 使用。若要使用新的 RunPod 专用域名，需先在 Cloudflare Public Hostname 绑定该 tunnel 并验证 `/health`，再把它写入 RunPod profile 的 `CENTRAL_API_URL`。
- 正式 Pod 的 `AGENT_ID` 应使用稳定、可 drain 的前缀，例如 `runpod_prod_img2img_manual_01`；当前 v0 默认只开放 `manual_01` 和 `manual_02`，可通过 `RUNPOD_PROD_MAX_MANUAL_SLOTS=N` 显式扩展到 `manual_01..NN`。当前手动正式 worker 已开放 `SUPPORTED_TASK_TYPES=img2img,img2img_lora`，并默认将 `gpuTypeIds` 固定为 `NVIDIA GeForce RTX 4090`，避免 RunPod 按 availability 自动分配 L40S/5090。

手动正式 RunPod 图生图 worker CLI：

```bash
python scripts/gpu_pool_controller.py runpod prod-worker render
python scripts/gpu_pool_controller.py runpod prod-worker status
python scripts/gpu_pool_controller.py runpod prod-worker up
python scripts/gpu_pool_controller.py runpod prod-worker enable
python scripts/gpu_pool_controller.py runpod prod-worker disable
python scripts/gpu_pool_controller.py runpod prod-worker down
python scripts/gpu_pool_controller.py runpod prod-worker canary
python scripts/gpu_pool_controller.py runpod prod-worker scale --desired N
```

`prod-worker` 会默认先加载 `.env.cloud.test` 里的 RunPod API/profile 默认值，再加载 `.env.cloud.prod` 覆盖正式 Central/Web/R2/JWT 变量；已在 shell 中显式设置的 `RUNPOD_*` 门禁不会被 prod env 文件覆盖。默认管理 `runpod_prod_img2img_manual_01`，单 slot 命令可追加 `--slot NN`，CLI 会在创建 provider 前把目标 agent 切到 `runpod_prod_img2img_manual_NN` / `allbot-runpod-prod-img2img-manual-NN`。默认最大 slot 是 2，`--slot 03` 或 `scale --desired 3` 必须先显式设置 `RUNPOD_PROD_MAX_MANUAL_SLOTS=3` 或更高。Pod 内业务入口固定为 `CENTRAL_API_URL=https://worker-central.aivison.it.com`，CLI 控制与 canary 默认走云正式 Tailscale 内网 `http://100.107.220.127:8003` / `http://100.107.220.127:8000/api`，避免 Cloudflare WAF 影响内部 control/status。

正式 profile 固定值：
- `AGENT_ID=runpod_prod_img2img_manual_01`，`--slot NN` 或 `scale --desired N` 渲染为 `runpod_prod_img2img_manual_NN`
- `SUPPORTED_TASK_TYPES=img2img,img2img_lora`
- `RUNPOD_PROD_GPU_TYPE_IDS=NVIDIA GeForce RTX 4090`
- `POOL_PROVIDER=runpod`
- `POOL_NODE_ID=runpod-cloud-prod`
- `POOL_RUNTIME_PROFILE=img2img_lora`
- `MINIO_*_BUCKET=user-data-prod`
- `RUNPOD_MODEL_BUCKET=allbot-model-cache`
- `RUNPOD_MODEL_PREFIX=img2img_lora/2026-06-10`
- `RUNPOD_MODEL_MANIFEST_KEY=img2img_lora/2026-06-10/manifest.json`
- `RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false`
- `RUNPOD_COMFY_KJNODES_ENABLED=false`

正式 RunPod Secret reference 固定为：

```dotenv
AGENT_SECRET_TOKEN={{ RUNPOD_SECRET_allbot_cloud_prod_agent_secret_token }}
MINIO_ACCESS_KEY={{ RUNPOD_SECRET_allbot_cloud_prod_r2_access_key }}
MINIO_SECRET_KEY={{ RUNPOD_SECRET_allbot_cloud_prod_r2_secret_key }}
RUNPOD_MODEL_ACCESS_KEY={{ RUNPOD_SECRET_allbot_model_cache_r2_access_key }}
RUNPOD_MODEL_SECRET_KEY={{ RUNPOD_SECRET_allbot_model_cache_r2_secret_key }}
```

其中前三个 secret 用于正式 Central 鉴权和 `user-data-prod` 读写，必须在 RunPod Secrets UI 中单独创建；后两个 secret 用于 `allbot-model-cache` 模型 manifest 热同步，可复用云测试阶段已创建的 `allbot_model_cache_r2_access_key` / `allbot_model_cache_r2_secret_key`。如果 RunPod UI 里缺少 `allbot_cloud_prod_agent_secret_token`、`allbot_cloud_prod_r2_access_key`、`allbot_cloud_prod_r2_secret_key`，Pod 可能停在 system log 的 `start container ... begin` 后没有 bootstrap 输出，也不会产生 Central heartbeat；这种 Pod 不能靠本地代码热修，需要创建 secret 后删除并重建。

真实 `up/down/scale` 必须同时显式满足四重门禁并带 `--execute`：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod prod-worker up --execute
```

创建第二台时必须显式选择 slot 并把门禁开到 2：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=2 \
RUNPOD_MAX_PODS_PER_TYPE=2 \
python scripts/gpu_pool_controller.py runpod prod-worker up --slot 02 --execute
```

扩到 N 台推荐先跑 `scale` dry-run，再执行：

```bash
RUNPOD_PROD_MAX_MANUAL_SLOTS=4 \
RUNPOD_MAX_PODS_TOTAL=4 \
RUNPOD_MAX_PODS_PER_TYPE=4 \
python scripts/gpu_pool_controller.py runpod prod-worker scale --desired 4

RUNPOD_PROD_MAX_MANUAL_SLOTS=4 \
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=4 \
RUNPOD_MAX_PODS_PER_TYPE=4 \
python scripts/gpu_pool_controller.py runpod prod-worker scale --desired 4 --execute
```

`up --execute` 的顺序固定为：RunPod/Central/render 预检 -> 先把目标 agent 写入 Central control `disabled` -> 创建 1 个 cloud-prod Pod -> 等 Pod readiness -> 等正式 Central heartbeat 且 control 仍为 `disabled`。因此新 Pod ready 后默认不会抢正式订单。

`down --execute` 的顺序固定为：预检 -> 设置 `disabled` -> 轮询 worker heartbeat，确认无 `current_task_id` -> 删除唯一的 managed prod Pod -> `list-pods/reconcile-managed-pods`。若仍有 `current_task_id`，命令拒绝删除，不提供隐式 force。

`scale --desired N` 的目标是让 `runpod_prod_img2img_manual_01..N` 最终成为可接单 worker。未带 `--execute` 时只输出 plan 和 `would_execute`，不会写 Central control 或调用 RunPod mutation。真实扩容按 slot 顺序执行 `disabled -> create Pod -> wait pod readiness -> wait disabled heartbeat -> enabled`；真实缩容从最高 slot 往下执行 `disabled -> wait no current_task_id -> delete Pod -> post reconcile`，忙碌 worker 会失败退出，不强杀任务。`scale --desired 0` 允许安全缩到 0，但仍必须通过 drain。

`canary --execute` 不会禁用任何现有正式 worker。它只会临时 enable 目标 agent，用内部 `user_id=3` Web JWT 上传一张 512x512 PNG 到 `user-data-prod` 并提交 1 条正式 `img2img`，完成后下载结果到 `runpod_canary_results/prod/<date>/`，最后恢复 `disabled`。如果任务被现有 `cloud_prod_worker_*` 接走，命令会记录“正式任务完成但 RunPod pop 未命中”，不会把它算作 RunPod 闭环验证。

2026-06-11 已完成一次云测试真实 RunPod Pod 前置闭环验证：使用 `yanwk/comfyui-boot:cu128-slim` 作为基础镜像、`dockerStartCmd` 注入 `remote_workers/scripts/runpod_bootstrap_from_git.sh`，不使用 RunPod Network Volume，创建 1 个 RTX 4090 Pod 后自动完成 `ComfyUI /system_stats ready -> remote relay /health ready -> comfy_agent heartbeat`。Central `/system/workers` 可看到 `runpod_test_img2img_lora_*`，状态为 `idle`，能力为 `img2img,img2img_lora`；验证后已 stop/delete Pod，`runpod list-pods` 确认无 orphan managed Pod。

2026-06-12 已完成 Phase 1R 真实业务 canary：创建 1 个 RunPod RTX 4090 Pod `if082v0w8eowow`，R2 manifest 6 个模型文件同步到 ComfyUI `models`，Central 注册 `runpod_test_img2img_lora_if082v0w8eowow`，并完成 3 个真实 Web 任务闭环：
- `img2img` 无 LoRA：`744a6d0a-928f-438d-8644-4465fb64ecce`
- `img2img_lora` + `qwen/YARN_1.0.safetensors`：`ae9ae529-b6be-44cb-8feb-999ec19a8448`
- `img2img_lora` + `qwen/realistic_texture.safetensors`：`52395689-9485-4f14-a2f5-5775d538842c`

三任务均由 RunPod worker pop，Central 终态 `done`，Web result `success`，结果对象落到 `user-data-test` 的 `history/<task_id>/original.png`。完成后已恢复临时禁用的云测试 worker，删除 Pod，`runpod list-pods count=0`，`reconcile-managed-pods managed_count=0`。

2026-06-12 已完成 GHCR baked profile 镜像真实 canary：使用公网可匿名 pull 的 `ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946` 创建 1 个 RunPod RTX 4090 Pod `ln61p9vk99sau7`，镜像内 baked `ComfyUI-KJNodes`，启动期关闭 custom node runtime install，模型仍从 `allbot-model-cache/img2img_lora/2026-06-10/manifest.json` 热同步。Central 注册 `runpod_test_img2img_lora_ln61p9vk99sau7`，完成 3 个真实 Web 任务闭环：
- `img2img` 无 LoRA：`ad27719a-7efd-40e1-8f6a-cf1b2b435577`
- `img2img_lora` + `qwen/YARN_1.0.safetensors`：`ceb16956-069d-44b5-a7e0-b6e8b768e8f1`
- `img2img_lora` + `qwen/realistic_texture.safetensors`：`dd6d3391-0076-412e-a059-b2998a717335`

三任务均 Central `done`、Web result `success`，完成后已恢复 `cloud_worker_test_01..07` 为 `enabled`，删除 Pod，`runpod list-pods count=0`，`reconcile-managed-pods managed_count=0`。同 digest 的独立 package tag `ghcr.io/giraffu/allbot-comfy-runpod-img2img-lora:20260612-kjnodes7967a946` 已 push 但 GHCR package 仍为 private；后续付费 Pod 应继续使用上面的 public alias，或先在 GitHub Packages UI 将独立 package 调为 public。

本轮排查得到的 RunPod v0 启动约束：
- `runpod_bootstrap_from_git.sh` 必须把 `remote_workers/` 根目录加入 `PYTHONPATH`，否则 `comfy_agent/workflow_patcher.py` 无法 import `src.workflow_mapping_validation`。
- RunPod 不会自动展开 env 中的 `AGENT_ID=runpod_test_img2img_lora_${RUNPOD_POD_ID:-pending}`；bootstrap 需检测字面量占位并用 `RUNPOD_POD_ID`、`POD_ID` 或 `hostname` 生成唯一 agent id。
- `remote_relay` 当前以 `/health` 作为可靠 ready probe；本地代码已兼容 `/ready`，bootstrap 默认等 `/health`。
- RunPod REST / runpodctl 当前不提供稳定容器日志读取接口；UI Logs 或 SSH proxy 是主要现场取证入口。`ports=22/tcp` 的 direct TCP 可能映射出来但仍连接拒绝，不能把 direct SSH 当成自动化依赖。
- 诊断 canary 可开启 `RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE=true` 保留失败现场；真实生产扩容应在镜像稳定后关闭或缩短保留策略。
- R2 manifest 模型热同步入口为 `remote_workers/scripts/runpod_sync_models_from_r2.py`。2026-06-12 正式 RunPod 首次接入时，28GB 级 checkpoint 曾在下载末尾触发 `IncompleteRead`；同步脚本已改为保留同目录 `.partial` 文件、按已下载字节 `offset` 断点续传、最多重试 `RUNPOD_MODEL_DOWNLOAD_MAX_ATTEMPTS` 次，并在后续新 Pod 日志中按 `RUNPOD_MODEL_DOWNLOAD_PROGRESS_BYTES` / `RUNPOD_MODEL_DOWNLOAD_PROGRESS_SECONDS` 输出下载进度。已经创建的 Pod 不会热更新 `dockerStartCmd`，需要删除重建才会拿到新的进度日志。
- `yanwk/comfyui-boot:cu128-slim` 不是本地 GPU 正式 ComfyUI runtime 镜像。R2 manifest 只同步模型文件，不同步 `custom_nodes/`；首个真实任务曾因缺少 `GetImageSizeAndCount` 失败，该节点来自 `ComfyUI-KJNodes`。bootstrap 现在会在启动 ComfyUI 前默认安装 `ComfyUI-KJNodes`，并安装其 `requirements.txt`；如未来改用自建 profile 镜像，也必须确保镜像或 bootstrap 提供同等 custom node 集。
- 2026-06-12 对“生产已验证镜像能否直接用于 RunPod”做了只读验证：`gpu-002` 生产 `comfy0` 实际 image 为 `yanwk/comfyui-boot:cu128-slim`，custom nodes/models/workflows 均来自宿主机 volume 挂载；本地 registry tag `localhost:5000/allbot/comfyui-boot:cu128-slim-gpu002-5daf3995` 与该基础镜像是同一 image id，启动无挂载一次性容器检查 `ComfyUI-KJNodes` 不存在。因此当前 `img2img_lora` 没有可直接给 RunPod 使用的自包含生产镜像；`POOL_IMAGE_REF` 仍是目标声明，必须先构建/发布公网可拉取的 profile 镜像，或继续由 bootstrap 安装 custom nodes。
- `img2img_lora` profile 镜像构建入口已落地：`remote_workers/docker/runpod_profiles/img2img_lora/Dockerfile` 默认从 pinned Git ref 安装 `ComfyUI-KJNodes`；`Dockerfile.local-kjnodes` 支持从已验证的本地 KJNodes 目录构建，规避 GitHub 网络抖动；`scripts/build_runpod_profile_image.sh` 默认 build + smoke test，只有显式 `--push` 才推 registry。2026-06-12 本机已构建 `allbot/comfy-runpod-img2img-lora:local-20260612`，KJNodes commit 为 `7967a946c296a74901606e6a8d1195aa2b6f9215`，镜像未包含 Qwen checkpoint/LoRA 业务模型；公网 RunPod 已验证 image 为 `ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946`。
- 使用 baked profile 镜像时，RunPod env 应设置 `RUNPOD_USE_TEMPLATE_IMG2IMG_LORA=false`、`RUNPOD_IMAGE_NAME_IMG2IMG_LORA=<public image ref>`、`RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false`、`RUNPOD_COMFY_KJNODES_ENABLED=false`；`RUNPOD_MODEL_SYNC_ENABLED=true`、`RUNPOD_MODEL_BUCKET=allbot-model-cache` 和 `MINIO_*_BUCKET=user-data-test` 继续保持。当前 `.env.cloud.test` 已默认固定为 public GHCR baked image，不再需要在 create 命令里手写这些覆盖。

RunPod v0 当前已通过 `img2img/img2img_lora` 真实任务 canary。后续扩展到其它任务 profile 前，必须为每个 profile 单独准备模型 manifest、custom nodes、系统依赖和真实任务 canary；不得把本轮 Qwen `img2img_lora` 通过等同于其它 workflow 已 ready。

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
- RunPod 作为 `RunPodProvider v0` 接入同一 provider 边界，不把远程 Pod 加入本地 SSH 节点池；当前只允许云测试 `img2img_lora` canary 和手动正式 `img2img` 备用 worker，生产自动按队列扩容不开启。
