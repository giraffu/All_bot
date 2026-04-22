# LTX 2.3 I2V.json 工作流分析报告

通过对 `/home/hfy/APP/All_bot/workers/comfy_agent1/workflows/LTX 2.3 I2V.json` 工作流文件的结构和节点逻辑进行梳理，各关键控制节点及注意事项如下：

## 1. 核心控制节点梳理

| 功能 | 节点 ID | 节点类型 (class_type) | 节点标题 (title) | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| **输入图片** | **15** | `LoadImage` | 加载图像 | 工作流的起始图像输入点。 |
| **正向提示词** | **28** | `CLIPTextEncode` | Positive | 描述视频内容的文本。 |
| **负向提示词** | **29** | `CLIPTextEncode` | Negative | 排除不需要的元素的文本。 |
| **视频时长** | **18** | `mxSlider` | Video Length (seconds) | 控制生成的视频秒数。工作流默认 FPS 为 24（节点 `26:43`），通过节点 `26:42` (Video Length) 将秒数转换为帧数：`秒数 * 24 + 1`。 |
| **视频宽度** | **19** | `mxSlider` | Video Width | 控制输出视频的宽度。 |
| **视频高度** | **181** | `mxSlider` | Video Height | 控制输出视频的高度。 |
| **随机种子** | **125** | `Seed (rgthree)` | Seed (rgthree) | 输出随机种子。 |
| **噪波生成** | **123** | `RandomNoise` | 随机噪波 | 接收节点 125 的种子并生成采样所需的初始噪波。 |

---

## 2. 关键逻辑与注意点分析

### 2.1 双阶段生成与空间放大 (Two-Pass & Spatial Upscale)
该工作流采用了一次生成 + 二次放大的“双阶段采样”策略：
- **First Pass (一阶段)**：使用自定义的降噪步数（节点 `225`，Sigmas First Pass）在节点 `26:51` (`Sampler First Pass`) 进行初步的音视频潜空间采样。
- **Spatial Upscale (空间放大)**：一阶段生成的潜空间通过节点 `26:89` (`LTXVLatentUpsampler`，使用 `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` 模型) 进行画面放大。
- **Final Pass (最终阶段)**：放大后的潜空间送入节点 `26:92` (`Sampler Final Pass`)，结合另一组 Sigmas（节点 `226`）进行最终细节完善。

### 2.2 音视频联合生成 (A/V Co-generation)
LTX 2.3 具有音频生成能力：
- 工作流中不仅处理了图像潜空间，还通过节点 `26:40` (`LTXVEmptyLatentAudio`) 生成了空音频潜空间。
- 使用 `LTXVConcatAVLatent` (如节点 `26:45`) 将音频和视频潜空间合并，一起送入采样器。
- 采样完成后，使用 `LTXVSeparateAVLatent` (如节点 `26:153`) 将音视频潜空间分离，并分别使用 VAE 解码（视频通过 `VAEDecode`，音频通过 `LTXVAudioVAEDecode`）。最终使用 `VHS_VideoCombine` 合成带声音的视频。

### 2.3 图片预处理的双重路径 (Image Preprocessing)
用户输入的图片（节点 15）被分发到两条不同的预处理路径：
1. **尺寸重置器 (节点 `26:178` ImageResizeKJv2)**：严格按照节点 19 (Width) 和 181 (Height) 的设定进行裁剪和缩放。
2. **长边约束 (节点 `26:231` ResizeImagesByLongerEdge)**：将图片长边限制为 1536，随后通过 `LTXVPreprocess` (节点 `26:232`) 压缩，并注入到 `LTXVImgToVideoInplace` 中作为 I2V 的参考底图。**注意**：这意味着底图注入时的实际分辨率可能与最终输出设定的宽高比不完全一致，依赖长边 1536 的缩放。

### 2.4 LoRA 模型的管理
- 节点 **6** 和 **7** 使用了 `Power Lora Loader (rgthree)`。
- 节点 **7** 默认开启了一个 LTX 2.3 专用的蒸馏 LoRA (`ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors`)。
- 节点 **6** 预置了大量的 NSFW/特殊效果 LoRA（目前均为 `on: false` 状态）。如果在代码中通过脚本注入参数，需要注意这些预置 LoRA 的开关状态和权重（强度）。

### 2.5 显存/内存管理压力
工作流中显式使用了 `RAMCleanup` (节点 161)、`VRAMCleanup` (节点 163) 和 `VRAM_Debug` (节点 `26:151`，带有清理缓存功能)。这表明 LTX 2.3 加上双阶段采样对显存的消耗极大，若 Worker 节点显存不足，容易在这些步骤触发 OOM（Out Of Memory）。在并发调度时需严格限制该工作流的并行数量。