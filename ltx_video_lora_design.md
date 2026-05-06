# LTX Video 附加模型 (LoRA) 动态控制设计方案

## 1. 现状与需求分析

目前系统中的高级图生视频（`ltx_video`）底层使用了 `LTX 2.3 I2V.json` 工作流。根据工作流分析：
- **加载节点**：工作流中的 `Node 6` 使用了 `Power Lora Loader (rgthree)` 节点来加载 LoRA。
- **硬编码状态**：目前该节点静态加载了三个 LoRA 模型：
  1. `ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors` (强度: 0.8)
  2. `ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors` (强度: 0.6)
  3. `ltx2.3/SynthPussy_01_rank32.safetensors` (强度: 0.5)
- **需求**：在不破坏现有架构红线的前提下，将这三个静态的 LoRA 转化为用户可选的动态配置，实现 Bot 和 Web 端对附加模型的自由控制。

---

## 2. 架构设计与数据流向

按照系统的分层解耦架构，我们需要从交互层、网关层到调度层打通参数传递的链路。

### A. 交互与状态机层 (Bot FSM / Web UI)
1. **模型配置字典**：在 `src/constants.py` 或 FSM 文件中统一定义这三个 LoRA 的中英文映射及默认权重。
   ```python
   LTX_VIDEO_LORAS = {
       "reasoning": {"path": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors", "strength": 0.8, "zh": "逻辑增强"},
       "preview": {"path": "ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors", "strength": 0.6, "zh": "画质预览"},
       "synth": {"path": "ltx2.3/SynthPussy_01_rank32.safetensors", "strength": 0.5, "zh": "特殊风格"}
   }
   ```
2. **Telegram Bot (ltx_video_fsm.py)**：
   - 现有的 `WAIT_SETTINGS_AND_PROMPT` 状态中，Inline 键盘已经包含了画质和时长的选择。
   - **方案 1（推荐单选）**：在键盘下方增加一行“风格选择”按钮（如：`无附加风格`、`逻辑增强`等）。用户点击后，记录 `lora_choice` 到 `context.user_data['ltx_video_data']`。
   - **方案 2（多选开关）**：将三个 LoRA 做成 Toggle 开关，允许叠加使用。
3. **Web 端**：在提交高级视频的表单中，新增一个 Select 下拉框或 Checkbox 组。

### B. 后端网关层 (Backend API)
1. **模型修改**：在 `backend/app/models.py` 中的 `LtxVideoRequest` 模型新增可选参数。
   ```python
   class LtxVideoRequest(BaseModel):
       # ... 现有字段
       loras: Optional[list[dict]] = None  # 例如 [{"name": "...", "strength": 0.8}]
       # 或者如果采取单选：
       # lora_name: Optional[str] = None
   ```
2. **参数组装**：Bot 的 `TaskService.process_ltx_video_task` 接收到用户选择后，将对应的 `loras` 列表组装并发送给 FastAPI 后端，由网关压入 Redis 队列。

### C. 核心调度层 (Worker Patcher)
这是最关键的一环。需要修改 `workers/comfy_agent/workflow_patcher.py` 中的 `patch_workflow` 方法，专门针对 `ltx_video` 任务类型和 `rgthree` 节点进行动态清洗与注入。

**实施逻辑：**
```python
elif task_type == "ltx_video":
    # 1. 现有的防爆清理逻辑...
    
    # 2. 动态 LoRA 注入逻辑 (针对 Node 6)
    if "6" in wf and wf["6"].get("class_type") == "Power Lora Loader (rgthree)":
        inputs = wf["6"]["inputs"]
        
        # 步骤 A：清洗硬编码的静态 LoRA (删除所有 lora_X 键)
        keys_to_remove = [k for k in inputs.keys() if k.startswith("lora_")]
        for k in keys_to_remove:
            inputs.pop(k, None)
            
        # 步骤 B：根据传入的参数动态注入
        user_loras = params.get("loras", [])
        if not user_loras:
            # 如果用户选择“无”，为防止 rgthree 节点报错，可以传入一个空状态，或者将其绕过
            # 最安全的方式是随便给一个空的 lora_1，并设置 on: false
            inputs["lora_1"] = {"on": False, "lora": "", "strength": 0.0}
        else:
            # 动态生成 lora_1, lora_2...
            for idx, lora_cfg in enumerate(user_loras, start=1):
                inputs[f"lora_{idx}"] = {
                    "on": True,
                    "lora": lora_cfg["name"],
                    "strength": float(lora_cfg.get("strength", 0.8))
                }
```

---

## 3. rgthree 节点动态注入的特殊注意事项 (红线提示)

1. **节点 ID 硬编码红线**：根据 `allbot-comfy-models` 技能规范，此方案依赖硬编码的节点 ID（当前为 `"6"`）。若后续在 ComfyUI 中重新连线并导出 API 格式的 JSON 导致 ID 发生改变，必须同步更新 `workflow_patcher.py`，否则动态控制将失效。
2. **数据结构严格性**：`Power Lora Loader (rgthree)` 严格要求输入的 JSON 结构为字典对象（包含 `on`, `lora`, `strength` 三个 Key），千万不能像普通的 `LoraLoader` 那样只传字符串。
3. **空载直通容错**：当不选择任何 LoRA 时，`rgthree` 节点只要没有任何 `on: true` 的项，它会自动直通（Pass-through）模型和 CLIP 数据，因此不需要像原版 LoRA 节点那样写复杂的“断线重连（Bypass）”逻辑，大幅简化了代码复杂度。

## 4. 总结与下一步行动

本方案**完全遵循**现有的解耦原则：
- 不破坏底层的 `.json` 模板文件，只需将其视为“底座”。
- 在 `workflow_patcher.py` 实施手术刀级别的精准修改。
- 业务侧（灵石计费、并发锁）完全透明，无缝兼容现有的 `ltx_video` 核心逻辑。

若确认该方案可行，下一步即可直接按照本设计实施代码层面的变更。
