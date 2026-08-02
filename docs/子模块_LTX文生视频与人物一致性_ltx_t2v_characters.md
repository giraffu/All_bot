# 子模块：LTX 2.3 Sulphur 文生视频与 Ingredients 人物一致性

## 1. 范围与发布状态

本能力使用独立执行 profile `ltx_t2v`，不会替换现有 `ltx_video` / 10Eros
图生视频。它包含三个用户任务：

- `ltx_t2v`：纯文生同步音视频；
- `ltx_t2v_ic`：文生同步音视频 + 私有人物参考表 + Ingredients；
- 人物子图：从本人上传源图生成一个指定人物视角，复用普通自由 P 图、自由 P 图
  v2.5 或自由 P 图 v3 任务链；`character_reference_build` 只保留旧版一次生成
  六图的兼容调用。

本阶段允许已授权的 cloud-test disabled canary、测试 Web 人工验收，并继续支持
本地 LAN 验收。后端 `LTX_T2V_BACKEND_ENABLED` 默认关闭，由云测试环境显式开启；
Web runtime flag `enable_ltx_t2v` 只在 test 为 `true`，prod 固定为 `false`。
关闭时，练功房不展示“人物参考图”和“文生视频”，修仙笔记不展示
“人物图库”，并且前端不注册人物图库路由；直接访问旧入口也不能绕过
Web API 的 backend flag。
不得开放正式用户、未经单次授权创建正式 Pod 或启用 autoscaler。RunPod 使用独立
`ltx_t2v` profile，只接受 `ltx_t2v,ltx_t2v_ic`，禁止 template，首轮只接受
32GB RTX 5090；不得把本地 registry 镜像当作 GHCR artifact。

LAN 可使用 `ltx_unified` 作为执行层聚合 profile，同时承接三类 `ltx_video`
和两类 `ltx_t2v`。这不合并用户侧逻辑 profile、计费、路由、公共开关或
RunPod 容量：`ltx_t2v` 在 prod 仍默认关闭，只允许 operator canary 通道提交。
统一 profile 的模型事实源是
`ltx_unified/2026-08-01-comfy-fast/manifest.json`，其中 Sulphur、Ingredients 与 extracted
10Eros LoRA 是独立分支资产，公共 CLIP/VAE/upscaler 只引用一次。
LAN-only `all` profile 的 LTX 子栈也复用这份统一 manifest：它保留其它任务的
五份 manifest，只用统一 LTX manifest 替换原先分别声明的 `ltx_video` 与
`ltx_t2v` manifest；内容寻址同步不会重复下载相同模型。三类 LTX 视频映射到
extracted-10Eros workflow，T2V/IC 继续映射到 Sulphur/Ingredients workflow。

## 2. 固定模型栈

模型 bundle 为 `ltx_t2v_runtime/2026-08-01-comfy-fast`，LAN model-cache 前缀为
`ltx_t2v/2026-08-01-comfy-fast`。普通 T2V 和 IC 使用各自的官方基座，两个任务分支
固定为：

1. 官方 `ltx-2.3-22b-dev-fp8.safetensors`；
2. 官方 distilled LoRA，强度 `0.5`；
3. 普通 `ltx_t2v` 追加 Sulphur rank-768 LoRA，强度 `1.0`；
4. `ltx_t2v_ic` 与官方 ComfyUI 快速模板一致：使用
   `ltx-2.3-22b-distilled-fp8.safetensors` checkpoint、
   `gemma_3_12B_it_fp4_mixed.safetensors` 和 Ingredients 0.9 `1.0`；不再加载
   dev checkpoint 或 distilled LoRA，不叠加 Sulphur，也不能以
   `ltx2310eros_v1` 作为底模；
   普通 `ltx_t2v` 继续保留 Sulphur，Ingredients + Sulphur 只保留隔离 A/B 图，
   不进入用户工作流。

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

脚本在下载前要求 registry 同文件系统至少 115 GiB 可用空间，流式写临时文件，
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

`--target ltx_t2v` 只构建 `ltx_t2v/2026-08-01-comfy-fast/manifest.json`，模型对象使用
`models/by-sha256/<sha[:2]>/<sha>`；manifest 只有在全部对象 HEAD 的大小和 SHA
metadata 都通过后才发布。

cloud-test 的 R2 bundle 固定为 `ltx_t2v/2026-08-01-comfy-fast/manifest.json`。临时
model-transfer Pod 只可直传公开的 dev FP8、distilled FP8 checkpoint、
FP4 Gemma 与 Sulphur，Ingredients
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

`workers/runpod_runtime/` 保持镜像内副本同步。两张 LTX 图均为 API-format
同步音频输出；T2V 是 `1280x704` 双阶段，IC 是 `768x448` 单阶段，交付规格
均为 `24 * seconds + 1` 帧、24fps。IC 支持 5/10/15/20 秒；Web 选择人物后只锁定
IC 的 768×448 分辨率，时长仍可编辑，费用随四档时长按领域配置计算。

IC workflow 是从 ComfyUI 官方 Ingredients 快速模板重新生成的干净 API 图，
只保留可达的推理与交付节点，不包含 NAG、第二阶段、latent upscaler、switch、
chunk feed-forward 或 preview override。worker 将单一人物 ingredient 面板保持
宽高比缩放到短边 448，并以缩放后的实际宽高驱动输出 latent；标准 1536×896
面板仍得到 768×448。随后用 `RepeatImageBatch` 复制成与输出完全同帧数
（`24 * seconds + 1`）的静态参考视频；`GetICLoRAParameters` 从 Ingredients
LoRA 读取 guide 参数，该视频在 `frame_idx=0` 通过 `LTXVAddGuide`
接入。`LTXVImgToVideoInplace` 明确 `bypass=true`，因此人物表不是可见首帧；
采样后的 `LTXVCropGuides` 删除追加的 guide latent，再由标准
`VAEDecodeTiled` 解码；交付结果无需添加保护尾段，也不经二次转码裁尾。
采样固定使用标准 `KSampler`、8 steps、CFG 1、`euler_ancestral`、
`linear_quadratic`、denoise 1。
Web 可传入非负 `seed` 复现固定种子任务；该字段必须经过 task dispatcher、
Web API client 与 Central `LtxT2VRequest` 原样进入 Worker。未指定时 Worker 只生成
一次合法的非负随机种子，并写入普通 T2V 的 `Seed (rgthree)` 或 IC 的
`KSampler.seed`；workflow 模板中的 `-1` 不得提交给 ComfyUI。

IC prompt 按官方可执行 workflow 的标题由 worker 组合为
`### Reference Sheet Description` 与 `### Target Description` 两段：前者使用人物资产中
必填的稳定外观描述，并规范化为 `Left Panel (Character Face)` 与
`Right Panel (Character Turnaround)` 两个训练子标题；人物身份文字中的
background/panel/参考图等布局句在组合时移除，避免目标 latent 把参考表布局当作场景。
后者原样承载用户场景。人物描述由服务端按 owner 和
`character_id` 读取，客户端不能为一次视频任务覆盖它。
缺失的用户负向提示按空字符串处理，禁止把 Python `None` 编入 conditioning；
Ingredients 基线负向固定为
`worst quality, inconsistent motion, blurry, jittery, distorted`；不默认追加与
reference-sheet 训练语义冲突的 grid/collage/character-sheet 排除词。可选音频描述
作为第三段继续追加为 `#Audio`。
候选 ComfyUI 使用 `--reserve-vram 5`。

四组有序 LAN A/B 图位于
`ops/gpu_pool_controller/validation_workflows/ltx_t2v/`。第 1 组是普通官方
baseline，第 4 组只保留历史 A/B 比较；第 2 组 Sulphur T2V 和第 3 组官方
distilled + Ingredients 均产出可播放、带音轨 MP4，当前目标栈才通过。
第 3/4 组人物 A/B 必须通过 `scripts/ltx_t2v_ic_ab_smoke.py` 在 intake disabled
的单槽运行：patcher 对第 3 组保持 `checkpoint → Ingredients`，只在第 4 组存在且
严格匹配固定节点 `258` 时保留 `checkpoint → Sulphur 1.0 → Ingredients 1.0`；
节点缺失或模型名、强度、输入链不符时 fail closed。runner 只把 workflow checksum、
种子、时长、Comfy prompt ID、媒体规格和 GPU 遥测写入 XDG evidence，不持久化人物
描述、场景提示词、私有 object key 或签名 URL。通过该 A/B 也不能修改用户侧
`ltx_t2v_ic` mapping，是否增加测试 Web 实验选项必须另行决策。

MSR V2 只存在于隔离验证栈。`scripts/ltx_t2v_msr_ab_smoke.py` 固定生成 4 个
5 秒样本：官方 Ingredients、MSR V2、MSR V2 + Sulphur 0.25、MSR V2 +
Sulphur 0.5。MSR 读取正脸、全身正面、侧面、背面 4 张原始白底图，使用纯白
空图满足其 background 输入，不复用 Ingredients 合成表；四组保持提示词、种子、
负向词、分辨率与时长一致。`ComfyUI-Licon-MSR` 固定 revision
`94a52bfec735ff6f802c480f7fe8fdac1d279a7f`，V2 LoRA 固定 revision
`593b0b7d2b912e8ecdb2825a34732cee36e720ba` 和 SHA256
`6f61d3b5c61b160c409b45ebaa72fd7ab9bb38bf3bf7f09edaddc87762d5fa98`。
该栈不得进入公共 workflow patcher、task type、Web 参数或计费映射；验证通过也
只能支持下一轮测试环境选项评估。

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

`character_references` 记录 UUID、owner、名称、必填人物描述、源图 key、最终参考表 key、
兼容任务 ID、状态与时间戳；`character_reference_views` 以
`(character_id, view_type)` 唯一保存每张子图的可编辑 prompt、task ID、object
key 与终态。资产只能由 owner 访问，不可投稿；每人最多保留 20 个 `draft/ready`
人物，子图生成仍受普通任务并发限制。

`POST /api/characters/drafts` 只接受当前用户
`web_uploads/{internal_user_id}/...` 下不超过 20 MiB 的 PNG/JPEG/WebP，创建草稿
不扣费；名称和人物描述均为必填，人物描述最多 500 字。用户按需处理四个官方面板固定槽位：正脸图、全身正面图、全身侧面图、
全身背面图。服务端目录是默认提示词事实源；四条默认词均使用中文，要求同一位
成年人、完全裸体、单一人物、纯白背景和明确视角，不再保留侧脸近景与 3/4 侧脸
槽位。API presenter 会把数据库中完全等于旧版黑底默认词的历史 prompt 映射为
对应白底默认词，使现有角色刷新后可直接重生；用户自行编辑过的黑底提示保持原样。
练功房 `CharacterReferenceWorkbench` 的新草稿占位词必须与服务端四条白底默认词
保持一致，不能在前端重复保留旧黑底词。

每个子图都是独立的标准生成任务。`POST
/api/characters/{id}/views/{view_type}/generate` 接受 `engine=free_edit |
free_edit_v2_5 | free_edit_v3`，分别提交既有 `edit`、`free_edit_v2_5`、
`pornmaster_flux2_edit_bf16` 业务类型，沿用各自价格、worker pool、workflow
与退款语义；v3 仍执行 Web 的 BF16 → `face_swap_v2` continuation。人物
`character_id/view_type` 只作为终态 metadata，在最终结果落地后回写对应子图，
不得改变 worker execution type。子任务保持私有，`record_history=false`，
不会污染闪回瓶，也不允许投稿；前端把返回的根 task ID 登记到统一任务 store，
因此与普通生成任务一样显示悬浮球、状态和取消入口。

每个槽位也可调用 `POST /api/characters/{id}/views/{view_type}/upload` 直接写入
当前用户已上传的 PNG/JPEG/WebP。服务端再次验证 owner、扩展名、存在性和 20 MiB
上限，再复制到人物持久目录并把该槽位置为 `ready`；直传不创建生成任务、不扣费、
不显示悬浮任务。正在生成的同一槽位拒绝覆盖，生成与直传结果可以混合组成面板。

练功房支持批量生成当前草稿中尚未生成或已失败的子图，已 `ready/pending` 的
槽位不会重复提交。前端每轮读取 `GET /api/characters/batch-capacity` 返回的
后端权威 `limit/active/available`，只补满实时可用任务锁；没有槽位时等待已有
任务终态释放锁，再继续逐张调用原单图生成接口。该调度不创建新的批量业务任务，
不合并 task ID/扣费/退款，也不从固定最多 3 个的悬浮任务球数量推断并发上限。

旧 `POST /api/characters/build`、`character_reference_build` workflow、
`character_view_index` patcher 和结果物化只保留一次六图兼容语义；新子图入口
不得再路由到该专用 worker type。

单张正面半身源图是受支持且必须覆盖的验收输入，但四个槽位不得复制同一正面
半身构图。真实 canary 仍须人工确认正脸与全身正面、侧面、背面及景别变化均成立。
完整参考面板用于官方
Ingredients 静态参考视频条件，但参考表、拼贴边框或任一格不得出现在交付视频
首帧、尾帧或场景切换附近。

四个固定槽位全部为 `ready` 后，`POST /api/characters/{id}/save` 才允许保存。服务端
通过 `shared/character_reference_sheet.py` 合成
`ingredients-character-panel-v3.png`：优先选择正脸作为左侧大幅身份锚点，右侧
依次放置全身正面、侧面和背面。多张人物素材属于一个 character ingredient，
禁止再输出六个等权场景面板，否则模型可能把它解释为多人物或直接复现参考表。
面板画布和 contain 补边固定为纯白色；v2 黑底面板必须重新保存为 v3 后才能用于
IC 视频，避免黑色舞台语义把多个视角解释为多个同时出现的人物。
人物图库可选择已有子图修改 prompt 后重新生成，再显式“更新人物参考图”重建面板；
旧参考表不再惰性迁移，非当前面板版本会要求用户重新完成四张子图并保存。
身体视图对横幅输入只居中裁掉空白两侧，对竖幅输入完整 contain，必须保留头顶和
脚部。控制面、共享 worker 与 `workers/runpod_runtime` 复用同一合成函数。
共享 RunPod runtime 保留人物单子图裁枝与物化兼容逻辑；只有实际声明
`character_reference_build` 的 PornMaster BF16 profile 通过 profile 内 installer
把选中分支切换到 BF16 checkpoint。installer、Dockerfile 或人物任务契约变化只重建
该 profile，不得修改共享镜像构建脚本并误触发全部 GPU profile。PornMaster 人物构建
镜像还必须显式打包共享图片模块，目录迁移后的真实 RunPod runtime 测试必须覆盖极端
竖图，防止旧 `ImageOps.fit` 回归。修复后的 artifact 和新人物表未完成 canary 前，
旧参考表不得作为 IC 人物一致性验收证据。

终态 finalizer 通过子图 task ID 幂等回写 `ready/failed` 与 object key；旧版任务
仍回写人物主记录。失败、取消或入队失败使用现有 Saga 幂等退款。

## 5. API、计费与所有权

人物 API 为：

- `POST /api/characters/drafts`：创建免费草稿；
- `GET /api/characters/batch-capacity`：只读返回当前用户任务锁的
  `limit/active/available`；
- `POST /api/characters/{id}/views/{view_type}/generate`：生成或重生一个子图；
- `POST /api/characters/{id}/views/{view_type}/upload`：直接上传并完成一个槽位；
- `POST /api/characters/{id}/save`：四个固定槽位全部 ready 后合成/更新参考表；
- `GET /api/characters`、`PATCH /api/characters/{id}`、
  `DELETE /api/characters/{id}`：列表、改名/描述与软删除；
- `POST /api/characters/build`：旧版一次六图兼容入口。

pending 子图存在时删除返回 409。

视频仍走 `POST /api/tasks/generate`：

- `ltx_t2v`：5/10/15/20 秒分别 10/20/30/40 灵石；
- `ltx_t2v_ic`：5/10/15/20 秒分别 12/24/36/48 灵石；
- 人物子图与重生按所选标准流程计费：自由 P 图 2 灵石、自由 P 图 v2.5
  3 灵石、自由 P 图 v3 5 灵石；失败沿用根任务幂等退款。

IC 客户端只能提交 `character_id`。服务端在扣费前验证 owner、`ready` 状态和
未删除状态，并解析真实 `sheet_object_key` 与非空人物描述；legacy 人物缺少描述时
要求先在人物图库补充。任何客户端直传 `character_sheet`
都拒绝。所有权读事务先释放，再进入扣费和入队 Saga。

## 6. Web 与验收

测试 Web 发布后，“练功房 → 人物参考图”提供源图上传、四个子图 tab、中文裸体
默认 prompt 编辑、自由 P 图三模式选择、独立生成/重生、单槽位直接上传、按实时
并发锁补位的未生成子图批量提交、统一悬浮球状态和四图齐全后保存。
“修仙笔记 → 人物图库”提供合成表与四子图查看、同样的三模式重生和重新合成。
每张人物卡直接提供资料编辑与删除入口：资料编辑复用
`PATCH /api/characters/{id}` 修改名称和必填描述，不触发生成或扣费；删除必须二次
确认并复用 `DELETE /api/characters/{id}` 软删除，删除后从人物图库和人物选择器
中隐藏。处于 legacy 整体构建 `pending` 状态的人物不可删除。
单个子图生成会登记一个悬浮任务；`CharacterReferenceView` 的 ready/failed
持久化状态负责收口该悬浮任务。由于子图使用 `record_history=false`，通用任务
运行态清理后的 404 不是失败证据，前端必须以人物子图持久化终态纠正悬浮球。
旧 `/characters` 只重定向到该 tab，不再保留独立人物页。统一工作台的“文生视频”
可清空人物选择：无人物提交 `ltx_t2v`；有人物自动提交 `ltx_t2v_ic` 并锁定规格
和价格。练功房仍保留视觉 prompt 与可选 audio prompt 两个任务输入；服务端把
人物资产描述由 Worker 规范化为含 face/turnaround 两个面板子标题的
`### Reference Sheet Description`，视觉 prompt 作为
`### Target Description`，
可选 audio prompt 作为 `#Audio`，默认生成同步音频。

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
