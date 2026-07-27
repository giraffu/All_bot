# 子模块：LTX 2.3 Sulphur 文生视频与 Ingredients 人物一致性

## 1. 范围与发布状态

本能力使用独立执行 profile `ltx_t2v`，不会替换现有 `ltx_video` / 10Eros
图生视频。它包含三个用户任务：

- `ltx_t2v`：纯文生同步音视频；
- `ltx_t2v_ic`：文生同步音视频 + 私有人物参考表 + Ingredients；
- `character_reference_build`：从本人上传源图生成六视图参考表。

本阶段允许已授权的 cloud-test disabled canary、测试 Web 人工验收，并继续支持
本地 LAN 验收。后端 `LTX_T2V_BACKEND_ENABLED` 默认关闭，由云测试环境显式开启；
Web runtime flag `enable_ltx_t2v` 只在 test 为 `true`，prod 固定为 `false`。
不得开放正式用户、未经单次授权创建正式 Pod 或启用 autoscaler。RunPod 使用独立
`ltx_t2v` profile，只接受 `ltx_t2v,ltx_t2v_ic`，禁止 template，首轮只接受
32GB RTX 5090；不得把本地 registry 镜像当作 GHCR artifact。

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

cloud-test 的 R2 bundle 固定为 `ltx_t2v/2026-07-22/manifest.json`。临时
model-transfer Pod 只可直传公开的 dev FP8 与 Sulphur 两个大文件，Ingredients
及复用文件必须从本地已校验 content-addressed registry 上传；任何 gated
凭据不得进入 Pod、batch 或日志。10/10 对象通过 size、SHA256 metadata 与 HEAD
之前不得发布 manifest，失败后必须清理 Pod 和 multipart upload。

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

`workers/runpod_runtime/` 保持镜像内副本同步。两张 LTX 图均为 API-format、双阶段、
同步音频输出；T2V 是 `1280x704` 和 `24 * seconds + 1` 帧，IC 第一版锁定
`768x448 / 121 frames / 24fps`。候选 ComfyUI 使用 `--reserve-vram 5`。

四组有序 LAN A/B 图位于
`ops/gpu_pool_controller/validation_workflows/ltx_t2v/`。第 1/3 组只是官方
baseline；只有第 2 组完整 Sulphur T2V 和第 4 组完整 Sulphur + Ingredients
均产出可播放、带音轨 MP4，目标栈才通过。

镜像入口：

- RunPod：`workers/runpod_profiles/ltx_t2v/Dockerfile`，发布为
  `gpu-execution` 的 `allbot-gpu-ltx-t2v` 不可变 artifact；镜像必须核对 OCI
  revision、agent、两份 workflow、46 节点和 Ingredients loader/guide，并拒绝
  baked 模型权重。
- 创建请求固定 baked entrypoint、`media_claim2_comfy1_delivery1_v1`、
  `containerDiskInGb=180`、volume 至少 100GB、固定模型 manifest 和单一 5090。
- `runpod canary --task-type ltx_t2v` 创建的 cloud-test worker 以 disabled
  control 进入，只在串行普通 Sulphur 与 Ingredients canary 期间临时 enabled，
  结束后再次 disabled、drain 并删除。本节描述已实现的 operator 契约；真实
  RunPod 黄金路径证据须以 main 同 SHA artifact 与本机 XDG state 为准。
- Dashboard 的手动 RunPod 管理列表登记 `ltx_t2v / Sulphur + Ingredients`；
  新建后仍默认 disabled，可执行开启、暂停、重启、锁定和删除。该入口只登记
  正式手动池能力，不代表获准创建正式 Pod，且该 profile 不进入 autoscaler。

- `workers/runpod_profiles/ltx_t2v/Dockerfile`；
- `workers/runpod_profiles/pornmaster_flux2_edit/Dockerfile`。

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
然后用 Pillow 按以下顺序确定性拼成 `1536x896` PNG：

1. 正脸近照；2. 3/4 脸；3. 正面半身；
4. 全身正面；5. 全身侧面；6. 全身背面。

每个视图统一复用 QQCC AI 动图的
`shared.image_aspect.adapt_image_to_aspect`：比例变化不安全或没有可靠焦点检测时，
使用模糊背景填充并完整缩放前景，再等比落到 `512x448`；禁止另写居中 cover
裁剪。竖幅人物必须完整保留头顶与脚部，六个格子再按固定 3x2 顺序拼接。
`src.services.smart_image_aspect_service` 只保留兼容 facade，控制面与
`workers/runpod_runtime` 的比例安全策略以 `shared/image_aspect.py` 为唯一事实源。
PornMaster 人物构建镜像必须显式打包该共享模块，目录迁移后的真实 RunPod runtime
测试必须覆盖极端竖图，防止旧 `ImageOps.fit` 回归。修复后的 artifact 和新人物表
未完成 canary 前，旧参考表不得作为 IC 人物一致性验收证据。

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

测试 Web 发布后，`/characters` 提供创建、状态轮询、重试、重命名、软删除和
预览。统一工作台的“文生视频”可清空人物选择：无人物提交 `ltx_t2v`；有人物
自动提交 `ltx_t2v_ic` 并锁定规格和价格。视觉 prompt 与可选 audio prompt
分别进入任务输入，默认生成同步音频。

LAN mutation 只能通过 `scripts/lan_aio_fleet_prod_ops.py`。先核对 live、ledger、
catalog 并带原因收口 unfinished operation；状态不唯一就停止。只在明确授权的
空闲物理槽顺序验证人物候选与 LTX 候选，检查 heartbeat、`/system_stats`、
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

代码/容器 smoke 通过不等于 LAN 或 RunPod 全链路通过；运行结果必须单独记录。
cloud-test RunPod canary 与测试 Web 人工验收已支持；生产 Web、正式 RunPod 和
autoscaler 仍属于单独授权边界。

测试人工验收使用同一套发布和任务链，不增加旁路：

1. main 同 SHA 的 control-plane/public-web 发布到 test；
2. 云测试 host 显式设置 `LTX_T2V_BACKEND_ENABLED=true`，prod 保持默认 false；
3. 通过专用 operator 创建 `runpod_test_ltx_t2v_*`，确认 disabled heartbeat 后
   人工 enable；不得用 Dashboard 的正式手动池命令创建测试 Pod；
4. 从 `https://web-cf-test.aivison.it.com` 登录，分别提交普通 T2V、创建人物参考表
   和 IC T2V；任务必须由目标测试 agent 接取并回流 `user-data-test`；
5. 人工测试结束后 disable、drain、删除测试 Pod，并确认 Central 无活动任务。

### 6.1 2026-07-22 LAN 运行结果

- `ltx_t2v/2026-07-22` 模型缓存与两个候选镜像的构建/registry 门禁已通过。
- PornMaster disabled 候选通过 exact digest、warm-cache、heartbeat、
  `/system_stats`、`/queue`、`/object_info` 与节点枚举；六视图 workflow 成功生成
  6 个唯一输出，并由正式 materializer 拼为 1536×896 PNG。
- 六视图完成后，`gpu-252/gpu1` 的 `GPU-8153a439-...` 先报 Xid 119
  （GSP RPC timeout），随后报 Xid 154（GPU Reset Required）。Docker 无法收到
  candidate 的退出事件。用户重启主机后已通过 operator 收口该槽；GPU1 继续
  硬件隔离，不参与后续验收。
- 用户明确授权后，GPU0 `GPU-09b7ea85-...` 先完成同一六视图/1536×896 人物表，
  再运行 LTX disabled candidate。10 个模型文件共约 62GB 全部通过 manifest
  size/SHA；最终镜像固定为
  `sha256:9ed3de73923fc8f021716f7fc19d8d3e5f6ed552a8ee11cb849b3dfb293db043`，
  OCI revision 为 `2f0a7459...`，46/46 workflow 节点和模型枚举齐全。
- 运行反馈环修复两项真实问题：LAN compose 必须从镜像内 `/opt/ComfyUI` 启动并
  单独挂载持久模型目录；工作流固定 x2 upscaler 前必须使用半尺寸 latent，
  Ingredients guide latent 必须在空间放大前裁剪，否则会输出 129 帧。最终 T2V
  为 1280×704，T2V-IC 为 768×448/121 帧，均为 24fps、约 5.04 秒并含 AAC。
- 四组 A/B 均生成可播放音视频；硬门禁第 2 组 Sulphur T2V 与第 4 组
  Sulphur + Ingredients 都通过。成人 NSFW T2V 抽帧确认无审查遮挡；同一人物表
  的美术馆、植物园、夜间城市三场景在脸、发型、红黑服装、体型和配件上保持
  一致。运行期间没有 OOM、任务中 status 137 或新 Xid/NVRM。
- 最终 `canary-stop-disabled` operation 为
  `20260722T133455Z-canary_stop_disabled-db3b9380`；GPU0/GPU1 的 live 与 ledger
  都恢复 `intentionally_empty`，production intake 从未开启。Web 代码、组件测试
  和构建门禁通过；Playwright 在独立本地进程开启 flag，以内存 API
  拦截完成了选图→预签名上传→建人物→ready 刷新→选人物→提交 IC，
  并断言最终 payload 为 `ltx_t2v_ic`/768×448/5 秒、只传 `character_id`。
  桌面/移动端截图保存在
  `/home/hfy/.local/state/allbot/lan-aio/evidence/2026-07-22-ltx-t2v-web/`；该验收
  证明 Web 交互链，但不等于真实 Central/账本/队列的隔离环境 E2E。
