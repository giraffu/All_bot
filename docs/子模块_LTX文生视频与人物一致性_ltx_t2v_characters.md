# 子模块：LTX 2.3 Sulphur 文生视频与 Ingredients 人物一致性

## 1. 范围与发布状态

本能力使用独立执行 profile `ltx_t2v`，不会替换现有 `ltx_video` / 10Eros
图生视频。它包含三个用户任务：

- `ltx_t2v`：纯文生同步音视频；
- `ltx_t2v_ic`：文生同步音视频 + 私有人物参考表 + Ingredients；
- `character_reference_build`：从本人上传源图生成六视图参考表。

本阶段仅允许本地 LAN 验收。后端 `LTX_T2V_BACKEND_ENABLED` 和 Web runtime
flag `enable_ltx_t2v` 默认均为关闭；不得部署共享 test/prod，不创建 RunPod
template，也不得把本地 registry 镜像当作 GHCR 正式 artifact。

## 2. 固定模型栈

模型 bundle 为 `ltx_t2v_runtime/2026-07-22`，LAN model-cache 前缀为
`ltx_t2v/2026-07-22`。运行栈顺序固定为：

1. 官方 `ltx-2.3-22b-dev-fp8.safetensors`；
2. 官方 distilled LoRA，强度 `0.5`；
3. Sulphur rank-768 LoRA，强度 `1.0`；
4. 仅 IC 任务追加 Ingredients 0.9，强度 `1.0`。

用户不能在这个固定栈上继续叠加 LoRA。Gemma、视频/音频 VAE 和空间
upscaler 复用 content-addressed registry 既有 blobs，不重复下载。权重不 baked
进镜像。

Ingredients 来自 Lightricks gated 仓库。操作者必须先接受许可，再在当前 shell
通过只读 `HF_TOKEN` 或 `HUGGING_FACE_HUB_TOKEN` 注入；Token 不写入 Git、模型
manifest、命令行参数或日志。准备入口：

```bash
python scripts/prepare_ltx_t2v_model_bundle.py \
  --registry-root /srv/allbot/model-registry
```

脚本在下载前要求 registry 同文件系统至少 75 GiB 可用空间，流式写临时文件，
校验 size/SHA256 后用硬链接导入 blob store，再移除临时文件。

发布到 LAN model-cache 必须复用共享 SHA 对象池，禁止按新 profile 前缀重复上传
七个既有 blob：

```bash
python scripts/upload_all_task_models_to_lan_cache.py \
  --env-file .env.lan.model-cache \
  --repo-root /srv/allbot/model-registry \
  --target ltx_t2v
# 核对 dry-run 的 upload_count / upload_total_size_bytes 与宿主余量后才追加 --execute
```

`--target ltx_t2v` 只构建 `ltx_t2v/2026-07-22/manifest.json`，模型对象使用
`models/by-sha256/<sha[:2]>/<sha>`；manifest 只有在全部对象 HEAD 的大小和 SHA
metadata 都通过后才发布。

2026-07-22 本地发布验收已确认：复用 7 个共享 blob，新上传 3 个 blob、
`40,722,210,544` bytes；10/10 对象 HEAD 验证通过，manifest SHA256 为
`e9f35a43c75bc539f4fe6d5545da267907ac483fca88de02cf0a4d6c897e2ca8`。
发布后的第二次 dry-run 为 `upload_count=0`、`skipped_existing_count=10`、
`manifest_skip_count=1`。该缓存证据不代表 GPU workflow 或业务全链路已通过。

## 3. 工作流与容器

运行 workflow 的事实源：

- `workers/comfy_agent/workflows/LTX 2.3 Sulphur T2V.json`；
- `workers/comfy_agent/workflows/LTX 2.3 Sulphur Ingredients T2V.json`；
- `workers/comfy_agent/workflows/Character Reference Six Views.json`。

`remote_workers/` 保持镜像内副本同步。两张 LTX 图均为 API-format、双阶段、
同步音频输出；T2V 是 `1280x704` 和 `24 * seconds + 1` 帧，IC 第一版锁定
`768x448 / 121 frames / 24fps`。候选 ComfyUI 使用 `--reserve-vram 5`。

四组有序 LAN A/B 图位于
`ops/gpu_pool_controller/validation_workflows/ltx_t2v/`。第 1/3 组只是官方
baseline；只有第 2 组完整 Sulphur T2V 和第 4 组完整 Sulphur + Ingredients
均产出可播放、带音轨 MP4，目标栈才通过。

镜像入口：

- `remote_workers/docker/runpod_profiles/ltx_t2v/Dockerfile`；
- `remote_workers/docker/runpod_profiles/pornmaster_flux2_edit/Dockerfile`。

LTX 镜像固定 ComfyUI revision `7bf8bfcd078c7f4ae50ca5149c9ff7d8613e1fb1`
和 ComfyUI-LTXVideo revision `aceeae9635f6d493f2893ba3c411a1c36031788a`。
构建必须验证 Ingredients loader/guide、低显存 loader、音视频 VAE、全部 workflow
节点可导入，并拒绝镜像内 `.safetensors`。

## 4. 人物资产与任务链

`character_references` 记录 UUID、owner、名称/描述、源图 key、参考表 key、任务
ID、状态与时间戳。资产只能由 owner 访问，不可投稿；每人最多保留 20 个
`ready` 人物，`pending` 仍受普通任务并发限制。

`POST /api/characters/build` 只接受当前用户
`web_uploads/{internal_user_id}/...` 下不超过 20 MiB 的 PNG/JPEG/WebP。PornMaster
FP8 在一个 workflow 中生成固定六视图，worker 要求六个输出标记完整且唯一，
然后用 Pillow 按以下顺序确定性拼成黑底 `1536x896` PNG：

1. 正脸近照；2. 3/4 脸；3. 正面半身；
4. 全身正面；5. 全身侧面；6. 全身背面。

子图只作 worker 临时材料，不单独上传。终态 finalizer 幂等把人物更新为
`ready` 或 `failed`；构建任务进入本人 History，但固定
`gallery_supported=false`。失败、取消或入队失败使用现有 Saga 幂等退款。

## 5. API、计费与所有权

人物 API 为 `POST /api/characters/build`、`GET /api/characters`、
`PATCH /api/characters/{id}` 和 `DELETE /api/characters/{id}`。DELETE 是软删除，
pending 构建返回 409。

视频仍走 `POST /api/tasks/generate`：

- `ltx_t2v`：5/10/15/20 秒分别 10/20/30/40 灵石；
- `ltx_t2v_ic`：固定 5 秒 12 灵石；
- 人物参考表：18 灵石。

IC 客户端只能提交 `character_id`。服务端在扣费前验证 owner、`ready` 状态和
未删除状态，并解析真实 `sheet_object_key`；任何客户端直传 `character_sheet`
都拒绝。所有权读事务先释放，再进入扣费和入队 Saga。

## 6. Web 与验收

开启本地 flags 后，`/characters` 提供创建、状态轮询、重试、重命名、软删除和
预览。统一工作台的“文生视频”可清空人物选择：无人物提交 `ltx_t2v`；有人物
自动提交 `ltx_t2v_ic` 并锁定规格和价格。视觉 prompt 与可选 audio prompt
分别进入任务输入，默认生成同步音频。

LAN mutation 只能通过 `scripts/lan_aio_fleet_prod_ops.py`。先核对 live、ledger、
catalog 并带原因收口 unfinished operation；状态不唯一就停止。只在当前空闲的
`gpu-252/gpu1` 顺序验证人物候选与 LTX 候选，检查 heartbeat、`/system_stats`、
`/object_info`、模型枚举、R2、音轨、时长、OOM/status 137 和三段人物一致性。
验收结束必须停止候选并恢复 `intentionally_empty`，不得开启 production intake。

本地验收固定使用事务化入口：

```bash
python scripts/lan_aio_fleet_prod_ops.py canary-start-disabled \
  --slot <slot> --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py canary-stop-disabled \
  --slot <slot> --include-disabled --execute
```

启动事务只执行 preflight、digest-pinned image、warm-cache 与 disabled heartbeat，
绝不执行 `enable-aio`；停止事务必须等待 Central worker 和 Comfy `/queue` 均空闲，
再停止候选并原子恢复 ledger 的 `intentionally_empty`。低层 `start-disabled`、手工
Docker 或成功后会开启 intake 的 `recover/takeover` 都不能用于这类验收。

代码/容器 smoke 通过不等于 LAN 全链路通过；运行结果必须单独记录。RunPod、
GHCR、autoscaler/canary 与共享环境发布属于下一阶段授权。

### 6.1 2026-07-22 LAN 运行结果

- `ltx_t2v/2026-07-22` 模型缓存与两个候选镜像的构建/registry 门禁已通过。
- PornMaster disabled 候选通过 exact digest、warm-cache、heartbeat、
  `/system_stats`、`/queue`、`/object_info` 与节点枚举；六视图 workflow 成功生成
  6 个唯一输出，并由正式 materializer 拼为 1536×896 PNG。
- 六视图完成后，`gpu-252/gpu1` 的 `GPU-8153a439-...` 先报 Xid 119
  （GSP RPC timeout），随后报 Xid 154（GPU Reset Required）。Docker 无法收到
  candidate 的退出事件，候选保持 Central disabled，但不能伪记为
  `intentionally_empty`。
- 因硬件门禁失败，LTX A/B、T2V、T2V-IC、音轨/R2 与 Web 端到端均未执行，
  本轮 LAN 全链路明确不通过。恢复必须在同机 GPU0 空闲且取得明确维护授权后，
  通过 operator 收口容器和 ledger；不得在当前状态继续启动 LTX 或启用 intake。
