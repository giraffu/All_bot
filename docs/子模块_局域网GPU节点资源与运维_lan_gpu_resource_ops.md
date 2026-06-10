# 子模块: 局域网 GPU 节点资源与运维 (LAN GPU Resource Ops)

## 1. 目标与范围

本文档记录武汉局域网 GPU 节点的硬件资源、容器布局、ComfyUI 实例、模型挂载、生产 worker 对应关系和安全运维边界。它用于后续研发、模型更新、ComfyUI 排障、worker 灰度和容量规划。

本文档不是实时监控面板。GPU 利用率、显存占用、队列长度和磁盘剩余空间都是采集时快照；做停机、扩容、清理或升级前必须重新采集。

最近一次采集：2026-06-08，Asia/Shanghai。
最近一次 ComfyUI 素材清理：2026-06-08，Asia/Shanghai。

## 2. 总体拓扑

正式生产控制面在云端，生产 worker/relay 在本地主服务器，真实 GPU 推理由 4 台局域网 GPU 节点上的 ComfyUI 提供：

| 层级 | 承担功能 | 入口 |
| :--- | :--- | :--- |
| 云控制面 | `cloud-central-api-prod`、Web API、Payment、Dashboard、Bot、imgproxy | `ssh allbot-do-sgp1-control` |
| 本地主服务器 | `cloud-prod-worker-relay`、`cloud-prod-comfy-agent-1..7`、结果 spool、legacy MinIO/Postgres/Redis 保留 | 本机 `/home/hfy/APP/All_bot` |
| GPU 节点 | ComfyUI 推理、模型文件、输入输出缓存、DCGM/node exporter | `allbot-gpu-226/177/252/002` |

生产 worker 容器不在 GPU 节点上；它们在本地主服务器运行，通过局域网 HTTP/WS 调用各 GPU 节点的 ComfyUI。

## 3. 服务器总览

| 服务器 | SSH Host | CPU | 内存 | GPU | 磁盘快照 | 主要功能 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 主服务器 `hfy-FAEX9` | 本机 | Ryzen AI MAX+ 395，16C/32T | 62GiB | 无独立推理 GPU | `/` 3.6T，已用 1.3T，可用 2.2T | worker/relay、spool、legacy 数据、开发运维 |
| 云控制面 `allbot-do-sgp1-control-01` | `allbot-do-sgp1-control` | DO-Regular，4 vCPU | 7.8GiB | 无 | `/` 154G，已用 58G，可用 97G | 正式控制面 |
| `192.168.1.226` | `allbot-gpu-226` | Ryzen 9 9950X，16C/32T | 60GiB | 1 x RTX 5090 32G | `/` 1.8T，已用 573G，可用 1.2T | 单 ComfyUI，worker 01 |
| `192.168.1.177` | `allbot-gpu-177` | Ryzen 7 9700X，8C/16T | 60GiB | 2 x RTX 5090 32G | `/` 915G，已用 508G，可用 361G；外置盘 `/media/ubantui/T71` 可用 228G | 双 ComfyUI，worker 02/03 |
| `192.168.1.252` | `allbot-gpu-252` | Ryzen 7 9700X，8C/16T | 60GiB | 2 x RTX 4090 48G | `/` 937G，已用 178G，可用 712G；外置盘 `/mnt/t7` 可用 269G | 双 ComfyUI，worker 04/05 |
| `192.168.1.2` | `allbot-gpu-002` | Ryzen 7 9700X，8C/16T | 60GiB | 2 x RTX 4090 48G | `/` 936G，已用 171G，可用 726G | 双 ComfyUI，worker 06/07 |

容量警戒：
- 2026-06-08 已清理各 GPU 节点 ComfyUI 旧素材，`192.168.1.177` 从高风险的约 `14G` 可用恢复到约 `361G` 可用。
- ComfyUI `input/output/temp` 仍会随视频任务快速增长；每次模型下载、Docker pull/build 或大视频压测前都要重新检查 `df -h`。
- `192.168.1.226` 与 `192.168.1.252` 曾观察到 swap 使用较高，排查慢响应时要同时看内存压力、ComfyUI 任务和 Docker stats。
- 2026-06-08 17:10 巡检时，Central pending 约 `23-24`、running `12`，最老 pending 约 `2873s`；`healthy_workers=7`、`error_workers=0`、`quarantined_workers=0`。这类状态说明队列在消化但用户会感到等待，不等于 worker 离线。
- GPU 利用率要和显存、ComfyUI `/queue`、worker heartbeat 一起看。显存高但 GPU 利用率低可能是模型常驻、加载、等待、后处理或 IO；单看 `memory.used` 不能判断“算力拉满”。

## 4. 本地主服务器 Worker 容器

本地主服务器运行云正式 worker 和 relay：

| 容器 | 角色 | 目标 ComfyUI | 支持任务 |
| :--- | :--- | :--- | :--- |
| `cloud-prod-worker-relay` | 本地 worker relay 与上传 sidecar，端口 `127.0.0.1:8013` | 云 Central `100.107.220.127:8003` | agent API 转发、R2 上传 sidecar |
| `cloud-prod-comfy-agent-1` | Worker 01 | `192.168.1.226:8188` | `face_swap,i2i_pro,i2i_draw,face_video,video_edit,image_to_video,t2i-pornmaster-turbo` |
| `cloud-prod-comfy-agent-2` | Worker 02 | `192.168.1.177:8188` | `video_insert,video_edit,image_to_video` |
| `cloud-prod-comfy-agent-3` | Worker 03 | `192.168.1.177:8189` | `ltx_video,image_to_video` |
| `cloud-prod-comfy-agent-4` | Worker 04 | `192.168.1.252:8188` | `img2img,img2img_lora` |
| `cloud-prod-comfy-agent-5` | Worker 05 | `192.168.1.252:8189` | `wan22_video_v2,video_edit,image_to_video` |
| `cloud-prod-comfy-agent-6` | Worker 06 | `192.168.1.2:8188` | `img2img,img2img_lora` |
| `cloud-prod-comfy-agent-7` | Worker 07 | `192.168.1.2:8189` | `video_insert,video_edit,image_to_video` |

所有 worker 挂载：
- `/home/hfy/APP/All_bot/workers/comfy_agent/workflows -> /app/worker/workflows`
- `/home/hfy/APP/All_bot/src -> /app/src`
- `/home/hfy/APP/All_bot/logs/workers-cloud-prod -> /app/logs`
- `/home/hfy/APP/All_bot/logs/worker-spool-cloud-prod -> /app/spool`

`PIPELINE_ENABLED=true`，`PIPELINE_MAX_RUNNING_TASKS=2`。worker 重建只影响对应 agent；不会自动重启目标 GPU 节点的 ComfyUI。

## 5. GPU 节点明细

### 5.1 `allbot-gpu-226` / `192.168.1.226`

硬件与系统：
- Ubuntu 24.04.4 LTS，kernel `6.17.0-20-generic`
- Ryzen 9 9950X，16C/32T
- 内存 60GiB
- 1 x RTX 5090 32G，driver `590.48.01`
- Docker 29.1.3，Compose 2.37.1

容器：
- `portainer_agent`
- `dcgm_exporter`
- `monitor_node_exporter`

ComfyUI：
- 宿主机进程，不是 Docker Comfy 容器
- 端口：`8188`
- 进程 cwd：`/home/ubantu/comfyui`
- 启动命令：`/home/ubantu/miniforge3/envs/comfyui/bin/python main.py --listen 0.0.0.0 --enable-manager`
- 模型目录：`/home/ubantu/comfyui/models`，约 `325G`
- 对应 worker：`cloud-prod-comfy-agent-1`

运维边界：
- 不要对 `comfy0/comfy1` 执行 Docker 操作；本机没有这类 Comfy 容器。
- 重启 ComfyUI 需要先确认它是由 systemd、tmux、screen、桌面会话还是手工进程管理，再按实际启动方式处理。
- 重启该 ComfyUI 只影响 `cloud_prod_worker_01`。

### 5.2 `allbot-gpu-177` / `192.168.1.177`

硬件与系统：
- Ubuntu 24.04.4 LTS，kernel `6.17.0-29-generic`
- Ryzen 7 9700X，8C/16T
- 内存 60GiB
- 2 x RTX 5090 32G，driver `580.159.03`
- Docker 29.1.3，Compose 2.37.1
- 根分区 `/` 可用约 `361G`，外置盘 `/media/ubantui/T71` 可用约 `228G`

容器：
- `comfy0`：`yanwk/comfyui-boot:cu130-slim`
- `comfy1`：`yanwk/comfyui-boot:cu130-slim`
- `portainer_agent`
- `dcgm_exporter`
- `monitor_node_exporter`

ComfyUI 实例：

| 容器 | GPU | Host 端口 | 容器端口 | 模型目录 | 独立目录 | 对应 worker |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `comfy0` | GPU `0` | `8188` | `8188` | `/data/comfy/models` | `/data/comfy/inst0/{input,output,temp,custom_nodes,workflows}` | `cloud-prod-comfy-agent-2` |
| `comfy1` | GPU `1` | `8189` | `8188` | `/data/comfy/models` | `/data/comfy/inst1/{input,output,temp,custom_nodes,workflows}` | `cloud-prod-comfy-agent-3` |

共享模型目录：`/data/comfy/models`，约 `444G`。

关键节点差异：
- `8188`：`FL_RIFE` 与 `RIFE VFI` 均存在。
- `8189`：`FL_RIFE` 与 `RIFE VFI` 均存在。2026-06-08 已在 `comfy1` 容器补齐 `socksio` 并重启，使 `comfyui_fill-nodes` 正常加载；Worker 03 不再需要 worker 侧 RIFE 节点类环境变量。

运维边界：
- 更新或重启 `comfy0` 只影响 `cloud_prod_worker_02`，不要动 `comfy1`。
- 更新或重启 `comfy1` 只影响 `cloud_prod_worker_03`，不要动 `comfy0`。
- 修改 `/data/comfy/models` 会影响两个 ComfyUI。
- 修改 `/data/comfy/inst0/custom_nodes` 或 `workflows` 只影响 `comfy0`。
- 修改 `/data/comfy/inst1/custom_nodes` 或 `workflows` 只影响 `comfy1`。
- ComfyUI `input/output/temp` 已做一次旧素材清理；模型下载、Docker pull/build、临时输出前仍要先检查磁盘。

### 5.3 `allbot-gpu-252` / `192.168.1.252`

硬件与系统：
- Ubuntu 24.04.3 LTS，kernel `6.17.0-29-generic`
- Ryzen 7 9700X，8C/16T
- 内存 60GiB
- 2 x RTX 4090 48G，driver `580.159.03`
- Docker 29.4.0，Compose v5.1.2
- 根分区 `/` 可用约 `712G`，外置盘 `/mnt/t7` 可用约 `269G`

容器：
- `comfy0`：`yanwk/comfyui-boot:cu128-slim`
- `comfy1`：`yanwk/comfyui-boot:cu128-slim`
- `dcgm_exporter`
- `node_exporter`

ComfyUI 实例：

| 容器 | GPU | Host 端口 | 容器端口 | 模型目录 | 独立目录 | 对应 worker |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `comfy0` | GPU `0` | `8188` | `8188` | `/home/user/APP/data/models` | `/home/user/APP/data/inst0/{input,output,temp,custom_nodes,workflows}` | `cloud-prod-comfy-agent-4` |
| `comfy1` | GPU `1` | `8189` | `8189` | `/home/user/APP/data/models` | `/home/user/APP/data/inst1/{input,output,temp,custom_nodes,workflows}` | `cloud-prod-comfy-agent-5` |

共享模型目录：`/home/user/APP/data/models`，约 `121G`。

运行备注：
- `comfy0` CLI 包含 `--fp8_e4m3fn-text-enc`。
- `comfy0`/`comfy1` 的模型目录共享，实例目录分离。

运维边界：
- 只处理 `img2img/img2img_lora` 相关问题时，优先定位 `comfy0` 与 worker 04。
- 只处理 `wan22_video_v2/video_edit/image_to_video` 相关问题时，优先定位 `comfy1` 与 worker 05。
- 修改共享模型目录会同时影响两个 worker；修改 `inst0/inst1` 下 custom_nodes/workflows/input/output/temp 只影响对应容器。

### 5.4 `allbot-gpu-002` / `192.168.1.2`

硬件与系统：
- Ubuntu 24.04.4 LTS，kernel `6.8.0-124-generic`
- Ryzen 7 9700X，8C/16T
- 内存 60GiB
- 2 x RTX 4090 48G，driver `580.159.03`
- Docker 29.1.3，Compose 2.40.3
- 根分区 `/` 可用约 `726G`

容器：
- `comfy0`：`yanwk/comfyui-boot:cu128-slim`
- `comfy1`：`yanwk/comfyui-boot:cu128-slim`
- `dcgm_exporter`
- `node_exporter`

ComfyUI 实例：

| 容器 | GPU | Host 端口 | 容器端口 | 模型目录 | 独立目录 | 对应 worker |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `comfy0` | GPU `0` | `8188` | `8188` | `/data/comfy/models` | `/data/comfy/inst0/{input,output,temp,custom_nodes,workflows}` | `cloud-prod-comfy-agent-6` |
| `comfy1` | GPU `1` | `8189` | `8188` | `/data/comfy/models` | `/data/comfy/inst1/{input,output,temp,custom_nodes,workflows}` | `cloud-prod-comfy-agent-7` |

共享模型目录：`/data/comfy/models`，约 `85G`。

运维边界：
- `comfy0` 对应 worker 06，主要处理 `img2img/img2img_lora`。
- `comfy1` 对应 worker 07，主要处理 `video_insert/video_edit/image_to_video`。
- 可只重启目标 Comfy 容器；不要因为一个容器异常而重启整台 GPU 节点。

## 6. 双卡节点安全操作红线

双卡 GPU 服务器的两个 ComfyUI 服务是独立容器，但不是完全隔离：

独立部分：
- Docker 容器：`comfy0` / `comfy1`
- GPU：`DeviceIDs ["0"]` / `DeviceIDs ["1"]`
- Host 端口：通常 `8188` / `8189`
- 输入目录：`inst0/input` / `inst1/input`
- 输出目录：`inst0/output` / `inst1/output`
- 临时目录：`inst0/temp` / `inst1/temp`
- 自定义节点目录：`inst0/custom_nodes` / `inst1/custom_nodes`
- workflow 目录：`inst0/workflows` / `inst1/workflows`

共享部分：
- 模型目录：`models`
- 模型 cache：`cache`
- Docker daemon
- 宿主机磁盘、CPU、内存、网络
- DCGM/node exporter 监控容器

因此：
- 处理单个 worker/Comfy 问题时，只重启对应 `cloud-prod-comfy-agent-N` 或对应 GPU 节点上的 `comfy0/comfy1`。
- 不要执行整机 reboot、`docker compose down`、无 service 名 `docker compose up -d` 或批量 `docker rm`。
- 修改共享模型目录前，要确认另一张卡没有正在使用同一模型文件。
- 删除 output/temp 可以按 `inst0` 或 `inst1` 定向清理；不要清理整个 `models` 或整个 `/data/comfy`。
- 更新 custom nodes 时优先只更新目标实例的 `custom_nodes`，验证通过后再同步另一实例。

## 7. ComfyUI 素材清理策略

2026-06-08 检查结果：4 台 GPU 节点只有系统默认 `systemd-tmpfiles-clean`、`logrotate`、apt/sysstat 等基础清理机制，没有发现针对 ComfyUI `input/output/temp` 的 cron、systemd timer 或项目级清理服务。因此此前旧图片、视频和临时文件会长期堆积。

当前推荐保留策略：

| 目录 | 推荐清理窗口 | 原因 |
| :--- | :--- | :--- |
| `output` | 删除 60 分钟以前文件 | Worker finalizer 正常会在任务完成后立即取回结果并上传 R2，旧输出主要是本地残留 |
| `temp` | 删除 60 分钟以前文件 | ComfyUI 中间产物，可按实例定向清理 |
| `input` | 删除 24 小时以前文件 | 已 pop/已 queue 的 ComfyUI prompt 仍可能引用输入文件，不能简单只保留 1 小时 |

不要清理：
- `models`
- `custom_nodes`
- `workflows`
- HuggingFace/Torch cache，除非明确是在做模型/缓存专项整理
- 当前 `/queue` 中 prompt 引用的输入文件

项目提供干跑优先脚本：

```bash
cd /home/hfy/APP/All_bot
scripts/cleanup_lan_comfy_artifacts.sh
scripts/cleanup_lan_comfy_artifacts.sh --host allbot-gpu-177
scripts/cleanup_lan_comfy_artifacts.sh --execute
```

脚本默认：
- 不带 `--execute` 只扫描不删除。
- `output/temp` 删除 60 分钟以前文件。
- `input` 删除 24 小时以前文件。
- `input` 保留窗口短于 360 分钟时必须显式加 `--force-short-input`，生产环境一般不要这么做。
- `allbot-gpu-226` 走宿主机路径 `/home/ubantu/comfyui/{input,output,temp}`。
- `allbot-gpu-177/252/002` 通过对应 `comfy0/comfy1` 容器内部 `/root/ComfyUI/{input,output,temp}` 清理，避免宿主权限导致 root-owned 文件残留。

手工清理前后必须验证：

```bash
for base in \
  http://192.168.1.226:8188 \
  http://192.168.1.177:8188 \
  http://192.168.1.177:8189 \
  http://192.168.1.252:8188 \
  http://192.168.1.252:8189 \
  http://192.168.1.2:8188 \
  http://192.168.1.2:8189
do
  curl -fsS "$base/system_stats" >/dev/null
  curl -fsS "$base/queue" >/dev/null
done
curl -fsS http://100.107.220.127:8003/system/status
```

2026-06-08 人工清理结果：

| 节点 | 清理后磁盘 | 主要释放来源 |
| :--- | :--- | :--- |
| `allbot-gpu-226` | `/` 1.8T，已用 573G，可用 1.2T | host ComfyUI `output` 旧文件约 387G，`input` 24h 前文件约 135G |
| `allbot-gpu-177` | `/` 915G，已用 508G，可用 361G | `inst0/inst1 output` 旧文件约 266G，`input` 24h 前文件约 80G |
| `allbot-gpu-252` | `/` 937G，已用 178G，可用 712G | `inst0 temp/input`、`inst1 output/input` 等旧文件约 392G |
| `allbot-gpu-002` | `/` 936G，已用 171G，可用 726G | `inst0 temp/input`、`inst1 output/input` 等旧文件约 276G |

长期建议：先用脚本 dry-run 纳入例行巡检，确认 1-2 周无误删后，再考虑为各 GPU 节点安装 systemd timer。启用 timer 前要保留 `input` 的长窗口，或者增加 `/queue` 文件引用排除逻辑。

## 8. 标准排障路径

从 Central 到 GPU 的定位顺序：

1. Central：`curl -fsS http://100.107.220.127:8003/system/workers`
2. Central Redis：统计 `comfy:queue:pending`、`comfy:queue:running`、pending 最老等待时间、`comfy:task_heartbeat:*` TTL
3. 本地主服务器 worker：`docker logs --since 5m cloud-prod-comfy-agent-N`
4. 目标 ComfyUI：`curl -fsS http://<gpu-ip>:<port>/system_stats`
5. 目标 ComfyUI 队列：`curl -fsS http://<gpu-ip>:<port>/queue`
6. 目标 GPU 节点：`ssh allbot-gpu-xxx 'nvidia-smi; docker ps'`
7. 目标 Comfy 容器：`docker logs --since 5m comfy0` 或 `comfy1`

不要跳过 worker 到 Comfy 的对应关系。比如 `cloud-prod-comfy-agent-5` 只对应 `192.168.1.252:8189` / `comfy1`，不应该重启 `192.168.1.252` 上的 `comfy0`。

## 9. Worker 自动恢复边界

本地主服务器提供宿主机 watchdog：

```bash
scripts/watch_cloud_worker_recovery.sh --env cloud-test --mode dry-run
scripts/watch_cloud_worker_recovery.sh --env cloud-prod --mode dry-run
```

安全边界：
- 云测试可在故障注入时显式使用 `--mode execute` 精确恢复 `cloud-worker-relay-test` 或单个 `cloud-comfy-agent-test-*`。
- 云正式默认只运行 dry-run；真实 execute 必须另行确认。
- watchdog 只恢复本地主服务器上的 relay/agent 容器，不重启 GPU 节点、不重启 `comfy0/comfy1` 或 `allbot-gpu-226` 宿主机 ComfyUI、不执行全量 compose。
- 若 Central 与多个 ComfyUI 同时不可达，判定为网络中断，等待网络恢复，不做容器重启动作。
- relay `/ready` 返回 404 代表当前运行 relay 仍是旧版本，watchdog 只记录 `relay_ready_endpoint_missing`，不通过重启替代部署升级。

## 10. 单容器更新流程

更新某个 GPU 节点上的单个 Comfy 容器时：

```bash
ssh allbot-gpu-177
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -fsS http://127.0.0.1:8189/queue
docker logs --since 5m comfy1
docker restart comfy1
curl -fsS http://127.0.0.1:8189/system_stats
```

注意：
- 上例只适合 `192.168.1.177:8189` / `comfy1`。
- 如果该 ComfyUI 正在执行任务，重启会中断当前任务。
- 如果 Central 中对应 worker 仍健康，优先等任务自然完成；紧急恢复时再中断。
- 对 `comfy0`/`comfy1` 执行 Docker 操作前，先确认当前所在 SSH Host，避免在错误机器上操作同名容器。

本地主服务器 worker 只更新某个 agent 时：

```bash
cd /home/hfy/APP/All_bot/workers
set -a; source ../.env.cloud.prod; set +a
docker-compose -f docker-compose-cloud-prod-worker.yml build cloud-prod-comfy-agent-5
docker rm -f cloud-prod-comfy-agent-5 2>/dev/null || true
docker-compose -f docker-compose-cloud-prod-worker.yml up -d --no-deps cloud-prod-comfy-agent-5
```

这只替换 worker 容器，不会重启 GPU 节点上的 `comfy1`。

## 11. 采集命令

硬件与容器：

```bash
for host in allbot-gpu-226 allbot-gpu-177 allbot-gpu-252 allbot-gpu-002; do
  ssh "$host" 'hostname; lscpu | grep -E "Model name|^CPU\\(s\\)"; free -h; df -hT -x tmpfs -x devtmpfs; nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw,temperature.gpu --format=csv,noheader,nounits; docker ps'
done
```

Central 队列与 heartbeat：

```bash
curl -fsS http://100.107.220.127:8003/system/status
curl -fsS http://100.107.220.127:8003/system/workers
```

若需要更准确的 pending 年龄与 heartbeat TTL，可在云 Central 容器内用 Redis 客户端做只读聚合；输出时只保留计数、类型、年龄分位和 TTL，不输出连接串或任务参数。

ComfyUI 节点能力：

```bash
for base in \
  http://192.168.1.226:8188 \
  http://192.168.1.177:8188 \
  http://192.168.1.177:8189 \
  http://192.168.1.252:8188 \
  http://192.168.1.252:8189 \
  http://192.168.1.2:8188 \
  http://192.168.1.2:8189
do
  curl -fsS "$base/system_stats"
  curl -fsS "$base/queue"
done
```

ComfyUI 队列判读：
- 7 个 ComfyUI `/queue` 都能毫秒级返回，且 Central heartbeat TTL 正常：节点未挂死。
- 某个 ComfyUI `running=1` 且 GPU 利用率持续 100%：该卡正在满载推理。
- 某个 ComfyUI `running=1` 但 GPU 利用率接近 0、显存高：先看 worker 日志是否处于上传、history 补偿、模型加载或等待阶段，再考虑单容器排障。
- Central pending 某类任务堆积，但对应 worker healthy：优先考虑该任务类型耗时长或 worker 数量不足，而不是重启全部 worker。

模型挂载：

```bash
ssh allbot-gpu-177 'docker inspect comfy0 comfy1 --format "{{.Name}} {{range .Mounts}}{{println .Source \"->\" .Destination}}{{end}}"'
ssh allbot-gpu-252 'docker inspect comfy0 comfy1 --format "{{.Name}} {{range .Mounts}}{{println .Source \"->\" .Destination}}{{end}}"'
ssh allbot-gpu-002 'docker inspect comfy0 comfy1 --format "{{.Name}} {{range .Mounts}}{{println .Source \"->\" .Destination}}{{end}}"'
```

## 12. 文档维护规则

以下事件发生后应更新本文档和 `docs/子模块_系统资源与容量画像_resource_inventory.md`：
- GPU 节点新增、下线、换卡或换 IP。
- ComfyUI 端口、容器名、模型目录或实例目录变化。
- worker `SUPPORTED_TASK_TYPES` 或 `COMFY_API_URL` 调整。
- ComfyUI 从宿主机进程迁移为容器，或反向迁移。
- 共享模型目录改路径。
- 远端磁盘低于 10% 可用空间并完成清理/迁移。
