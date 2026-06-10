# AllBot GPU Pool 升级状态与 ComfyUI Runtime 容器化接管路线图

更新时间：2026-06-10  
当前口径：第一阶段已经完成 Worker Agent 新协议、模型仓库、镜像仓库与 Controller dry-run 基础能力；底层 ComfyUI Runtime 还没有全部容器化并纳入 Controller 自动接管。文档中 `POOL_IMAGE_REF`、profile 镜像和 bundle 版本属于目标/期望声明，不等同于当前 ComfyUI Runtime 已由该镜像实际运行。

## 1. 最终目标

目标不是简单把 ComfyUI 放进 Docker，而是建立一套可以长期扩展的 GPU 算力资源池：

- 业务层只改 `ops/gpu_pool_controller/config/assignments.yml`，声明哪个 GPU/worker 支持哪些任务类型。
- Controller 根据 `task_profiles.yml` 自动推导目标节点需要的 ComfyUI 镜像、模型 bundle、custom nodes、workflow、worker 配置和 canary 验收。
- 每张 GPU 都有明确的 ComfyUI Runtime 实例，统一由 Controller 盘点、预热、切换、回滚。
- Worker Agent 层继续负责 `pop/status/complete/heartbeat`、workflow patch、R2 上传和结果回流。
- ComfyUI Runtime 层负责实际模型加载与推理，最终全部使用受控 Docker 容器运行。
- 本地 4 台 LAN GPU 节点先接管；RunPod 后续作为 `RunPodProvider` 接入同一套 profile / bundle / image / assignment 抽象。

目标状态下，一次任务能力切换应变成：

```text
修改 assignments.yml
-> controller plan
-> drain 目标 worker
-> sync model bundle
-> pull/switch ComfyUI runtime image
-> update worker task types/runtime metadata
-> canary
-> enable worker
```

## 2. 已完成升级项

### 2.1 Worker Agent 新协议

已在正式 worker 层完成：

- 7 个本地 `cloud-prod-comfy-agent-*` 已升级到新 Worker Agent 镜像。
- Worker `/api/agent/task/pop` 已携带 `agent_id`。
- Central 已支持 `enabled / draining / disabled` 控制键。
- worker heartbeat 已能携带 GPU pool 元数据，例如 `node_id`、`gpu_index`、`runtime_profile`、`pool_managed`。
- 本地 relay `/ready` 已可用于 worker/relay 深度健康检查。
- 测试环境已用 `cloud_worker_test_06/07` 验证多 worker 控制和任务类型声明切换。

重要边界：

- 这里的“新协议生效”只表示 Worker Agent 层生效。
- 不表示底层 ComfyUI Runtime 已经全部容器化。
- `cloud_prod_worker_01` 对应的 `gpu-226:8188` 仍是宿主机 ComfyUI 服务。

### 2.2 本地模型仓库

本地主服务器已建立模型仓库：

```text
/srv/allbot/model-registry
```

当前状态：

- 仓库大小约 `258G`。
- 首轮导入报告存在：
  - `/srv/allbot/model-registry/reports/model-import-plan-20260610.json`
  - `/srv/allbot/model-registry/reports/model-import-execute-20260610.json`
- `model-import-plan` 结果：`missing_count=0`。
- `model-import-execute` 结果：复制 `65` 个 sha256 blob，跳过已存在 `6` 个，生成 `5` 个 bundle manifest。

已落库 bundle：

- `face_i2i_t2i_baseline`
- `video_basic_baseline`
- `ltx_video_baseline`
- `img2img_lora_baseline`
- `wan22_video_v2_baseline`

模型仓库采用 sha256 内容寻址：

```text
/srv/allbot/model-registry/blobs/sha256/...
/srv/allbot/model-registry/bundles/<bundle>/<version>/manifest.yml
```

同一模型被多个 bundle 使用时只保存一份 blob，避免模型仓库膨胀。

### 2.3 本地 Docker Registry

本地主服务器已启动本地镜像仓库：

```text
/srv/allbot/docker-registry
```

当前状态：

- 仓库大小约 `17G`。
- 容器：`allbot-local-registry`
- 监听：
  - `127.0.0.1:5000`
  - `192.168.1.115:5000`

当前 registry catalog：

```text
allbot/comfyui-boot
allbot/worker-agent
allbot/worker-relay
```

当前 tag：

```text
allbot/comfyui-boot:
  cu128-slim-gpu002-5daf3995
  cu130-slim-gpu177-df7c4868
  cu128-slim-gpu252-e4124ab9

allbot/worker-agent:
  942c59c-41fa5a382d29
  942c59c-3df88b45635e

allbot/worker-relay:
  942c59c-41fa5a382d29
```

注意：

- 当前已有的是 ComfyUI boot/runtime 基线镜像归档，不是最终 profile 专用镜像矩阵。
- 目标 profile 镜像如 `allbot/comfy-cu130-ltx`、`allbot/comfy-cu128-wan22` 仍属于后续构建项。
- GPU 节点从 `192.168.1.115:5000` pull 前，还需要在维护窗口配置 Docker daemon 信任该 insecure registry。

### 2.4 GPU Pool Controller v1

已建立 Controller 子系统：

```text
ops/gpu_pool_controller/
scripts/gpu_pool_controller.py
```

已具备的基础模块：

- `providers/lan_ssh.py`
- `providers/runpod.py` 桩
- `model_repo.py`
- `model_importer.py`
- `image_repo.py`
- `planner.py`
- `canary.py`
- `config_loader.py`
- `types.py`

已建立声明式配置：

- `nodes.yml`
- `task_profiles.yml`
- `assignments.yml`
- `model_bundles.yml`

常用命令：

```bash
python scripts/gpu_pool_controller.py inventory
python scripts/gpu_pool_controller.py plan
python scripts/gpu_pool_controller.py canary --assignment lan-252-8188-worker-04
python scripts/gpu_pool_controller.py workflow-model-check
python scripts/gpu_pool_controller.py model-import-plan
python scripts/gpu_pool_controller.py model-import-execute
```

当前 Controller 仍是 dry-run / canary 优先，不默认改生产 ComfyUI Runtime。

### 2.5 正式环境更新与知识库纠偏

已完成：

- 云正式数据库迁移到 Alembic `4f9a2b7c8d10`。
- 本地正式 7 个 worker agent 和 relay 已重建并运行。
- Dashboard Backend 已补 billing core provider 注册，避免退款/终止路径出现 `Billing core providers 未注册`。
- 知识库已明确区分 Worker Agent 层与 ComfyUI Runtime 层。
- 常规正式 worker/relay 更新 SOP 已改为优先维护门禁、阻止新任务、等待队列或目标 worker 空闲后再重建。

待修复的生产观察项：

- Central Redis 写连接偶发 reset，可能导致 `/status/{task_id}` 或 worker heartbeat/status 短暂 500。后续应在 Central Redis 关键读写路径增加有限 retry/reconnect。

## 3. 当前 GPU 节点状态

| 节点 | GPU | 当前 ComfyUI Runtime | 当前 worker | 当前 profile / 实际任务类型 |
| :--- | :--- | :--- | :--- | :--- |
| `gpu-226` / `192.168.1.226` | 1 x RTX 5090 32G | 宿主机进程，端口 `8188` | `cloud_prod_worker_01` | profile `face_i2i_t2i`；任务 `face_swap,i2i_pro,i2i_draw,face_video,video_edit,image_to_video,t2i-pornmaster-turbo` |
| `gpu-177` / `192.168.1.177` | 2 x RTX 5090 32G | Docker `comfy0/comfy1`，端口 `8188/8189` | `cloud_prod_worker_02/03` | worker 02 profile `video_basic`，任务 `video_insert,video_edit,image_to_video`；worker 03 profile `ltx_video`，任务 `ltx_video,image_to_video` |
| `gpu-252` / `192.168.1.252` | 2 x RTX 4090 48G | Docker `comfy0/comfy1`，端口 `8188/8189` | `cloud_prod_worker_04/05` | worker 04 profile `img2img_lora`，任务 `img2img,img2img_lora`；worker 05 profile `wan22_video_v2`，任务 `wan22_video_v2,video_edit,image_to_video` |
| `gpu-002` / `192.168.1.2` | 2 x RTX 4090 48G | Docker `comfy0/comfy1`，端口 `8188/8189` | `cloud_prod_worker_06/07` | worker 06 profile `img2img_lora`，任务 `img2img,img2img_lora`；worker 07 profile `video_basic`，任务 `video_insert,video_edit,image_to_video` |

关键边界：

- `gpu-226` 是最后迁移对象，不能按 Docker Comfy 容器处理。
- `gpu-177/252/002` 已是 Docker Comfy，但还没有完全标准化为 Controller 生成和接管的 compose/runtime。
- `remote_workers` 不纳入本地动态 GPU 资源池，因为当前不能通过 LAN SSH 可靠管理。

## 4. 尚未完成的目标

### 4.1 ComfyUI Runtime 全容器化

未完成项：

- `gpu-226` 仍是宿主机 ComfyUI，需要迁移为容器。
- `gpu-177/252/002` 虽然已经是 Docker Comfy，但还不是 Controller 标准生成和生命周期管理。
- 还没有统一的 runtime compose 模板。
- 还没有统一的容器命名、label、健康检查、profile 切换和回滚机制。

目标：

```text
gpu-xxx:
  allbot-comfy-gpu0 -> GPU 0 -> 8188
  allbot-comfy-gpu1 -> GPU 1 -> 8189
```

单卡节点：

```text
gpu-226:
  allbot-comfy-gpu0 -> GPU 0 -> 8188 或迁移期新端口 8190
```

### 4.2 Profile 专用镜像矩阵

建议目标镜像矩阵如下。该列表描述 Phase 1+ 目标 profile 镜像命名，不表示当前每个 worker 的 `POOL_IMAGE_REF` 或底层 ComfyUI Runtime 已完全一致；例如 worker 07 当前声明为 `comfy-cu128-video-basic`，而 `task_profiles.yml` 中的 `video_basic` 目标镜像仍是 `comfy-cu130-video-basic`。

```text
192.168.1.115:5000/allbot/comfy-cu130-face-i2i:baseline
192.168.1.115:5000/allbot/comfy-cu130-video-basic:baseline
192.168.1.115:5000/allbot/comfy-cu130-ltx:baseline
192.168.1.115:5000/allbot/comfy-cu128-img2img:baseline
192.168.1.115:5000/allbot/comfy-cu128-wan22:baseline
192.168.1.115:5000/allbot/worker-agent:<git_sha>
```

原则：

- 镜像包含 ComfyUI、Python 环境、custom nodes、系统依赖和启动脚本。
- 模型不默认打进镜像。
- 镜像按 profile 拆分，不做一个无限膨胀的大一统镜像。
- 可保留一个 debug/base 镜像用于人工排障。

### 4.3 Controller 真实执行命令

需要新增或补强命令：

```bash
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-apply --assignment lan-002-8188-worker-06 --execute
python scripts/gpu_pool_controller.py prewarm-profile --assignment lan-002-8188-worker-06 --profile wan22_video_v2
python scripts/gpu_pool_controller.py switch-profile --assignment lan-002-8188-worker-06 --profile img2img_lora --execute
python scripts/gpu_pool_controller.py rollback-profile --assignment lan-002-8188-worker-06 --execute
```

命令默认 dry-run，真实变更必须显式 `--execute`。

## 5. 标准化 Runtime 设计

每个 ComfyUI Runtime 应具备以下声明字段：

```yaml
comfy_runtime_kind: docker_container
comfy_runtime_managed: true
container_name: allbot-comfy-gpu0
image_ref: 192.168.1.115:5000/allbot/comfy-cu128-img2img:baseline
gpu_index: 0
host_port: 8188
container_port: 8188
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

统一挂载原则：

- `models` 可共享，按节点共享模型目录。
- `input/output/temp/custom_nodes/workflows` 必须按 GPU 实例隔离。
- custom nodes 和 workflows 随镜像/profile 或受控同步，不由业务运行中随意改。
- 清理脚本只碰 `input/output/temp`，不碰 `models/custom_nodes/workflows`。

## 6. 标准切换流程

一次 profile 切换必须按以下顺序：

1. 读取 `assignments.yml` 与目标 `task_profiles.yml`。
2. Controller 输出 dry-run diff：
   - worker task types diff
   - runtime image diff
   - model bundle diff
   - custom node / object_info diff
   - GPU/VRAM/磁盘/swap 风险
3. 设置目标 worker 为 `draining`。
4. 等待：
   - Central 中目标 worker 不再接新任务
   - 目标 Comfy `/queue` 的 running/pending 清空
   - task heartbeat 无目标 worker 正在运行的正式任务
5. 同步模型 bundle：
   - 只写目标共享 `models`
   - sha256 校验
   - 不复制重复模型
6. pull 目标 runtime image。
7. 重建目标 ComfyUI 容器。
8. 验证 Comfy：
   - `/system_stats`
   - `/queue`
   - `/object_info`
   - required nodes
   - required model paths
9. 更新 Worker Agent：
   - `SUPPORTED_TASK_TYPES`
   - `RUNTIME_PROFILE`
   - `POOL_IMAGE_REF`
   - `MODEL_BUNDLE_VERSIONS`
10. 启动 worker 并恢复 `enabled`。
11. 提交真实 canary。
12. canary 成功后扩大到正式任务；失败则 rollback。

## 7. 分阶段落地计划

### Phase 0：Controller Schema 与 dry-run 完整化

目标：

- 扩展 `nodes.yml`，把每个 Comfy 实例的 runtime 管理字段补齐，例如 `comfy_runtime_kind`、`comfy_runtime_managed`、`container_name`、`compose_template`、`rollback_state`。
- 补齐 `task_profiles.yml` 的 canary 元数据和 runtime diff 所需字段；当前 `image_ref`、model bundles、required nodes、最低显存和 workflow 已有首版配置。
- 收敛 `assignments.yml`，让业务层只声明目标任务类型和 profile，runtime 细节由 node/profile 推导。
- 增加 runtime diff 输出，不执行任何远端变更。

验收：

- `runtime-plan` 能对 7 个 assignment 输出差异。
- 能识别 `gpu-226` 是 `host_service`，不生成 Docker 操作计划。
- 能识别 Docker runtime 的 image/model/profile 差异。

### Phase 1：`gpu-002` 测试试点

选择：

- `gpu-002:8188` / `cloud_worker_test_06`
- `gpu-002:8189` / `cloud_worker_test_07`

原因：

- 已在测试环境验证过 worker 6/7 控制链路。
- 002 是双 4090 48G，适合做 img2img/video_basic 互换和后续 Wan22 预热测试。
- 不需要先碰 `gpu-226` 宿主机 ComfyUI。

工作项：

- 为 `gpu-002` 生成标准 runtime compose。
- 配置 `192.168.1.115:5000` insecure registry。
- 用 test worker 6/7 做 profile 切换：
  - `img2img_lora -> video_basic`
  - `video_basic -> img2img_lora`
- 跑真实测试任务 canary。

验收：

- test worker 6/7 能被单独 `draining/disabled/enabled`。
- profile 切换不会影响其它正式 worker。
- ComfyUI 容器切换后 `/object_info` 暴露目标 required nodes。
- 测试任务能完成并上传到测试 R2。

### Phase 2：`gpu-252` 48G 正式候选

目标：

- 将 `gpu-252` 的 `comfy0/comfy1` 标准化为 Controller 管理 runtime。
- 验证 `img2img_lora` 与 `wan22_video_v2` 两个 48G profile。
- 测试模型 bundle 共享目录去重和切换速度。

验收：

- `wan22_video_v2` canary 成功。
- `img2img_lora` canary 成功。
- 重启 `comfy0` 不影响 `comfy1`，反之亦然。
- 失败时可回滚到原镜像和原 worker task types。

### Phase 3：`gpu-177` 5090 cu130 profile

目标：

- 标准化 `gpu-177` 的 `video_basic` 与 `ltx_video`。
- 构建 cu130 profile 镜像。
- 验证 LTX custom nodes、RIFE、VHS、rgthree LoRA loader。

验收：

- `ltx_video` canary 成功。
- `video_basic` canary 成功。
- `FL_RIFE` 不再依赖人工在容器里补依赖。

### Phase 4：`gpu-226` 宿主机 ComfyUI 迁移

这是风险最高的一步，最后做。

推荐迁移方式：

1. 不直接替换 `8188`。
2. 先在 `gpu-226` 起新容器到 `8190`。
3. 复用或同步 `/home/ubantu/comfyui/models`。
4. 对 `8190` 跑：
   - `/system_stats`
   - `/object_info`
   - face/i2i/t2i canary
5. 测试 worker 先指向 `8190`。
6. 成功后再考虑正式 worker 01 从 `8188` 切到容器端口。
7. 保留宿主机 ComfyUI 作为短期回滚。

验收：

- worker 01 的全部任务类型 canary 成功。
- t2i workflow 模型路径与 `/object_info` 完全一致。
- 宿主机 ComfyUI 可作为回滚入口保留，直到容器运行稳定。

### Phase 5：正式环境灰度接管

顺序：

1. 先接管测试 worker。
2. 再接管正式低风险 worker。
3. 再接管视频长任务 worker。
4. 最后接管 `worker_01 / gpu-226`。

每次正式接管必须：

- 开启维护或等价门禁，阻止新生成任务进入。
- 等待目标 worker 或全局队列达到维护条件。
- 执行 Controller `--execute`。
- canary 成功后关闭维护。
- 观察 Central `/system/workers`、Comfy `/queue`、R2 上传和任务完成回调。

### Phase 6：RunPod Provider 扩展

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

RunPod 侧优先从云端模型仓库或 Hugging Face / R2 / S3 热缓存拉模型，不从本地主服务器跨公网拉大模型。

## 8. 回滚策略

每次切换必须保存上一版 runtime state：

```yaml
previous:
  image_ref: ...
  task_types: ...
  runtime_profile: ...
  model_bundle_versions: ...
  compose_render_hash: ...
  container_id: ...
```

回滚流程：

1. 设置目标 worker `disabled`。
2. 停止新 runtime 容器。
3. 恢复上一版 image 和 compose。
4. 恢复 worker task types 和 runtime metadata。
5. 验证 `/system_stats`、`/queue`、`/object_info`。
6. 跑原 profile canary。
7. 恢复 `enabled`。

对于 `gpu-226` 迁移期，回滚优先方式是把 worker 01 的 `COMFY_API_URL` 指回宿主机 `192.168.1.226:8188`。

## 9. 验收标准

### 9.1 单节点切换验收

- Controller dry-run diff 清晰。
- 目标 worker drain 生效，不再接新任务。
- 目标 Comfy queue 清空后才切换。
- 模型 bundle sha256 校验通过。
- runtime image pull 成功。
- Comfy `/system_stats`、`/queue`、`/object_info` 正常。
- required nodes 和 required model paths 全部满足。
- 真实 canary 任务完成并上传结果。
- Central `/system/workers` 显示 worker healthy。
- 失败可在 5-10 分钟内回滚。

### 9.2 全池接管验收

- 7 张 GPU 都是 Controller 可识别 runtime。
- 6 个 Docker Comfy 实例已标准化；`gpu-226` 完成容器迁移。
- 业务层可以只通过 `assignments.yml` 切换任务能力。
- 所有 profile 至少有一个已验证节点。
- 所有 profile 镜像都在本地 registry 和云端 registry 有副本。
- 所有首轮模型 bundle 都有本地模型仓库 manifest，并有云端镜像或热缓存策略。
- RunPod provider 可复用同一 profile / bundle / image 配置。

## 10. 风险与约束

- 任务能力切换不等于无限快；如果模型和镜像未预热，切换可能从数分钟变成数小时。
- 4090 48G 和 5090 32G 不应无脑互换所有 profile；Wan22 等高显存任务优先保留在 48G 节点。
- 双卡节点共享模型目录，删除或替换模型前必须确认另一张卡没有正在使用同一文件。
- `gpu-226` 从宿主机进程迁移到容器时，要保留宿主机回滚路径。
- Docker daemon insecure registry 配置属于 GPU 节点维护动作，需要维护窗口。
- Controller 真实执行必须默认禁止批量操作；一次只切一个 assignment，直到灰度稳定。

## 11. 下一步建议

建议下一步直接做 Phase 0 + Phase 1：

1. 扩展 Controller schema，补 `comfy_runtime_kind`、`comfy_runtime_managed`、`container_name`、`compose_template`、`rollback_state`。
2. 新增 `runtime-plan`，只输出 `gpu-002` 的切换计划。
3. 新增 `runtime-render`，生成 `gpu-002` 的标准 Comfy runtime compose。
4. 在测试环境用 `cloud_worker_test_06/07` 做 `img2img_lora` 与 `video_basic` 互换。
5. 成功后再把同一能力扩展到 `gpu-252`。

这条路线最稳：先把已经是 Docker 的节点纳入 Controller，再迁移最特殊的 `gpu-226`。
