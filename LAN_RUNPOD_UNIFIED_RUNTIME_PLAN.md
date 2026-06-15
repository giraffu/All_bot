# LAN RunPod 化统一运行时方案

日期：2026-06-15

## 目标

把局域网 GPU 服务器的运行形态收敛到与 RunPod 尽量一致：

- 每个 LAN GPU slot 运行一个 profile 一体容器，容器内同时包含 `ComfyUI`、`remote relay/upload sidecar` 与 `comfy agent`。
- LAN 与 RunPod 共用镜像、profile、bootstrap、model manifest 与任务接单协议。
- 不再依赖每台 GPU 服务器各自不同的模型挂载目录、自定义节点目录和启动方式。
- 模型同步继续走 manifest 驱动；RunPod 从 R2 `allbot-model-cache` 拉取，LAN 从本地主服务器的局域网 S3/MinIO 镜像拉取。
- profile 切换必须通过受控 drain，不强制中断运行中任务。

最终状态下，GPU slot 的差异只应体现在 GPU 型号、slot id、profile env 与缓存命中情况，而不是宿主机目录结构或手工安装状态。

## 统一后的运行链路

目标链路与 RunPod 保持同构：

```text
Central API
  -> worker-central.aivison.it.com / worker-central-test.aivison.it.com
  -> GPU slot all-in-one container
  -> local remote relay at 127.0.0.1:8013
  -> comfy agent
  -> local ComfyUI at 127.0.0.1:8188
  -> R2 result upload
  -> Central /complete
```

容器内部固定约定：

- `MASTER_API_URL=http://127.0.0.1:8013`
- `UPLOAD_SIDECAR_URL=http://127.0.0.1:8013`
- `COMFY_API_URL=http://127.0.0.1:8188`
- `COMFY_WS_URL=ws://127.0.0.1:8188/ws`
- `PIPELINE_MAX_RUNNING_TASKS=1` 作为首期默认值，避免单 slot profile 切换阶段引入额外并发复杂度。
- `SUPPORTED_TASK_TYPES`、`POOL_RUNTIME_PROFILE`、`TASK_TYPE_WORKFLOW_OVERRIDES` 由 profile 渲染，不在 GPU 宿主机上手工维护。

生产接棒时，同一个 `AGENT_ID` 不能同时存在于旧主服务器 worker 容器和新 LAN 一体容器。迁移流程必须先停旧 agent 或把旧 agent control 置为 `disabled` 后，再让新一体容器 heartbeat。

## 网络差异与 Central 访问结论

现有主服务器 worker 与未来 LAN 一体容器的 Central 网络入口不同：

- 当前主服务器 `cloud-prod-comfy-agent-*` 通过本机 relay 访问云正式 Central，compose 中的 `CENTRAL_API_URL` 是 `http://${CLOUD_PROD_TAILSCALE_IP}:8003`，依赖主服务器可达云正式 Tailscale IP。
- 当前云测试本地主服务器 worker 类似，通过 `http://${CLOUD_TEST_CONTROL_HOST}:8004` 访问云测试 Tailscale IP。
- RunPod / 远程 worker 使用独立 worker Central 域名：正式 `https://worker-central.aivison.it.com`，测试 `https://worker-central-test.aivison.it.com`，由 Cloudflare Tunnel 回源 Central。

2026-06-15 从局域网 GPU 节点做过只读网络探测：

| 探测位置 | `worker-central.aivison.it.com` | `worker-central-test.aivison.it.com` | `100.107.220.127:8003` | `100.82.124.91:8004` | `192.168.1.115:5000` |
| --- | --- | --- | --- | --- | --- |
| 主服务器 | HTTP 200 | HTTP 200 | HTTP 200 | HTTP 200 | HTTP 200 |
| `gpu-002` 宿主机 | HTTP 200 | HTTP 200 | 超时 | 超时 | HTTP 200 |
| `gpu-177` 宿主机 | HTTP 200 | HTTP 200 | 超时 | 超时 | HTTP 200 |
| `gpu-252` 宿主机 | HTTP 200 | HTTP 200 | 超时 | 超时 | HTTP 200 |
| `gpu-226` 宿主机 | HTTP 200 | HTTP 200 | 超时 | 超时 | HTTP 200 |

因此，LAN 一体容器不能沿用主服务器 worker 的 `http://100.x.x.x:<port>` Tailscale Central 地址；它应按 RunPod/remote worker 方式使用 worker Central 域名。

容器网络还要注意代理环境：

- 现有部分 GPU ComfyUI 容器内存在 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` 指向 `192.168.1.115:7890`，这会让容器网络行为和宿主机不同。
- 用接近 worker relay 的 `httpx` 直连模式验证时，`https://worker-central.aivison.it.com/health` 可达，`http://100.107.220.127:8003/health` 超时。
- 一体容器启动时应显式设置 `NO_PROXY=*` 与 `no_proxy=*`，或由 profile 明确声明代理策略，避免继承宿主/基础镜像里的代理导致排障混乱。

本地主服务器 Docker registry `192.168.1.115:5000` 当前从 GPU 宿主机可达；计划中的模型缓存 S3/MinIO `192.168.1.115:9010` 尚未部署，不能作为当前可用依赖。

## 统一目录与模型缓存

LAN 宿主机只暴露标准 runtime 根目录，不再按机器自定义 ComfyUI 目录：

```text
/srv/allbot/runpod-runtime/
  models/                         # 节点共享模型缓存
  slots/
    <slot_id>/
      profiles/
        <profile>/
          workspace/              # 映射为容器 /workspace
          spool/
          logs/
```

容器内固定路径：

```text
/workspace/ComfyUI
/workspace/ComfyUI/models
/workspace/ComfyUI/input
/workspace/ComfyUI/output
/workspace/ComfyUI/temp
/workspace/allbot
```

模型同步策略：

- 新增本地主服务器局域网模型 S3/MinIO 镜像，建议服务名 `allbot-model-cache-lan`，监听 `192.168.1.115:9010`。
- 本地模型镜像只承载 `allbot-model-cache`，不得复用 legacy 媒体 MinIO 或 `user-data-prod` / `user-data-test`。
- R2 与 LAN S3 使用完全相同的 key 结构：

```text
<profile>/<version>/manifest.json
<profile>/<version>/models/<relative_path>
```

- RunPod env 继续指向 R2 endpoint；LAN env 指向局域网 S3 endpoint。
- `RUNPOD_MODEL_TARGET_DIR` 在 LAN 与 RunPod 都固定为 `/workspace/ComfyUI/models`。
- 大模型文件只通过 manifest、size 与 sha256 校验进入缓存；不得通过手工别名、散落目录或 custom node 目录夹带模型。

## 镜像与 Profile

镜像原则：

- 继续复用 `remote_workers/docker/runpod_profiles/*` 作为 profile 镜像构建入口。
- 同一个 profile 镜像推送到 GHCR 给 RunPod 使用，同时镜像到 `192.168.1.115:5000` 给 LAN GPU 节点使用。
- 镜像 baked ComfyUI、custom nodes、ffmpeg、bootstrap、remote relay 与 comfy agent。
- 镜像不得 baked 业务大模型、R2 key、Bot token、JWT secret、RunPod token 或 `.env.cloud.*`。

首期 profile 以现有 RunPod 和 GPU Pool profile 为准：

| Profile | 任务类型 | 模型来源 | 备注 |
| --- | --- | --- | --- |
| `img2img_lora` | `img2img,img2img_lora` | `img2img_lora/<version>/manifest.json` | 首期 gpu-002 slot 0 试点 |
| `video_basic` / `image_to_video` | `video_insert,video_edit,image_to_video` | `image_to_video` 或 `video_basic` manifest | 首期 gpu-002 slot 1 试点 |
| `wan22_video_v2` | `wan22_video_v2` | `wan22_video_v2/<version>/manifest.json` | 保持 RunPod split profile 口径 |
| `i2i_pro` | `i2i_pro,t2i-pornmaster-turbo,face_swap` | `i2i_pro/<version>/manifest.json` | 保持 workflow override |
| `ltx_video` | `ltx_video` | `ltx_video/<version>/manifest.json` | 后续迁移 |

长期应避免 `wan22_aio_video` 作为主路径；它只作为兼容和回滚 profile 保留。

## GPU Pool Controller 改造

新增 LAN RunPod 化 runtime 规格：

- `runtime_shape=runpod_all_in_one`
- `provider=lan_ssh`
- `slot_id=<node>-gpu<index>`
- `runtime_root=/srv/allbot/runpod-runtime`
- `model_cache_endpoint=http://192.168.1.115:9010`
- `image_registry=192.168.1.115:5000`

Controller 需要支持：

- 渲染 LAN 一体容器 compose，env 与 RunPod render 尽量同名同义。
- `runtime-plan` 展示当前 profile、目标 profile、镜像 diff、模型 manifest diff、agent id、Central URL、model endpoint 与回滚状态。
- `runtime-render` 输出只读 compose，不泄露 secret。
- `switch-profile --execute` 只允许 `comfy_runtime_managed=true` 的 slot，第一阶段仅 `gpu-002`。
- 切换前通过 Central agent control 设置 `draining`，等待目标 `AGENT_ID` 无 `current_task_id`，并确认旧 Comfy queue 为空。
- 切换期间设置 `disabled`，启动新一体容器并等待 heartbeat。
- canary 成功后才设置 `enabled`。
- 失败时保持 `disabled`，保留容器与日志现场，不自动接单。

Controller 还应显式阻止：

- 同一 `AGENT_ID` 双实例同时在线。
- host_service 直接执行 Docker 切换。
- 对整台 GPU 节点执行 reboot、无 service 名 `docker compose down/up` 或批量删除容器。
- 把 legacy 媒体 MinIO 当作模型缓存源。

## 迁移阶段

### Phase 0: 准备本地镜像源

- 启动或新增本地模型 S3/MinIO 镜像服务。
- 建立 R2 `allbot-model-cache` 到 LAN S3 的同步脚本。
- 验证 manifest、size、sha256、断点续传与本地 endpoint 访问。
- 确认各 GPU 节点 Docker daemon 可拉取 `192.168.1.115:5000` 镜像。

### Phase 1: gpu-002 云测试试点

- 在 `gpu-002` 上渲染一体容器 canary compose，先使用临时 `AGENT_ID` 和云测试 Central。
- 验证 `img2img_lora` 与 `video_basic` / `image_to_video` 两类 profile。
- 验证容器内 `/workspace/ComfyUI/models` 模型同步、ComfyUI `/system_stats`、`/queue`、`/object_info`。
- 验证任务由 LAN 一体容器 pop、生成、上传 R2、`/complete` 成功。

### Phase 2: gpu-002 生产单 slot 接棒

- 选择一个低峰维护窗口。
- 将目标旧主服务器 agent 设置为 `draining`，等待当前任务结束。
- 停止旧 `cloud-prod-comfy-agent-6` 或 `cloud-prod-comfy-agent-7`。
- 启动对应 GPU slot 一体容器，使用同一个生产 `AGENT_ID`。
- 等待 `disabled` heartbeat，执行生产 canary。
- canary 成功后设置 `enabled`。

### Phase 3: 推广到 gpu-177 / gpu-252

- 按 slot 逐个迁移，不整机切换。
- 每个 slot 先云测试 canary，再生产 disabled heartbeat，再生产 canary。
- 保留原宿主机目录作为只读回滚参考，待稳定后再清理。

### Phase 4: gpu-226 迁移

- `gpu-226` 当前是 host_service，不能直接执行 Docker 切换。
- 等其它 Docker 节点稳定后，单独安排维护窗口，把 `gpu-226` 的宿主机 ComfyUI 迁为同款一体容器。
- 迁移前必须导出现有 systemd 启动参数、模型清单、custom nodes 清单和回滚命令。

## 验证与回滚

每次切换前验证：

- 目标模型 manifest 在 LAN S3 可读。
- 目标镜像在 LAN registry 可拉取。
- 目标 GPU 节点磁盘空间足够。
- Central agent control 可读写。
- 旧 agent 无运行中任务，ComfyUI `/queue` 为空。

每次切换后验证：

- 一体容器 `Up`，无高频 `ERROR/Traceback/Exception`。
- ComfyUI `/system_stats`、`/queue`、`/object_info` 正常。
- remote relay `/ready` 正常。
- Central `/system/workers` 出现目标 `AGENT_ID` heartbeat，profile、task types、GPU pool metadata 符合预期。
- 真实 canary 任务由目标 `AGENT_ID` pop。
- 结果上传 R2 成功后才 `/complete`。
- Web owner result 返回成功，视频任务必须确认 R2 result ready。

回滚入口：

- 设置目标 `AGENT_ID` 为 `disabled`。
- 停止新 LAN 一体容器。
- 恢复旧主服务器 `cloud-prod-comfy-agent-*` 或上一版 LAN profile 容器。
- 等待旧 worker heartbeat。
- 跑原 profile canary。
- 成功后设置 `enabled`。

## 风险与边界

- 本方案是运行时统一方案，不改变业务 task type，也不新增用户侧功能入口。
- 运行时统一不代表立即全量迁移；首批只允许 `gpu-002` 试点。
- LAN 模型缓存是模型专用对象存储，不得与 legacy 媒体 MinIO 混用。
- profile 镜像可以共享，但模型必须通过 manifest 外置同步，不 baked 入镜像。
- 生产切换必须显式维护窗口确认；普通研发、联调或文档更新不等于允许上线。
- 同一 `AGENT_ID` 双实例同时在线会导致任务竞争，必须由脚本和人工检查双重阻断。
- 任何失败都应默认停在 `disabled`，保留现场排查，而不是自动恢复接单。
- 修改 Controller、profile、compose、agent control、模型同步或 RunPod/LAN 运行口径后，必须同步更新相关 docs / skills，并调用知识库同步流程。
