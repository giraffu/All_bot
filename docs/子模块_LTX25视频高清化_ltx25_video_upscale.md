# LTX-2.5 视频高清化

## 1. 能力边界

公开任务类型和执行类型均为 `ltx25_video_upscale`。当前只接收一个最长 20 秒、
最大 40MB 的视频，统一为 24fps，并按真实媒体时长选择 `24 * 秒数 + 1` 帧的
模型网格。用户可在高于源视频长边的档位中选择 720p、1080p 或 2K，最高不超过
2K；价格按服务端核验后的整秒时长和目标档位计算，分别为 5、10、18 灵石/秒。
它的主要定位是对本项目当前 H3 beta4 生成的已定稿成片做第二次 IC V2V，
不依赖或回退到早期 beta2 模型与工作流。
它是独立 GPU profile，不替换 H3、`ltx_video`、SCAIL-2 或传统超分任务。

Web 使用练功房结构化 `target_video` 上传槽；主 Bot 使用
`menu.video_upscale` 或 `/video_upscale`。两端入口默认关闭：Web 菜单配置中的
`ltx25_video_upscale` 初始为不可见，服务端和 Bot 还要求
`LTX25_VIDEO_UPSCALE_ENABLED=true`。只有模型许可、镜像和 canary 均通过后才能
同时打开入口和执行开关。
Web 服务端在素材 promotion、扣费和 Central 派发之前通过对象存储短签与 ffprobe
读取真实视频宽、高和时长；超过 20 秒的成片直接返回明确参数错误，探测失败也
fail closed。为兼容音频封装尾部，只允许最多 20.25 秒的编码容差；计费秒数取
`ceil(真实时长 - 0.25)` 并约束到 1 至 20 秒，不能以客户端上报的 duration 或
source size 代替真实媒体校验。目标档位必须严格高于源视频长边；源视频已达到或
超过 2K 时拒绝提交。
`config-contract` 必须将该开关同时投影到 `web-api` 和 `main-bot`；
只写入宿主机总 env 但未出现在这两个容器中时，入口仍按关闭处理。

## 2. 工作流与输入契约

canonical API workflow 是
`workers/comfy_agent/workflows/LTX 2.5 IC V2V Upscale.api.json`，mapping 和
patcher 固定注入输入视频、正负提示词、seed、IC-LoRA 强度 `1.0` 和输出前缀。
Worker 在上传 ComfyUI 前通过 ffmpeg 将素材规范化为 24fps、动态帧数和 Div32
模型输入尺寸。工作流内部仍固定执行 2 倍 IC V2V，因此 Worker 会先把源视频按
比例缩放到目标档位长边的一半；最终长边分别接近 1280、1920 或 2560，短边受
Div64 输出网格约束。用户看到的是目标档位选择，不是固定的“源宽高乘 2”。无声
视频会补静音轨；最终 `CreateVideo` 复用源视频音轨，不使用采样器生成的音频作为
结果。

该 IC-LoRA 是生成式 2 倍高清化：它会合成细节，不等同于确定性像素超分。
输入应是构图和动作已经满意的干净低分辨率成片；严重压缩伪影修复不属于其
保证范围。空提示词使用“严格保持主体、身份、构图、动作和背景”的服务端默认值。

## 3. 独立 GPU profile

profile、模型包和镜像入口分别是：

- `ops/gpu_pool_controller/config/task_profiles.yml` 的 `ltx25_video_upscale`
- `ops/gpu_pool_controller/config/model_bundles.yml` 的
  `ltx25_video_upscale_runtime`
- `workers/runpod_profiles/ltx25_video_upscale/Dockerfile`
- `scripts/prepare_ltx25_video_upscale_model_bundle.py`

镜像不包含模型权重，只烘焙固定 revision 的 ComfyUI、ComfyUI-LTXVideo、Worker
runtime 和 workflow。模型 manifest 固定为
`ltx25_video_upscale/2026-08-31-int8-ic-v1/manifest.json`，五个文件合计约
39GB，全部按 size 和 SHA256 校验。基础 LTX-2.5 和 Pixel Spatial Upscaler 仓库
均需先在 Hugging Face 接受许可，再使用只读 `HF_TOKEN` 下载；token 不写入 Git、
日志或镜像。

候选 GPU 为 RTX 5090 和 RTX PRO 6000 Blackwell，容器盘至少 100GB、volume 至少
60GB。profile 默认不参加 autoscaler，首次发布必须使用 digest-pinned 镜像，先以
disabled Worker 按计划开放的时长/分辨率组合跑 canary，至少覆盖默认档和最大负载；
核对输出档位、动态帧数、音轨、显存峰值和 identity/composition 保真，再决定是否
启用接单。

云测试 canary 使用已经上传到 `user-data-test` 的测试视频对象，入口为：

```bash
python3 scripts/gpu_pool_controller.py runpod canary \
  --task-type ltx25_video_upscale \
  --env cloud-test \
  --env-file .env.cloud.test \
  --input-object-key <test-video-object-key> \
  --ltx25-resolution 2k \
  --allow-existing-prod-managed-pods \
  --execute
```

runner 在目标 heartbeat 后先把新 agent 设为 disabled，仅在提交这一单时临时启用，
终态或异常都会再次禁用并删除本次 test Pod；既有 prod manual Pod 只允许作为忽略的
只读基线，不能成为 cleanup 目标。验收后还要回读 provider 和 Central，确认测试 Pod
与 agent heartbeat 均无残留。

### 3.1 正式 Pod 与测试 Worker 并存

Dashboard 手工创建 `ltx25_video_upscale` 正式 Pod 时，Pod 内始终启动正式 consumer；
它使用 `runpod_prod_ltx25_video_upscale_manual_NN`、prod Central 和
`user-data-prod`。同一 Pod 还启动一个窄化的测试 consumer，使用
`runpod_test_ltx25_video_upscale_<pod-id>`、test Central 和 `user-data-test`，只
声明 `ltx25_video_upscale`。测试 consumer 关闭 prefetch/pipeline，并标记
`POOL_MANAGED=false`，因此不会成为正式 autoscaler 容量，也不会消费正式任务。

两个 consumer 只共享 Pod loopback 上的 ComfyUI 和物理 GPU 队列；各自使用独立
relay 端口、spool、agent identity、Central 与对象存储。不得为了测试开放公网
8188、复用正式 agent ID，或把 test Central 配成正式 Central。正式创建契约会对
test Central URL 和两组 RunPod secret reference fail closed；如果测试配置缺失，
整个 Pod 创建在 provider sanity check 阶段失败，不能退化成只有正式 Worker 的
半配置状态。

因此人工操作只需要在正式 Dashboard 的 RunPod 管理中新增
“LTX-2.5 IC V2V / 视频高清化”。Pod 完成模型同步并启动后，应分别在 prod/test
Central 回读两个 heartbeat；无需创建 cloud-test Pod、填写公网 ComfyUI 地址或在
测试主机部署临时隧道。没有实际创建 Pod 时，只能验证请求渲染和镜像契约，不能声称
测试 Worker 已在线或 GPU 任务已通过。

### 3.2 LAN `all` 与测试 Worker 并存

LAN-only `all` profile 也包含 `ltx25_video_upscale` 的 workflow、节点和独立模型
manifest。正式 consumer 将它作为完整能力集合的一员连接 prod Central；同容器额外
启动一个只声明该类型的 test consumer，连接 test Central 与 `user-data-test`，并
使用独立 relay、spool、prefetch cache 和 agent identity。测试 consumer 不受 GPU
pool 管理且关闭 prefetch/pipeline，不能消费正式任务；两个 consumer 只共享
loopback ComfyUI。

该接线只准备 LAN 底层 Worker，不修改 test/prod Web 配置，也不自动打开
`LTX25_VIDEO_UPSCALE_ENABLED`。LAN artifact 必须进入本地 registry 并按精确 digest
单槽 rollout；不得因此推送 GHCR 或变更云端 RunPod 配置。

## 4. 发布红线与验证

模型准备、镜像构建和 Git 提交不等于部署。创建 RunPod/LAN Worker、上传模型、
修改 test/prod env 或开放入口仍属于 GPU/生产 mutation，必须由用户明确确认。
正式 Dashboard 环境还必须将 `RUNPOD_CLOUD_TEST_CENTRAL_API_URL` 投影给受控
RunPod operator，并把 `ltx25_video_upscale` 加入 verified profile allowlist；
`RUNPOD_RELEASE_PROFILE_PINS_JSON` 中的 LTX25 image 必须为 exact digest。

最小验证包括 task registry、60 个时长/分辨率计价 variant、Central request、
dispatcher、workflow mapping/patcher、ffmpeg 输入规范化、Web 载荷、Bot 菜单配置、
RunPod pod request、前端构建和 `scripts/doc_quality_checker.py`。只验证代码或请求
渲染不能证明 20 秒/2K 最大负载可用；必须以目标测试 GPU 的实际 canary 为准。
