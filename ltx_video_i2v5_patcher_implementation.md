# LTX Video I2V5 Patcher 实施方案

## 1. 背景

当前项目中的高级图生视频任务类型为 `ltx_video`，Worker 在加载工作流后，会进入 `workers/comfy_agent/workflow_patcher.py` 的专用补丁逻辑，对 `LTX 2.3 I2V.json` 做一次运行时裁剪和重连。

现状代码位于：

- `workers/comfy_agent/workflow_patcher.py`

当前 `ltx_video` 分支的核心逻辑为：

```python
elif task_type == "ltx_video":
    if "210" in wf:
        wf.pop("210", None)
    if "5" in wf:
        wf.pop("5", None)
    if "59" in wf:
        wf.pop("59", None)

    if "8" in wf and "inputs" in wf["8"]:
        wf["8"]["inputs"]["model"] = ["7", 0]
```

这段逻辑是基于旧版 `LTX 2.3 I2V.json` 的节点拓扑写死的。

现在计划废弃旧工作流，直接用 `LTX 2.3 I2V5.json` 替换旧文件，并最终将其重命名为 `LTX 2.3 I2V.json`。因此不需要兼容双版本，只需要保证新工作流在当前架构下稳定运行。

---

## 2. 问题分析

### 2.1 当前风险点

旧 patcher 逻辑会在删除 `210` 之后，把节点 `8` 的 `model` 输入直接接回 `["7", 0]`。

但在新 `I2V5` 工作流中：

- `8` 的上游当前是 `210`
- `210.inputs.model` 指向的是 `["256", 0]`
- `7` 本身又依赖 `8`

如果仍然保留旧逻辑：

```python
wf["8"]["inputs"]["model"] = ["7", 0]
```

则会在新工作流中形成：

```text
7 -> 8 -> 7
```

这会导致以下问题之一：

- ComfyUI 在校验 prompt 时直接拒绝执行
- 执行阶段出现环依赖或结构错误
- Worker 表面提交成功，但 ComfyUI history 中无有效输出

### 2.2 为什么旧逻辑曾经是对的

旧版 `LTX 2.3 I2V.json` 中，`210` 被当作 preview override 使用，其 `model` 上游链路最终可安全回接到 `7`。因此删除 `210` 后，将 `8` 直接接回 `7` 不会形成环。

### 2.3 为什么新工作流必须改成接 `256`

在新 `LTX 2.3 I2V5.json` 中，`210` 删除后，`8` 不应该回接到 `7`，而应该接到 `210` 原本的 `model` 来源，也就是：

```python
["256", 0]
```

因此，对于仅适配 `I2V5` 的最终方案，重连目标应固定修改为：

```python
wf["8"]["inputs"]["model"] = ["256", 0]
```

---

## 3. 新工作流下的目标行为

替换后的目标行为如下：

1. Worker 加载新的 `LTX 2.3 I2V.json`（实际内容来自原 `I2V5`）
2. 运行 `ltx_video` patcher
3. 删除会影响 API 模式的 preview 相关节点
4. 将 `8.inputs.model` 重新指向 `["256", 0]`
5. 保持参数注入逻辑不变
6. 保持结果输出节点和回传逻辑不变

等价理解为：

```text
删除 210 后，8 不再走 preview override，而是直接走新图中的基础模型分支 256
```

---

## 4. 实施范围

本次实施只涉及以下内容：

- 修改 `workers/comfy_agent/workflow_patcher.py`
- 替换工作流文件：
  - 删除旧 `workers/comfy_agent/workflows/LTX 2.3 I2V.json`
  - 将 `workers/comfy_agent/workflows/LTX 2.3 I2V5.json` 重命名为 `LTX 2.3 I2V.json`

本次不需要修改以下模块：

- Telegram FSM
- `TaskService`
- `task_dispatcher`
- `image_service`
- `api_client`
- FastAPI `LtxVideoRequest`
- 队列类型 `TaskType.LTX_VIDEO`
- 结果下载与回传逻辑
- `mappings.json`

原因是新旧工作流对外暴露的任务参数接口没有变化，`ltx_video` 仍然只依赖：

- `image`
- `prompt`
- `width`
- `height`
- `length`

---

## 5. 代码修改方案

### 5.1 修改目标

文件：

- `workers/comfy_agent/workflow_patcher.py`

当前代码：

```python
elif task_type == "ltx_video":
    # Remove the preview override node as it causes AttributeError in API mode (serv.last_node_id is None)
    if "210" in wf:
        wf.pop("210", None)
    if "5" in wf:
        wf.pop("5", None)
    if "59" in wf:
        wf.pop("59", None)
    # Route Node 7 directly to Node 8
    if "8" in wf and "inputs" in wf["8"]:
        wf["8"]["inputs"]["model"] = ["7", 0]
```

建议修改为：

```python
elif task_type == "ltx_video":
    # I2V5 工作流下，210 删除后需要把 8 直接接回 256，避免形成 7 -> 8 -> 7 环
    if "210" in wf:
        wf.pop("210", None)
    if "5" in wf:
        wf.pop("5", None)
    if "59" in wf:
        wf.pop("59", None)

    if "8" in wf and "inputs" in wf["8"]:
        wf["8"]["inputs"]["model"] = ["256", 0]
```

### 5.2 注释建议

建议把旧注释：

```python
# Route Node 7 directly to Node 8
```

改成更明确的说明，例如：

```python
# I2V5 工作流中，删除 210 后，8 必须接回 256；若接回 7 会形成环依赖
```

这样后续维护者看到这段代码时，能立刻知道这是对新工作流拓扑的硬编码适配，而不是随意写的数字。

---

## 6. 文件替换步骤

建议按以下顺序执行：

1. 先修改 `workflow_patcher.py`
2. 确认本地代码已保存
3. 删除旧工作流文件 `workers/comfy_agent/workflows/LTX 2.3 I2V.json`
4. 将 `workers/comfy_agent/workflows/LTX 2.3 I2V5.json` 重命名为 `workers/comfy_agent/workflows/LTX 2.3 I2V.json`
5. 重启对应的 comfy-agent 进程或容器
6. 提交一条最小化 `ltx_video` 任务验证

不建议先删旧文件再改 patcher，否则在 patcher 尚未更新的窗口期内，若 worker 被重启，就可能直接加载新文件并套用旧逻辑，导致任务失败。

---

## 7. 验证方案

### 7.1 静态验证

验证替换后的工作流与代码是否匹配：

- `workflow_patcher.py` 中不再出现：

```python
["7", 0]
```

- `ltx_video` 分支中明确改成：

```python
["256", 0]
```

- 新的 `LTX 2.3 I2V.json` 中：
  - 存在节点 `8`
  - 存在节点 `256`
  - 原 `210` 为 preview override
  - 最终输出节点仍保留视频输出能力

### 7.2 运行验证

提交一条最小 `ltx_video` 任务，观察：

- Worker 日志没有 `cycle`、`invalid prompt`、`execution_error`
- ComfyUI 成功接收 prompt
- history 中存在 `videos` 输出
- Worker 能正常拿到 `result_path`
- Bot 或 Web 能正常下载最终 mp4

### 7.3 结果回传验证

重点确认以下行为未受影响：

- `agent_main.py` 能从 websocket 或 history 中拿到 `videos`
- `VHS_VideoCombine` 输出仍可被识别
- `/video/{task_id}` 可以成功下载文件

---

## 8. 风险点与排障建议

### 8.1 硬编码节点 ID 变更风险

本方案建立在以下新工作流节点 ID 不变的前提上：

- `8`
- `210`
- `256`
- `61`

如果你后续再次在 ComfyUI 里改图并重新导出 API JSON，导致这些节点重新编号，则必须同步更新 patcher。

### 8.2 输出节点变化风险

如果后续新工作流不再使用当前的 `VHS_VideoCombine` 输出视频，虽然 patcher 本身可能不报错，但 worker 结果回传可能会出现：

- history 里没有 `videos`
- 最终 `task_result` 为空
- Bot 提示“生成完成但未获取到文件路径”

### 8.3 误删节点风险

当前 patcher 会删除：

- `210`
- `5`
- `59`

其中：

- `210` 是本次明确要删除的 preview override
- `59` 是旧工作流里的额外视频合成输出节点，新图里已经不存在，`pop(..., None)` 安全
- `5` 仍存在于新图，是否继续删除，应以实际 API 模式兼容性为准；如果未来验证发现删除 `5` 会影响别的链路，需要单独回看它在新图中的真实用途

换句话说，本次最关键、必须调整的是 `8 -> 256`；`5` 是否继续删除属于次级验证项。

---

## 9. 推荐的最小落地版本

如果希望这次改动尽量小、尽量稳，建议只做以下最小修改：

1. 保留现有删除逻辑
2. 仅将

```python
wf["8"]["inputs"]["model"] = ["7", 0]
```

改成

```python
wf["8"]["inputs"]["model"] = ["256", 0]
```

3. 增加一行清晰注释，说明该逻辑只适配新 `I2V5`

这是本次替换工作流后最小、最直接、风险最低的落地方案。

---

## 10. 结论

本次 `ltx_video` 工作流替换的核心不是后端接口，也不是用户调用链路，而是 Worker 中对新工作流拓扑的硬编码重连必须同步更新。

最终结论如下：

- 旧逻辑 `8 -> 7` 不能再用
- 新逻辑应改为 `8 -> 256`
- 本次不需要保留双版本兼容
- 只要 patcher 和新工作流文件同时切换，现有的 `ltx_video` 业务链路无需额外改造

一句话总结：

> 这次替换的关键修复点，就是把 `ltx_video` patcher 从“删除 210 后接回 7”改成“删除 210 后接回 256”。
