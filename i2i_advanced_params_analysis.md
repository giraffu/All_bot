# 自由P图 (Image-to-Image) 增加高级参数方案分析

基于当前系统的三层解耦架构（Bot -> Backend -> Worker）以及 `Qwen-Rapid-AIO.json` 工作流，如果需要为自由P图增加 **负面提示词 (Negative Prompt)**、**分辨率 (Resolution)** 和 **长宽比 (Aspect Ratio)** 参数，整体原则是：**前端按需收集，后端透传，Worker 动态篡改连线**。

以下是具体的实施方案分析讨论：

## 一、 Bot 交互层 (Telegram FSM)
**涉及模块**: `src/handlers/fsm/edit_image_fsm.py`

**痛点**: 现有的 FSM 是线性收集的（选模型 -> 传图 -> 传词）。如果为了收集这三个参数直接增加 3 个等待步骤，会导致交互流程过长，严重影响用户体验。
**方案**:
1. **指令后缀解析提取（推荐）**：允许用户在输入提示词时，直接使用类似 Midjourney 的参数语法。例如用户输入：
   `把背景换成赛博朋克城市 --no 闲杂人等, 水印 --ar 16:9`
   在 FSM 接收到提示词文本后，使用正则将其解析，提取出 `--no` (负面提示词) 和 `--ar` (长宽比) 参数，从主提示词中剥离，分别存入 `context.user_data` 中。
2. **高级设置面板**：在输入提示词环节，下方提供一个带有 InlineKeyboardButton 的 `⚙️ 高级设置` 按钮，点击后展开参数面板供选填。

## 二、 Backend 网关层 (FastAPI)
**涉及模块**: `backend/app/models.py` & `backend/app/main.py`

**方案**:
需要扩展现有的 Pydantic 验证模型（如 `Img2ImgRequest` / `Img2ImgLoraRequest`），增加可选字段：
```python
class Img2ImgLoraRequest(BaseModel):
    # ... 原有字段保持不变 ...
    negative_prompt: Optional[str] = ""
    aspect_ratio: Optional[str] = None  # 例如 "16:9", "4:3", "1:1"
    resolution: Optional[str] = None    # 例如 "1024x1024"
```
由于后端的主要职责是参数的校验与透传，只要 Pydantic 模型接收了这些字段，`main.py` 在组装 `TaskType.IMG2IMG` 或 `TaskType.IMG2IMG_LORA` 并压入 Redis 队列时，就能将其原样序列化并带给下游 Worker。

## 三、 Worker 调度层与 ComfyUI 工作流 (核心)
这是整个方案最关键的一环。根据 `Qwen-Rapid-AIO.json` 的结构，我们需要对 `workflow_patcher.py` 机制进行巧妙利用。

### 1. 负面提示词 (Negative Prompt) 的注入
**现状**: 在工作流 JSON 中，Node ID `4` 是负责负面提示词的 `TextEncodeQwenImageEditPlus` 节点，当前其 `prompt` 属性被硬编码为空字符串 `""`。
**方案**:
- **Mappings 映射法**: 无需修改任何 Python 代码逻辑，只需在 `workers/comfy_agent/workflows/mappings.json` 中新增一行映射：`"negative_prompt": "4"`。
- **效果**: 当 Worker 从 Redis 取出的任务载荷中包含 `negative_prompt` 键时，Patcher 会自动将该值填入 Node 4 的 `prompt` 字段。

### 2. 分辨率 (Resolution) 与长宽比 (Aspect Ratio) 的注入
**现状**: 在 JSON 中，最终生成的潜空间图像尺寸由 Node `9` (`EmptyLatentImage`) 决定。
当前 Node 9 的 `width` 和 `height` 是一个数组引用 `["11", 1]` 和 `["11", 2]`。这意味着它动态接收 Node `11` (`GetImageSizeAndCount`) 的输出，而 Node 11 的尺寸来源于输入图片 (Node 10)。**当前逻辑强制生成图与参考图保持一致尺寸比例。**

**方案**: 必须在 `workers/comfy_agent/workflow_patcher.py` 中使用**动态断线与常量注入**策略。
当任务载荷中存在 `aspect_ratio` 或 `resolution` 时，触发自定义 Patch：
1. **定位节点**: 在 Python 字典中找到 `workflow["9"]["inputs"]`。
2. **斩断连线并覆写常量**: 
   将 `width` 和 `height` 从数组形式（连线引用）直接覆写为整型常量（Integer）。
   ```python
   # 伪代码示例：在 workflow_patcher.py 中增加判断
   if "aspect_ratio" in task_payload:
       # 计算等效的百万像素宽高
       width, height = calculate_dimensions_by_ar(task_payload["aspect_ratio"], megapixels=1.0)
       workflow["9"]["inputs"]["width"] = width
       workflow["9"]["inputs"]["height"] = height
   elif "resolution" in task_payload:
       width, height = parse_resolution(task_payload["resolution"])
       workflow["9"]["inputs"]["width"] = width
       workflow["9"]["inputs"]["height"] = height
   ```
3. **安全计算策略 (防爆显存)**: 
   现有工作流中的 Node 10 限制了参考图缩放的 `megapixels: 1`（约 1024x1024）。我们在实现 `calculate_dimensions_by_ar` 函数时，如果用户指定了 `16:9`，代码应自动将其转换为总像素接近 100万的宽高值（例如 1344 x 768），这能有效防止因分辨率过大导致的 GPU OOM。

## 四、 总结与实施建议

为了平稳迭代，建议分步实施：

1. **第一阶段（无感增强）**：
   - 仅修改 `mappings.json` 添加 `negative_prompt: 4`。
   - 修改 Bot 层 FSM，使用正则拦截用户输入的 `--no` 参数。
   - 这一步改动极小，零风险，即可实现负面提示词的支持。
2. **第二阶段（尺寸解绑）**：
   - 修改 `workflow_patcher.py`，增加对 Node 9 的断线覆写逻辑。
   - 在 Bot 层 FSM 继续扩展 `--ar` 和 `--res` 的正则提取。
   - 这一步打破了“必须跟随原图尺寸”的限制，极大提升了自由P图的可玩性和自由度。
