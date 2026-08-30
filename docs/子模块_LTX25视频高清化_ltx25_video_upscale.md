# LTX-2.5 视频高清化

## 1. 能力边界

公开任务类型和执行类型均为 `ltx25_video_upscale`。首版只接收一个最长 5 秒、
最大 40MB 的视频，固定 24fps、121 帧，输出宽高各 2 倍，价格 40 灵石。
它的主要定位是对本项目当前 H3 beta4 生成的已定稿成片做第二次 IC V2V，
不依赖或回退到早期 beta2 模型与工作流。
它是独立 GPU profile，不替换 H3、`ltx_video`、SCAIL-2 或传统超分任务。

Web 使用练功房结构化 `target_video` 上传槽；主 Bot 使用
`menu.video_upscale` 或 `/video_upscale`。两端入口默认关闭：Web 菜单配置中的
`ltx25_video_upscale` 初始为不可见，服务端和 Bot 还要求
`LTX25_VIDEO_UPSCALE_ENABLED=true`。只有模型许可、镜像和 canary 均通过后才能
同时打开入口和执行开关。

## 2. 工作流与输入契约

canonical API workflow 是
`workers/comfy_agent/workflows/LTX 2.5 IC V2V Upscale.api.json`，mapping 和
patcher 固定注入输入视频、正负提示词、seed、IC-LoRA 强度 `1.0` 和输出前缀。
Worker 在上传 ComfyUI 前通过 ffmpeg 统一成 Div64、24fps、121 帧，并为无声视频
补静音轨。最终 `CreateVideo` 复用源视频音轨，不使用采样器生成的音频作为结果。

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
disabled Worker 跑一单 5 秒 canary，核对 2 倍尺寸、121 帧、音轨和 identity/
composition 保真，再决定是否启用接单。

云测试 canary 使用已经上传到 `user-data-test` 的最长 5 秒视频对象，入口为：

```bash
python3 scripts/gpu_pool_controller.py runpod canary \
  --task-type ltx25_video_upscale \
  --env cloud-test \
  --env-file .env.cloud.test \
  --input-object-key <test-video-object-key> \
  --allow-existing-prod-managed-pods \
  --execute
```

runner 在目标 heartbeat 后先把新 agent 设为 disabled，仅在提交这一单时临时启用，
终态或异常都会再次禁用并删除本次 test Pod；既有 prod manual Pod 只允许作为忽略的
只读基线，不能成为 cleanup 目标。验收后还要回读 provider 和 Central，确认测试 Pod
与 agent heartbeat 均无残留。

## 4. 发布红线与验证

模型准备、镜像构建和 Git 提交不等于部署。创建 RunPod/LAN Worker、上传模型、
修改 test/prod env 或开放入口仍属于 GPU/生产 mutation，必须由用户明确确认。

最小验证包括 task registry、Central request、dispatcher、workflow mapping/
patcher、ffmpeg 输入规范化、Web 载荷、Bot 菜单配置、RunPod pod request、前端构建
和 `scripts/doc_quality_checker.py`。
