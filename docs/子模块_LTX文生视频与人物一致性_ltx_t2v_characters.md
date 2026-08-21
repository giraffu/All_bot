# 子模块：LTX 10Eros 文生视频与 Licon MSR 双角色一致性

## 当前测试契约

人物参考图已升级为独立的私人人物身份素材库，由
`CHARACTER_ASSETS_ENABLED/enable_character_assets` 控制，不再跟随 LTX 开关。
四个基础视图仍是保存人物和生成 LTX 合成面板的必需项；可选
`genitals_front` 由 `CHARACTER_EXPLICIT_VIEWS_ENABLED/
enable_character_explicit_views` 单独控制，且不进入 LTX 四视图面板。

新人物必须提交性别、成年人确认和素材使用权确认。旧人物可在首次用于 H3 或补充
器官特写前完成确认；缺失性别只允许补设一次。器官特写必须以 ready 的
`body_front` 作为自由 P 图编辑输入，也可直接上传替换；生成按所选 2/3/5 灵石流程
计费并沿用失败退款，上传和保存不扣费。所有人物子图仅写私人人物库，不写
History/Gallery，也不能投稿或转为模板。

练功房的文生视频入口支持两种互斥模式：

- `ltx_t2v`：纯文字生成，不需要参考图片，1280×704，支持 5/10/15/20 秒。
- `ltx_t2v_ic`：开启“角色与环境参考”后恰好选择两个角色和一张环境图，固定
  768×448，支持 5/10/15/20 秒。

`ltx_t2v_ic` 采用社区 `runexx_msr_workflow.json` 的稳定两阶段拓扑，但主模型固定
替换为 `10Eros_v1.4_DMD_int8_convrot.safetensors`。成人生成能力来自 10Eros
checkpoint；`LTX2.3-Licon-MSR-test_version.safetensors` 只提供人物身份一致性，
不叠加 Sulphur 或其它 NSFW LoRA，也不加载 workflow 原有的 distilled LoRA。

运行链路是：

```text
10Eros v1.4 DMD
  -> Licon MSR test IC-LoRA
  -> 第一阶段 LTXAddVideoICLoRAGuide + LTXVCropGuides + sampler
  -> latent upscale
  -> 第二阶段 LTXAddVideoICLoRAGuide + LTXVCropGuides + sampler
  -> 最终 guide 裁剪、音视频输出
```

第一阶段视频 latent 为 384×224，Licon MSR 合成图必须直接按最终阶段的
768×448 生成：IC-LoRA 节点的 downscale factor 会在第一阶段将它适配到低分辨率，
latent x2 放大后第二阶段再复用原尺寸合成图。若 MSR 合成图错误地按第一阶段尺寸
生成，第二阶段 sampler 会因 guide 与 keyframe grid 长度不同而失败。
`LTXVAddGuideMulti` 还要求 KJNodes 至少包含上游
`5fc6db6b39638a692f114c4bb5b6949f801b4efa` 的 guide-attention 修复；更早版本会把
每个 guide 的 latent offset 重复计入 attention entry，并在第一阶段产生同样的
`pre_filter_counts != keyframe grid mask length` 错误。`ltx_unified` 镜像必须显式
固定该修复版本，不能继承旧 base 镜像中的 KJNodes。

gpu177 GPU1 是 compute capability 12.0 的 Blackwell 卡。当 IC workflow
传入 guide attention tensor mask 时，旧 xFormers FA/CUTLASS 内核不支持
SM120，会在首个 sampler 报 `memory_efficient_attention_forward` 无可用
operator。`ltx_unified` LAN AIO 必须通过受管 compose 参数固定
`--use-pytorch-cross-attention`；不得在 GPU 宿主机上手改 compose 或现场安装
xFormers。

三张媒体的稳定顺序是：角色参考图 1、角色参考图 2、场景背景图。LTX 使用的人物参考图是人物
图库生成的完整四视图面板；背景只定义环境、布局和光线。三者都不是视频首帧或
终帧。Worker 输入准备必须对 `character_sheets` 和 `background_image` 分别执行
对象存储下载、图片规范化和 ComfyUI input 上传，再把 workflow 的 `LoadImage`
参数替换为 ComfyUI 本地文件名；远端 object key 不得直接进入 workflow。

## 输入与授权边界

浏览器的新提交结构为：

```json
{
  "character_refs": [
    {"source": "private", "id": "character-1"},
    {"source": "official", "id": "character-2"}
  ],
  "environment_ref": {"source": "official", "id": "environment-1"}
}
```

角色可混合选择当前用户私有角色和 published 官方角色；环境在 published 官方单图
与当前任务临时上传单图之间二选一，环境不需要多视角。旧
`character_ids/background_object_key` 暂时归一化兼容。服务端在扣费前检查两个引用
不同、私有 owner、官方 published、私有 moderation active、面板有效且描述非空；
上传环境必须归属当前用户、为 PNG/JPEG/WebP 且不超过 20 MB。随后才将
角色面板、人物描述和背景 object key 写入不可变任务载荷。客户端不能直接提交面板
路径、描述、模型、LoRA 或强度。

练功房选择“上传环境”后，应在环境来源控件下直接显示单图上传按钮；该入口复用
通用预签名上传链路，最多保留一张环境图。纯 T2V 与“官方环境”模式不显示该按钮。

纯 T2V 不能携带角色或背景；IC 模式不能少于或多于两个角色，也不能缺少背景。
这些限制由前端体验层、Web submission service、domain config 和 Worker patcher
重复校验，任何不一致都 fail closed。

## Workflow 与模型事实源

- task/profile 映射：`src/domain_config/task_type_registry.py`、
  `ops/gpu_pool_controller/config/task_profiles.yml`
- 输入规范：`src/domain_config/ltx_t2v.py`
- Web owner fence：`src/web_api/services/task_submission_service.py`
- patcher：`workers/comfy_agent/workflow_task_patchers.py` 与 RunPod 镜像副本
- 测试 agent：`cloud_worker_test_ltx_v2_01`，只消费
  `ltx_video_v2,ltx_video_v2_flf2v,ltx_t2v,ltx_t2v_ic`
- workflow：`workers/comfy_agent/workflows/LTX 2.3 Sulphur T2V.json`
- 模型 manifest 构建：`scripts/prepare_ltx_unified_model_bundle.py`

`ltx_unified` 的构建 base 必须引用 GHCR canonical `ltx_t2v` 精确 digest，使
`allbot-sgp1` 云构建器可独立解析；LAN registry 只接收构建完成后的保摘要镜像，不能
反向作为 canonical Dockerfile base。

虽然 workflow 文件名为历史名称，当前 `ltx_t2v_ic` patcher 会替换模型节点并移除
旧 distilled/LoRA 链；运行时语义以 patcher focused tests 和最终 API workflow 为准。

模型校验：

- 10Eros v1.4 DMD：29,161,842,398 bytes，SHA256
  `dc7b2809eb349f26aada43e40d140d778b8025d0f94550c97912b022222b8f81`
- Licon MSR test IC-LoRA：805,412,808 bytes，SHA256
  `51121a7e9d9579734943db1ebf89df12592ef7e6cdda460eca4f9ab8ef989859`

模型必须通过 `ltx_unified` manifest 校验与 LAN cache 预热进入 gpu177 GPU1。禁止
现场复制未校验模型、自由 compose 或修改正式 runtime。若运行中的 Comfy 无法热
发现新增模型，停止 canary 并申请维护窗口，不主动重启共享正式 runtime。

## Prompt Optimizer

文生视频以 `ltx_scene_script_cinematic@4` 作为兼容默认基线，并按场景读取管理后台
当前配置：

- `ltx_eros_t2v@1` 不带媒体；
- `ltx_eros_t2v_ic_msr@1` 固定
  `reference_character_1/reference_character_2/scene_background`；
- 最终只输出英文 `positive_prompt`，规则正文在服务端版本化且不暴露给客户端；
- `ltx_t2v_ic` 的配置必须引用人物描述、环境描述和媒体语义变量；新任务保存渲染后
  snapshot/revision/hash，配置保存不会改变运行中任务；
- 使用现有 `prompt_optimize`、1 灵石、单用户并发 1、四 lane、24 小时文本结果和
  `text_delta` 流式预览契约；最终结构化 JSON 验证仍是唯一成功依据。

发布顺序保持 Worker-first、Web-activation-last。旧 @3 图生视频模板继续只兼容
I2V/FLF2V，@4 不得用于首帧任务。

## 官方素材与管理边界

官方角色使用独立表和 `draft/ready/published/archived` 生命周期，固定正脸、全身正面、
全身侧面、全身背面四槽，可混合上传/生成；全部 ready 后合成 1536×896 白底面板才可
发布。官方环境是一张目标场景图，可上传或文生图生成，不制作多视角。管理端生成使用
`dashboard:official-assets` operator、cost=0、不写 History/Gallery，但仍走任务终态、
失败和素材回写。管理员只能停用/恢复用户私有角色，不能编辑或转为官方。

## 最小验证

```bash
.venv/bin/python -m pytest -q \
  tests/config/test_ltx_t2v.py \
  tests/web_api/test_ltx_t2v_submission.py \
  tests/workers/test_workflow_patcher.py \
  tests/prompt_optimizer/test_registry.py \
  tests/web_api/test_prompt_optimizations.py \
  tests/scripts/test_prepare_ltx_unified_model_bundle.py
```

前端至少验证纯 T2V、恰好两个角色加背景、@4 capability、流式替换与失败退款；
GPU canary 至少覆盖 5/10/15/20 秒的节点补丁，并在真实环境完成一组短视频后再开放
测试 flag。
