# 子模块：LTX 2.3 Sulphur 文生视频与 Ingredients 人物一致性

## 1. 范围与发布状态

本能力使用独立执行 profile `ltx_t2v`，不会替换现有 `ltx_video` / 10Eros
图生视频。它包含三个用户任务：

- `ltx_t2v`：纯文生同步音视频；
- `ltx_t2v_ic`：文生同步音视频 + 私有人物参考表 + Ingredients；
- `character_reference_build`：从本人上传源图生成一个指定人物视角；旧版一次生成
  六图的调用仍只作兼容。

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
同步音频输出；T2V 是 `1280x704`，IC 是 `768x448`，交付规格均为
`24 * seconds + 1` 帧、24fps。IC 支持 5/10/15/20 秒。人物参考表只作隐藏条件：
workflow 在请求时长之外额外生成一秒并把 guide 固定在尾端，统一结果物化层在上传
前重编码裁掉该一秒。裁剪、AAC 音轨或输出生成失败必须 fail closed，禁止回退上传
含参考表的原 MP4；fallback last frame 只能从裁剪后的交付 MP4 提取。
候选 ComfyUI 使用 `--reserve-vram 5`。

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

`character_references` 记录 UUID、owner、名称/描述、源图 key、最终参考表 key、
兼容任务 ID、状态与时间戳；`character_reference_views` 以
`(character_id, view_type)` 唯一保存每张子图的可编辑 prompt、task ID、object
key 与终态。资产只能由 owner 访问，不可投稿；每人最多保留 20 个 `draft/ready`
人物，子图生成仍受普通任务并发限制。

`POST /api/characters/drafts` 只接受当前用户
`web_uploads/{internal_user_id}/...` 下不超过 20 MiB 的 PNG/JPEG/WebP，创建草稿
不扣费。用户按需对下列固定槽位调用子图生成接口：

1. 正脸图；2. 侧脸图；3. 3/4 侧脸图；
4. 全身正面图；5. 全身侧面图；6. 全身背面图。

每个子图都是独立 `character_reference_build` 任务。控制面传
`character_view_index/type` 和该槽位 prompt；worker 在既有六分支 workflow 中
删除其余五个分支，把所选分支切换到 BF16 V4 UNET，并只物化所选输出。该执行
类型属于 `pornmaster_flux2_edit_bf16` 共享容量池，RunPod/LAN profile 必须显式
声明它且使用对应 BF16 模型 manifest；无 index 的旧六图兼容任务仍保留 FP8
workflow 模型。子任务保持私有，`record_history=false`，
不会污染闪回瓶，也不允许投稿。旧 `POST /api/characters/build` 与无
`character_view_index` 的 worker 路径继续保留一次六图兼容语义。

单张正面半身源图是受支持且必须覆盖的验收输入，但它不意味着六格都可以复制
正面半身构图。materializer 使用视觉感知差异门禁拒绝近似重复视图，但不把该门禁
冒充姿态语义识别；真实 canary 仍须
人工确认至少正面、3/4、侧面、背面和景别变化均成立。参考表、拼贴边框或任一格
不得出现在交付视频首帧、尾帧或场景切换附近。

至少两个子图为 `ready` 后，`POST /api/characters/{id}/save` 才允许保存。服务端
按固定 3×2 槽位合成 `1536x896` PNG；未生成的槽位保持纯黑，因此不同数量和重试
顺序不会改变视角位置。人物图库可选择已有子图修改 prompt 后重新生成，再显式
“更新人物参考图”重建合成表。

每个已完成视图统一复用 QQCC AI 动图的
`shared.image_aspect.adapt_image_to_aspect`：比例变化不安全或没有可靠焦点检测时，
使用模糊背景填充并完整缩放前景，再等比落到 `512x448`；禁止另写居中 cover
裁剪。竖幅人物必须完整保留头顶与脚部，六个格子再按固定 3x2 顺序拼接。
`src.services.smart_image_aspect_service` 只保留兼容 facade，控制面与
`workers/runpod_runtime` 的比例安全策略以 `shared/image_aspect.py` 为唯一事实源。
人物子图 patcher 与 materializer 由 PornMaster profile 在共享 RunPod runtime
之上显式 overlay；不得把人物专属实现写回共享 runtime 并误触发全部 GPU profile
重建。PornMaster 人物构建镜像还必须显式打包共享图片模块，目录迁移后的真实
RunPod runtime 测试必须覆盖极端竖图，防止旧 `ImageOps.fit` 回归。修复后的
artifact 和新人物表未完成 canary 前，旧参考表不得作为 IC 人物一致性验收证据。

终态 finalizer 通过子图 task ID 幂等回写 `ready/failed` 与 object key；旧版任务
仍回写人物主记录。失败、取消或入队失败使用现有 Saga 幂等退款。

## 5. API、计费与所有权

人物 API 为：

- `POST /api/characters/drafts`：创建免费草稿；
- `POST /api/characters/{id}/views/{view_type}/generate`：生成或重生一个子图；
- `POST /api/characters/{id}/save`：至少两个 ready 子图后合成/更新参考表；
- `GET /api/characters`、`PATCH /api/characters/{id}`、
  `DELETE /api/characters/{id}`：列表、改名/描述与软删除；
- `POST /api/characters/build`：旧版一次六图兼容入口。

pending 子图存在时删除返回 409。

视频仍走 `POST /api/tasks/generate`：

- `ltx_t2v`：5/10/15/20 秒分别 10/20/30/40 灵石；
- `ltx_t2v_ic`：5/10/15/20 秒分别 12/24/36/48 灵石；
- 人物子图：每张 3 灵石，最多六张合计 18 灵石；重生同样按张计费。

IC 客户端只能提交 `character_id`。服务端在扣费前验证 owner、`ready` 状态和
未删除状态，并解析真实 `sheet_object_key`；任何客户端直传 `character_sheet`
都拒绝。所有权读事务先释放，再进入扣费和入队 Saga。

## 6. Web 与验收

测试 Web 发布后，“练功房 → 人物参考图”提供上传、六个子图 tab、各槽位默认
prompt 编辑、独立生成/重生、状态轮询和至少两图保存。“修仙笔记 → 人物图库”
提供合成表与六子图查看、选择子图重生和重新合成；旧 `/characters` 只重定向到
该 tab，不再保留独立人物页。统一工作台的“文生视频”可清空人物选择：无人物提交
`ltx_t2v`；有人物自动提交 `ltx_t2v_ic` 并锁定规格和价格。视觉 prompt 与可选
audio prompt 分别进入任务输入，默认生成同步音频。

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

本轮 IC 黄金用例固定从一张隔离的亚洲成年人物正面半身照开始：先生成并检查六种
语义视图，再提交 20 秒 `ltx_t2v_ic`。prompt 明确 0–5、5–10、10–15、15–20 秒
四个场景并在 5/10/15 秒切换。验收下载首帧、各切换点前后帧和尾帧，确认同一亚洲
成年人五官、发型、年龄与服装连续，同时任何帧均不出现 3×2 参考表、分屏或拼贴。
还须用 ffprobe 核对 768×448、24fps、AAC、约 20 秒且无 OOM/status 137。

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
