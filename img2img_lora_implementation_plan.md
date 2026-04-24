# 新增 /comfy_img2img_lora 接口实现方案

为了在不影响现有 `/comfy_img2img` 接口和底层生图业务的前提下，支持图生图动态附加或取消 LoRA 模型，建议采用与 `/perfect_video_lora` 类似的设计方案（即：后端 API 增加新路由，复用现有 `TaskType`，并在 Worker 端进行动态工作流修补）。

## 1. 后端 API 数据模型调整
**文件**: `/backend/app/models.py`

新增一个 `Img2ImgLoraRequest` 模型。包含原有的图生图字段，并增加 `lora_name` 和可选的 `lora_strength` 参数。

```python
class Img2ImgLoraRequest(BaseModel):
    image: Optional[str] = None
    image2: Optional[str] = None
    images: Optional[List[str]] = None
    prompt: str
    negative_prompt: Optional[str] = " "
    num_inference_steps: Optional[int] = 6
    guidance_scale: Optional[float] = 1.0
    seed: Optional[int] = None
    priority: int = 0
    # 新增 LoRA 相关参数
    lora_name: Optional[str] = None
    lora_strength: Optional[float] = None
```

## 2. 后端 API 路由新增
**文件**: `/backend/app/main.py`

新增 `/comfy_img2img_lora` 接口。如同 `/perfect_video_lora` 路由复用 `VIDEO_EDIT` 任务类型一样，新接口继续复用 `TaskType.IMG2IMG`，参数会被透传，底层的 Comfy Agent 无需新增 Task 分支即可接收任务。

```python
@app.post("/comfy_img2img_lora", response_model=TaskResponse)
async def create_img2img_lora_task(
    request: Img2ImgLoraRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    params = request.dict()
    priority = params.pop("priority", 0)
    # 复用 IMG2IMG TaskType，参数 lora_name 会随着 params 透传给 Worker
    task_id = await queue_manager.enqueue_task(TaskType.IMG2IMG, params, priority)
    return TaskResponse(task_id=task_id)
```

## 3. Worker 节点工作流动态修补 (Workflow Patcher)
**文件**: `/workers/comfy_agent4/workflow_patcher.py` (及其他相关 agent 节点)

解析原工作流 `Qwen-Rapid-AIO.json` 可知结构如下：
- `Node 1`: `CheckpointLoaderSimple` 模型加载节点。
- `Node 32`: `LoraLoaderModelOnly` 节点（默认加载 `qwen/YARN_1.0.safetensors`）。
- `Node 2`: `KSampler`，其 `model` 输入连接自 `Node 32`。

我们需要在 `patch_workflow` 方法处理 `task_type == "img2img"` 的逻辑中，根据 `lora_name` 的值动态修改节点属性和连线：

```python
        # Dynamic JSON pruning for img2img task to avoid empty nodes and blank inputs
        if task_type == "img2img":
            # ... [此处保留原有清理 image2, image3 节点的逻辑] ...

            # === 新增动态处理 LoRA 逻辑 ===
            if "lora_name" in params:
                lora_name = params["lora_name"]
                if lora_name and str(lora_name).strip() != "":
                    # 场景 1: 用户指定了具体的 LoRA 模型名称 -> 覆盖原有 LoRA 名称
                    if "32" in wf and "inputs" in wf["32"]:
                        wf["32"]["inputs"]["lora_name"] = lora_name
                        if params.get("lora_strength") is not None:
                            wf["32"]["inputs"]["strength_model"] = float(params["lora_strength"])
                elif lora_name == "":
                    # 场景 2: 用户显式传入空字符串 ("") -> 动态摘除 LoRA 节点
                    # 绕过 Node 32，将 KSampler (Node 2) 的 model 直接连到 Checkpoint (Node 1)
                    if "2" in wf and "inputs" in wf["2"]:
                        wf["2"]["inputs"]["model"] = ["1", 0]
                    # 删除原来的 LoRA 节点
                    if "32" in wf:
                        wf.pop("32", None)
                # 场景 3: 如果 lora_name 为 None (或原有老接口调用)，则什么都不做，保留工作流默认的 LoRA 模型
```

## 4. 方案优势与影响评估
1. **零侵入性 (兼容性)**: 没有修改现有的 `/comfy_img2img` 接口代码，老接口调用时不会传入 `lora_name` 键（或传 None），代码会直接跳过修补逻辑，保持工作流默认带有 `YARN_1.0` 的行为。
2. **极高灵活性**: 新接口支持传入任意 `lora_name` 以替换模型，同时也支持传入空字符串 `""` 来动态摘除该节点进行纯大模型推理，满足“不附加 LoRA”的需求。
3. **架构统一**: 遵循了系统中现有的“同一种工作流 (TaskType) 通过不同 API 入口解耦参数映射”的最佳实践。