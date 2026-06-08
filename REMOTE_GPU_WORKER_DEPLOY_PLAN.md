# 远程双 GPU Worker 部署计划

本文档用于在“两台远程 GPU 服务器同一局域网内的中控服务器”上新增 2 个正式 worker：

- `remote-prod-img2img-agent`：面向 `img2img`，如确认模型齐全可扩展到 `img2img_lora`。
- `remote-prod-face-swap-agent`：面向 `face_swap`。

当前正式生产控制面仍是云端 Central API，新增 worker 只通过 heartbeat / pop / status / complete 接入，不改云端 Web API、Bot、Payment、Dashboard、PostgreSQL 或 Valkey 结构。

## 0. 变量约定

部署前先替换以下占位符：

| 变量 | 示例 | 说明 |
| :--- | :--- | :--- |
| `LAN_CONTROL_HOST` | `root@192.168.x.10` | 两台 GPU 同局域网内、用于运行 worker 容器的中控服务器 SSH 地址 |
| `LAN_CONTROL_APP_DIR` | `/home/deploy/APP/All_bot` | 中控服务器上的项目目录 |
| `IMG2IMG_COMFY_HOST` | `192.168.x.21` | 支持 `img2img` 的 GPU 服务器 LAN IP |
| `IMG2IMG_COMFY_PORT` | `8188` | 支持 `img2img` 的 ComfyUI 端口 |
| `FACE_SWAP_COMFY_HOST` | `192.168.x.22` | 支持 `face_swap` 的 GPU 服务器 LAN IP |
| `FACE_SWAP_COMFY_PORT` | `8188` | 支持 `face_swap` 的 ComfyUI 端口 |
| `CLOUD_PROD_CENTRAL_TS_IP` | `100.107.220.127` | 当前云正式 Central API 的 Tailscale IP |

推荐 worker ID：

- `cloud_prod_remote_img2img_01`
- `cloud_prod_remote_face_swap_01`

不要复用现有 `cloud_prod_worker_01..07`，否则 Central worker heartbeat 会互相覆盖。

## 1. 架构目标

新增链路：

```text
云正式 Central API
  <- Tailscale/内网 HTTP ->
远程局域网中控服务器上的 worker 容器
  <- LAN HTTP / WebSocket ->
远程 GPU 服务器上的 ComfyUI
  <- R2 S3 API ->
Cloudflare R2 user-data-prod
```

worker 仍然是主动拉取任务：

```text
worker heartbeat -> Central /api/agent/task/heartbeat
worker pop       -> Central /api/agent/task/pop?types=...
worker status    -> Central /api/agent/task/status
worker complete  -> Central /api/agent/task/complete
```

## 2. 高压边界

- 本计划只新增两个 worker，不执行 `safe_deploy.sh`，不改云正式控制面 compose，不做 Alembic，不重建 Bot/Web/Payment/Dashboard。
- 新 worker 必须先用 `SUPPORTED_TASK_TYPES=__probe_only__` 启动验证，确认健康后再切真实任务类型。
- `SUPPORTED_TASK_TYPES` 只能配置远程 ComfyUI 已经具备完整 workflow、模型、LoRA、自定义节点的类型。
- `img2img_lora` 只有在该 GPU 服务器已安装对应 LoRA 文件和 workflow 依赖时才加入。
- worker 写路径必须继续使用 R2 `user-data-prod`，不要配置 legacy MinIO 写入。
- 真实密钥只放在远程服务器本地 `.env.remote-workers.prod`，不要提交、不要贴到聊天或文档。

## 3. 远程中控服务器前置准备

在 `LAN_CONTROL_HOST` 上安装基础依赖：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl rsync
```

安装 Docker 和 Compose 插件后确认：

```bash
docker --version
docker compose version
```

让该中控服务器加入当前生产 Tailscale 网络，并确认可访问云 Central：

```bash
tailscale status
curl -fsS "http://CLOUD_PROD_CENTRAL_TS_IP:8003/health"
```

确认它能访问两台 GPU ComfyUI：

```bash
curl -fsS "http://IMG2IMG_COMFY_HOST:IMG2IMG_COMFY_PORT/system_stats"
curl -fsS "http://IMG2IMG_COMFY_HOST:IMG2IMG_COMFY_PORT/queue"

curl -fsS "http://FACE_SWAP_COMFY_HOST:FACE_SWAP_COMFY_PORT/system_stats"
curl -fsS "http://FACE_SWAP_COMFY_HOST:FACE_SWAP_COMFY_PORT/queue"
```

如果 `/system_stats` 或 `/queue` 不通，先处理局域网、防火墙、ComfyUI 监听地址或端口问题，不要启动 worker。

## 4. 从文件拷贝开始

在当前主项目机器 `/home/hfy/APP/All_bot` 执行：

```bash
export LAN_CONTROL_HOST="root@192.168.x.10"
export LAN_CONTROL_APP_DIR="/home/deploy/APP/All_bot"

ssh "$LAN_CONTROL_HOST" "mkdir -p '$LAN_CONTROL_APP_DIR/workers' '$LAN_CONTROL_APP_DIR/src' '$LAN_CONTROL_APP_DIR/logs/workers-remote-prod'"

rsync -az workers/Dockerfile workers/worker_requirements.txt "$LAN_CONTROL_HOST:$LAN_CONTROL_APP_DIR/workers/"
rsync -az workers/comfy_agent/ "$LAN_CONTROL_HOST:$LAN_CONTROL_APP_DIR/workers/comfy_agent/"
rsync -az src/ "$LAN_CONTROL_HOST:$LAN_CONTROL_APP_DIR/src/"
```

说明：

- `workers/Dockerfile` 会把 `workers/comfy_agent` 复制进镜像。
- `workers/comfy_agent/workflows` 是 worker workflow 事实源，必须同步。
- `src` 会被挂载到 `/app/src`，用于 worker 运行时读取 domain config、常量和媒体路径逻辑。
- 不需要拷贝 `deploy/docker-compose-cloud-prod.yml`，远程中控服务器只运行 worker compose。

## 5. 创建远程最小密钥环境文件

在远程中控服务器创建：

```bash
cd /home/deploy/APP/All_bot
umask 077
nano .env.remote-workers.prod
```

写入以下键。真实值从当前正式 `.env.cloud.prod` 提取，但不要在终端历史或文档里打印密钥：

```dotenv
AGENT_SECRET_TOKEN=...

MINIO_ENDPOINT=...
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
MINIO_BUCKET=user-data-prod
MINIO_INPUT_BUCKET=user-data-prod
MINIO_RESULT_BUCKET=user-data-prod
MINIO_TEMPLATE_BUCKET=user-data-prod
MINIO_SECURE=true
```

设置权限：

```bash
chmod 600 /home/deploy/APP/All_bot/.env.remote-workers.prod
```

## 6. 创建两个远程 worker 的 compose 文件

在远程中控服务器创建：

```bash
cd /home/deploy/APP/All_bot/workers
nano docker-compose-remote-gpu-worker.prod.yml
```

先使用探针类型版本，避免一启动就抢生产任务：

```yaml
name: allbot-remote-prod-workers

x-worker-base: &worker-base
  build:
    context: ./
    dockerfile: Dockerfile
  restart: always
  env_file:
    - ../.env.remote-workers.prod
  network_mode: "host"
  volumes:
    - ../logs/workers-remote-prod:/app/logs
    - ./comfy_agent/workflows:/app/worker/workflows:ro
    - ../src:/app/src:ro

x-worker-common-env: &worker-common-env
  TZ: Asia/Shanghai
  MASTER_API_URL: http://CLOUD_PROD_CENTRAL_TS_IP:8003
  COMFY_INPUT_DIR: /tmp/input
  COMFY_OUTPUT_DIR: /tmp/output

services:
  remote-prod-img2img-agent:
    <<: *worker-base
    container_name: cloud-prod-remote-img2img-agent
    environment:
      <<: *worker-common-env
      AGENT_ID: cloud_prod_remote_img2img_01
      SUPPORTED_TASK_TYPES: __probe_only__
      COMFY_API_URL: http://IMG2IMG_COMFY_HOST:IMG2IMG_COMFY_PORT
      COMFY_WS_URL: ws://IMG2IMG_COMFY_HOST:IMG2IMG_COMFY_PORT/ws

  remote-prod-face-swap-agent:
    <<: *worker-base
    container_name: cloud-prod-remote-face-swap-agent
    environment:
      <<: *worker-common-env
      AGENT_ID: cloud_prod_remote_face_swap_01
      SUPPORTED_TASK_TYPES: __probe_only__
      COMFY_API_URL: http://FACE_SWAP_COMFY_HOST:FACE_SWAP_COMFY_PORT
      COMFY_WS_URL: ws://FACE_SWAP_COMFY_HOST:FACE_SWAP_COMFY_PORT/ws
```

保存前替换：

- `CLOUD_PROD_CENTRAL_TS_IP`
- `IMG2IMG_COMFY_HOST`
- `IMG2IMG_COMFY_PORT`
- `FACE_SWAP_COMFY_HOST`
- `FACE_SWAP_COMFY_PORT`

## 7. 启动探针版本

在远程中控服务器执行：

```bash
cd /home/deploy/APP/All_bot/workers

docker compose -f docker-compose-remote-gpu-worker.prod.yml config --services
docker compose -f docker-compose-remote-gpu-worker.prod.yml build remote-prod-img2img-agent remote-prod-face-swap-agent
docker compose -f docker-compose-remote-gpu-worker.prod.yml up -d --no-deps remote-prod-img2img-agent remote-prod-face-swap-agent
```

验证容器：

```bash
docker ps --format '{{.Names}}\t{{.Status}}' | grep 'cloud-prod-remote'
docker inspect cloud-prod-remote-img2img-agent --format 'restart={{.RestartCount}}'
docker inspect cloud-prod-remote-face-swap-agent --format 'restart={{.RestartCount}}'
```

看日志时只看状态，不贴密钥：

```bash
docker logs --tail 100 cloud-prod-remote-img2img-agent
docker logs --tail 100 cloud-prod-remote-face-swap-agent
```

期望看到：

- `MinIO client initialized`
- `Agent cloud_prod_remote_img2img_01 started heartbeat loop`
- `Agent cloud_prod_remote_face_swap_01 started heartbeat loop`
- `Agent ... started polling ... (types: __probe_only__)`

如果出现 `Central API returned HTTP 401`，优先检查 `AGENT_SECRET_TOKEN` 是否与云 Central 一致。

如果出现 ComfyUI probe 失败，优先检查 `COMFY_API_URL`、局域网、防火墙、ComfyUI 是否监听 `0.0.0.0` 或目标 LAN IP。

## 8. 验证 Central 可见

在能访问云 Central 的机器上执行：

```bash
curl -fsS "http://CLOUD_PROD_CENTRAL_TS_IP:8003/system/workers" | python -m json.tool
curl -fsS "http://CLOUD_PROD_CENTRAL_TS_IP:8003/system/status" | python -m json.tool
```

期望：

- 能看到 `cloud_prod_remote_img2img_01`
- 能看到 `cloud_prod_remote_face_swap_01`
- 两个 worker 状态为 `idle` 或 `running`
- `health_reason` 为空
- `consecutive_failures=0`
- `error_workers=0`
- `quarantined_workers=0`

探针阶段 `types` 是 `__probe_only__`，所以不会拉取真实生产任务。

## 9. 切换到真实任务类型

确认两台远程 ComfyUI 的模型、workflow、自定义节点齐全后，再编辑 compose：

```bash
cd /home/deploy/APP/All_bot/workers
nano docker-compose-remote-gpu-worker.prod.yml
```

推荐先切成保守版本：

```yaml
      SUPPORTED_TASK_TYPES: img2img
```

和：

```yaml
      SUPPORTED_TASK_TYPES: face_swap
```

如果 `img2img` 远程 GPU 已确认具备 LoRA 文件和相关 workflow 依赖，可以把第一台扩展为：

```yaml
      SUPPORTED_TASK_TYPES: img2img,img2img_lora
```

重新替换两个 worker：

```bash
cd /home/deploy/APP/All_bot/workers

docker compose -f docker-compose-remote-gpu-worker.prod.yml up -d --no-deps remote-prod-img2img-agent remote-prod-face-swap-agent
```

注意：如果只改 `SUPPORTED_TASK_TYPES`、`COMFY_API_URL`、`MASTER_API_URL` 这类 compose 环境变量，通常不需要 rebuild。若更新了 `workers/comfy_agent` 代码、`worker_requirements.txt` 或 `Dockerfile`，必须先 `build` 再 `up`。

## 10. 上线后观察

观察 Central：

```bash
curl -fsS "http://CLOUD_PROD_CENTRAL_TS_IP:8003/system/status" | python -m json.tool
curl -fsS "http://CLOUD_PROD_CENTRAL_TS_IP:8003/system/workers" | python -m json.tool
```

观察远程 worker：

```bash
docker logs --since 10m cloud-prod-remote-img2img-agent
docker logs --since 10m cloud-prod-remote-face-swap-agent
```

重点检查：

- `Processing task ... of type img2img`
- `Processing task ... of type face_swap`
- `Submitted task ... to ComfyUI`
- `Task ... completed successfully`
- `/api/agent/task/complete` 返回 200

不要只凭 worker 本地 `uploaded` 日志判定成功，成功收口硬依赖 Central `/api/agent/task/complete` 返回 200。

## 11. 回滚方式

如果新 worker 出现错误，先只停新增 worker，不动现有 7 个正式 worker：

```bash
cd /home/deploy/APP/All_bot/workers

docker compose -f docker-compose-remote-gpu-worker.prod.yml stop remote-prod-img2img-agent remote-prod-face-swap-agent
```

也可以把 `SUPPORTED_TASK_TYPES` 改回：

```yaml
      SUPPORTED_TASK_TYPES: __probe_only__
```

然后执行：

```bash
docker compose -f docker-compose-remote-gpu-worker.prod.yml up -d --no-deps remote-prod-img2img-agent remote-prod-face-swap-agent
```

这样 worker 仍保留 heartbeat 和健康观测，但不再领取真实任务。

## 12. 后续代码更新流程

从当前主项目机器重新同步：

```bash
export LAN_CONTROL_HOST="root@192.168.x.10"
export LAN_CONTROL_APP_DIR="/home/deploy/APP/All_bot"

rsync -az workers/Dockerfile workers/worker_requirements.txt "$LAN_CONTROL_HOST:$LAN_CONTROL_APP_DIR/workers/"
rsync -az workers/comfy_agent/ "$LAN_CONTROL_HOST:$LAN_CONTROL_APP_DIR/workers/comfy_agent/"
rsync -az src/ "$LAN_CONTROL_HOST:$LAN_CONTROL_APP_DIR/src/"
```

远程中控服务器上替换：

```bash
cd /home/deploy/APP/All_bot/workers

docker compose -f docker-compose-remote-gpu-worker.prod.yml build remote-prod-img2img-agent remote-prod-face-swap-agent
docker compose -f docker-compose-remote-gpu-worker.prod.yml up -d --no-deps remote-prod-img2img-agent remote-prod-face-swap-agent
```

如果远程服务器 Docker Compose 版本较老，遇到 recreate 兼容问题时，只清理这两个目标容器：

```bash
docker rm -f cloud-prod-remote-img2img-agent cloud-prod-remote-face-swap-agent 2>/dev/null || true
docker compose -f docker-compose-remote-gpu-worker.prod.yml up -d --no-deps remote-prod-img2img-agent remote-prod-face-swap-agent
```

不要使用 `--remove-orphans`，不要清理整组 worker。

## 13. 可选 workflow 本地校验

远程中控服务器上可以运行：

```bash
cd /home/deploy/APP/All_bot
python3 - <<'PY'
from src.workflow_mapping_validation import validate_workflow_directory
validate_workflow_directory("workers/comfy_agent/workflows")
print("workflow mappings ok")
PY
```

这个校验只能证明 worker 目录里的 workflow JSON 与 `mappings.json` 对得上，不能证明远程 ComfyUI 已安装对应模型、自定义节点和 LoRA。真实可运行性仍要看 ComfyUI 日志和首批任务结果。

## 14. 交付验收清单

- 远程中控服务器能访问云 Central `:8003/health`。
- 远程中控服务器能访问两台 GPU ComfyUI `/system_stats` 和 `/queue`。
- 两个容器 `Up`，`RestartCount=0`。
- Central `/system/workers` 能看到两个唯一 `agent_id`。
- 探针阶段不拉生产任务。
- 切真实类型后，`img2img` 和 `face_swap` 任务能成功 `/complete`。
- Central `/system/status` 中 `healthy_workers` 增加，`error_workers=0`，`quarantined_workers=0`。
- 最近 10 分钟 worker 日志无 `ERROR`、`Traceback`、`401`、ComfyUI probe 失败或 R2 上传失败。
