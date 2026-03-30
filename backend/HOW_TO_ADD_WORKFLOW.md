# 后端添加新 ComfyUI 工作流指南

本指南介绍如何将一个新的 ComfyUI 工作流添加到后端系统，并正确暴露和映射参数。

---

## 1. 准备工作流文件

### 1.1 导出 API 格式 JSON
在 ComfyUI 界面中：
1. 打开设置 (Settings)。
2. 勾选 **"Enable Dev mode Options"**。
3. 点击右侧面板中的 **"Save (API Format)"**。
   - **注意**：必须是 API Format，普通的 `Save` 导出的 JSON 包含 UI 信息，后端无法直接解析。

### 1.2 放置文件
将导出的 JSON 文件重命名并放入以下目录：
`backend/workflows/your_workflow_name.json`

---

## 2. 定义任务类型

在 [models.py](file:///home/ubantu/backend/app/models.py) 中，将新任务添加到 `TaskType` 枚举类：

```python
class TaskType(str, Enum):
    IMG2IMG = "img2img"
    # ... 其他任务
    NEW_TASK = "new_task"  # 添加这一行
```

---

## 3. 配置参数映射

在 [mappings.json](file:///home/ubantu/backend/workflows/mappings.json) 中定义如何将 API 请求参数注入到 ComfyUI 节点。

### 映射规则示例：
```json
"new_task": {
    "prompt": "3",            // 将参数 prompt 注入到 ID 为 3 的节点
    "prompt_input": "text",   // 对应节点的输入字段名为 text
    "image": "10",            // 将图片文件名注入到 ID 为 10 的节点
    "image_input": "image"    // 对应 LoadImage 节点的输入字段名为 image
}
```
- **Key**: 用户在 API 请求中传递的参数名。
- **Value**: ComfyUI 工作流中的节点 ID（字符串）。
- **{Key}_input**: (可选) 指定节点内的具体输入字段名，默认通常为 `image`。

---

## 4. 实现 API 接口

在 [main.py](file:///home/ubantu/backend/app/main.py) 中添加一个新的 POST 路由：

```python
@app.post("/new_task", response_model=TaskResponse)
async def create_new_task(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    priority: int = Form(0),
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    # 1. 保存上传的文件
    filename = await save_upload_file(image)
    
    # 2. 构建参数字典 (需与 mappings.json 中的 Key 一致)
    params = {
        "image": filename,
        "prompt": prompt
    }
    
    # 3. 入队任务
    task_id = await queue_manager.enqueue_task(TaskType.NEW_TASK, params, priority)
    return TaskResponse(task_id=task_id)
```

---

## 5. 关联工作流文件

在 [worker.py](file:///home/ubantu/backend/app/worker.py) 的 `load_workflow` 方法中添加文件映射逻辑：

```python
def load_workflow(self, task_type: str) -> Dict[str, Any]:
    # ... 现有逻辑
    if task_type == TaskType.NEW_TASK:
        filename = "your_workflow_name.json"
    # ...
```

---

## 6. 应用更改

完成代码修改后，需要重建并重启容器：

```bash
cd /home/ubantu/backend
docker compose up -d --build
```

---

## 7. 调试与验证

- **查看日志**：`docker logs -f backend-api-1` 观察任务处理情况。
- **检查 Patch 文件**：系统会自动在 `workflows/` 目录下生成 `debug_patched_new_task.json`，打开它可以检查参数是否被正确替换。
- **验证输出**：任务完成后，通过 `/image/{task_id}` 接口获取结果。
