# AllBot GPU Pool Runtime 容器化接管路线图

更新时间：2026-06-10  
当前口径：Worker Agent 新协议、模型仓库、镜像仓库、Controller Phase 0 dry-run 能力与 Phase 1A 备用端口 canary 渲染能力已经完成；底层 ComfyUI Runtime 仍未全量纳入 Controller 自动接管。`POOL_IMAGE_REF`、profile 镜像、bundle 版本、`runtime-plan` 与 `runtime-render --host-port` 输出均是目标声明或 dry-run / render 计划，不等于当前 ComfyUI Runtime 已经由对应镜像实际运行。

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

### 1.2 当前 GPU 节点事实

| 节点 | GPU | 当前 Runtime | Controller 状态 | 当前 worker / profile |
| :--- | :--- | :--- | :--- | :--- |
| `gpu-226` / `192.168.1.226` | 1 x RTX 5090 32G | 宿主机进程 `8188` | `host_service`，`managed=false` | `cloud_prod_worker_01` / `face_i2i_t2i` |
| `gpu-177` / `192.168.1.177` | 2 x RTX 5090 32G | Docker `comfy0/comfy1`，`8188/8189` | `docker_container`，`managed=false` | worker 02=`video_basic`，worker 03=`ltx_video` |
| `gpu-252` / `192.168.1.252` | 2 x RTX 4090 48G | Docker `comfy0/comfy1`，`8188/8189` | `docker_container`，`managed=false` | worker 04=`img2img_lora`，worker 05=`wan22_video_v2` |
| `gpu-002` / `192.168.1.2` | 2 x RTX 4090 48G | Docker `comfy0/comfy1`，`8188/8189` | `docker_container`，`managed=true` Phase 1 试点 | worker 06=`img2img_lora`，worker 07=`video_basic` |

关键边界：

- `gpu-226` 是最后迁移对象，不得对它执行 `docker restart comfy0` 或任何假设 Docker Comfy 存在的命令。
- `gpu-177/252` 可生成 dry-run 计划，但未标记为可执行接管；Phase 1 通过前不要推进。
- `remote_workers` 不纳入本地动态 GPU 资源池。

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

禁止：

- 用 `--remove-orphans` 清理 worker project。
- 无 service 名执行 `docker compose down/up`。
- 因一个 Comfy 容器异常整机 reboot。
- 在未 drain 的情况下用强制重启代替能力切换。
- 把 `POOL_IMAGE_REF` 当作当前 ComfyUI 实际镜像。
- 把 `runtime-render` 输出直接用于 `gpu-226` 或任何 `host_service` runtime。

## 3. Controller 命令参考

### 3.1 现有 dry-run 命令

```bash
python scripts/gpu_pool_controller.py inventory
python scripts/gpu_pool_controller.py plan
python scripts/gpu_pool_controller.py runtime-plan
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
python scripts/gpu_pool_controller.py canary --assignment lan-252-8188-worker-04
python scripts/gpu_pool_controller.py workflow-model-check
python scripts/gpu_pool_controller.py model-import-plan
python scripts/gpu_pool_controller.py model-import-execute
```

预期行为：

- `plan`：输出 7 个 assignment 的资源池 dry-run。`gpu-226` 只允许出现 host_service 警告，不得出现 Docker pull/up/restart。
- `runtime-plan`：输出 runtime / image / model bundle / worker env diff。
- `runtime-plan --host-port 8190`：输出备用端口 canary worker env，默认指向 `http://192.168.1.2:8190` / `ws://192.168.1.2:8190/ws`，只给测试 worker 审阅和后续手工覆盖使用。
- `runtime-render`：仅支持 `docker_container`；对 `gpu-226` 应返回结构化错误并退出非 0。
- `runtime-render --host-port 8190`：渲染 `8190:8188` 的 canary compose，默认容器名为 `allbot-comfy-gpu0-canary`，不会覆盖生产 `8188`。
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

状态：等待 Phase 1A 和维护窗口。

只允许在用户明确确认维护窗口后执行。

执行顺序：

1. 运行 dry-run：

   ```bash
   python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
   python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06 --profile video_basic --host-port 8190
   ```

2. 只读检查 `gpu-002`：

   ```bash
   ssh allbot-gpu-002 'df -hT / /data || true; docker ps --format "{{.Names}} {{.Image}} {{.Status}}"'
   ```

3. 确认本地 registry 和镜像：

   ```bash
   curl -fsS http://127.0.0.1:5000/v2/_catalog
   curl -fsS http://127.0.0.1:5000/v2/allbot/comfy-cu130-video-basic/tags/list
   ```

4. 若 GPU 节点尚未信任 `192.168.1.115:5000`，在维护窗口内配置 Docker daemon insecure registry。
5. 在 `gpu-002` 启动备用端口 runtime，不碰现有 `comfy0/comfy1`。
6. 对备用端口运行：

   ```bash
   curl -fsS http://192.168.1.2:8190/system_stats
   curl -fsS http://192.168.1.2:8190/queue
   curl -fsS http://192.168.1.2:8190/object_info
   ```

7. 用云测试 worker 6/7 指向备用端口：

   ```bash
   set -a
   source .env.cloud.test
   set +a

   CLOUD_TEST_WORKER_06_TASK_TYPES='video_insert,image_to_video' \
   CLOUD_TEST_WORKER_06_RUNTIME_PROFILE='video_basic_canary' \
   CLOUD_TEST_WORKER_06_COMFY_API_URL='http://192.168.1.2:8190' \
   CLOUD_TEST_WORKER_06_COMFY_WS_URL='ws://192.168.1.2:8190/ws' \
   docker-compose --env-file .env.cloud.test -f workers/docker-compose-cloud-worker-test.yml \
     up -d --no-deps cloud-comfy-agent-test-6
   ```

8. 验证 `/system/workers` 中 `cloud_worker_test_06` 的 task types、runtime profile、node/gpu 元数据和 healthy 状态。
9. 提交真实测试任务 canary，确认结果上传到 R2 `user-data-test`。
10. 恢复测试 worker 默认配置，并停止备用端口 runtime。

验收：

- 备用 runtime `/system_stats`、`/queue`、`/object_info` 正常。
- required nodes 全部存在。
- 测试任务完成并上传到测试 R2。
- `cloud_worker_test_06/07` 可恢复默认类型。
- 不影响正式 worker 6/7 的默认生产 `8188/8189`。

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

状态：等待 Phase 1 完成。

目标：

- 将 `gpu-252` 的 `img2img_lora` 与 `wan22_video_v2` 标准化为 Controller managed runtime。
- 验证 48G profile、共享模型目录去重和回滚速度。

准入条件：

- Phase 1B 至少完成一次备用端口真实 canary。
- Phase 1C 执行器有 focused tests。
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

镜像原则：

- 镜像包含 ComfyUI、Python 环境、custom nodes、系统依赖和启动脚本。
- 模型不默认打进镜像。
- 按 profile 拆分，不做一个无限膨胀的大一统镜像。
- 保留 debug/base 镜像用于人工排障。
- 任何 profile 镜像进入 live canary 前，必须能被 `runtime-render` 引用并从目标 GPU 节点 pull。

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

交付前：

- focused tests 通过。
- dry-run 输出已保存或总结。
- 文档和 skill 已同步。
- 明确说明是否执行了 live canary；默认没有执行。

## 9. 当前未完成事项

- Phase 1A 只完成了 dry-run / render 能力，尚未执行 `gpu-002` 备用端口 live canary。
- `runtime-apply/switch-profile/rollback-profile --execute` 尚未实现真实执行器。
- profile 专用镜像矩阵尚未全部构建和验证。
- `runtime-plan` 尚未做远端磁盘/swap/registry 信任状态采集。
- 模型 bundle sync 仍是计划能力，尚未接入安全执行器。
- Comfy real task canary 尚未自动化；当前 `canary` 只做 HTTP/object_info 级验证。
- Central Redis 偶发写连接 reset 是独立 P1 生产观察项，应另起修复，不要混入 runtime 接管。

## 10. 下一步推荐

下一轮最小闭环：

1. 审阅 `gpu-002` 的 `8190/8191` canary plan 与 compose 输出。
2. 在只读模式下验证 registry catalog、目标 image tag、`gpu-002` 磁盘和当前容器布局。
3. 用户确认维护窗口后，执行 `gpu-002` 备用端口 live canary。
4. live canary 通过后，记录测试 R2 结果和 `/system/workers` 状态。
5. 再实现 `runtime-apply --execute` 的最小安全执行器。

这条路线的原则：先把已经是 Docker 的 `gpu-002` 用备用端口纳入 Controller 验证，再考虑替换生产端口；最后才迁移最特殊的 `gpu-226`。
