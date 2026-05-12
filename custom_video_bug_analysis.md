# `custom_video` Bug 原因梳理与更严谨的结论

## 1. 问题概述

最近在 `custom_video` 链路中出现了用户任务失败的问题，常见表象包括：

- `tg-bot` 最终提示失败
- `comfy-agent` 日志出现 MinIO `NoSuchKey`
- ComfyUI 返回 `Prompt outputs failed validation`
- 失败节点集中在工作流里的 `LoadImage`

结合当前仓库代码，可以较高置信度地认为：**这类问题的直接触发点，不是 ComfyUI 工作流模板本身，而是上游把“本地临时路径”继续透传到了下游，最终被 worker 当成 MinIO Object Key 去下载。**

但需要把几个概念分开写清楚：

1. **直接根因**：`bot/core` 侧对本地输入上传失败缺少硬失败保护，导致原始本地路径可能继续向下游透传。
2. **故障放大器**：worker 对输入处理失败缺少 fail-fast，导致错误没有停留在“非法输入”这一层，而是继续扩散到 ComfyUI 执行阶段。
3. **独立问题**：当前 FSM 临时目录与 `TaskService` 清理目录不一致，容易造成临时文件残留；它与本次 `NoSuchKey` 并不是同一个问题，但值得一起修。

同时需要特别说明：**按当前代码，不能把主因定性为“FSM 在创建后台任务后立刻删掉了本地图片”。** 当前代码更能证明的是“文件没有被这一轮 FSM 清理删掉”，以及“统一清理逻辑实际上删不到这类临时文件”。

## 2. 与当前代码一致的调用链

一次典型失败链路如下：

1. 用户在 Telegram 中进入 `custom_video` 流程并上传参考图。
2. FSM 把图片下载到本地临时目录，例如：

```text
/tmp/bot_fsm_tmp/xxxx_custom_vid.png
```

3. 用户发送提示词后，FSM 在 `receive_prompt(...)` 中先把 `image_path` 从 `custom_video_data` 里 `pop` 出来，再启动后台任务。
4. 随后 FSM 调用 `_cleanup_context(...)`；但由于 `image_path` 已经被 `pop`，这一轮清理实际上拿不到当前任务用到的图片路径，因此**不会在这里把这张图删掉**。
5. 后台任务进入 `TaskService.process_custom_video_task(...)`，再进一步调用 `process_and_submit_task(...)`。
6. `process_and_submit_task(...)` 会调用 `_process_input_path(...)`，尝试把本地临时图上传到 MinIO。
7. 如果上传成功，下游拿到的是合法对象 key；如果上传失败，或者本地文件此时不可读，`_process_input_path(...)` 当前不会直接报错，而是把原始路径继续返回。
8. 因此 `saved_input_images` 里可能出现如下脏值：

```text
/tmp/bot_fsm_tmp/xxxx_custom_vid.png
```

9. 视频分发策略会把 `saved_input_images[0]` 当作 `image_path` 传给 `submit_perfect_video_edit(...)`。
10. 该接口语义要求 `image_path` 是 MinIO Object Key，但当前链路没有在上游强制校验。
11. worker 收到任务后，会把 `image` 参数当成 MinIO object name 下载。
12. 如果传入的是 `/tmp/...` 本地路径，MinIO 会返回 `NoSuchKey`。
13. worker 当前对输入处理失败缺少 fail-fast：无论是 MinIO 下载失败，还是上传到 ComfyUI API 失败，都不一定会立刻中止任务；坏参数仍可能继续参与 workflow patch / prompt 提交。
14. ComfyUI 最终在 `LoadImage` 节点消费到无效输入，返回 `Prompt outputs failed validation`。

因此，**最终报错虽然发生在 worker / ComfyUI 侧，但当前代码下最早可确认的设计缺陷，发生在 bot/core 的输入路径软失败回退。**

## 3. 更准确的根因拆分

### 3.1 直接根因：`_process_input_path(...)` 缺少硬失败保护

`_process_input_path(...)` 的当前逻辑是：

- 如果是 `template:`，直接返回
- 如果是 `MINIO_BUCKET/...`，去掉 bucket 前缀后返回
- 否则把它当成本地文件，调用 `user_logger.save_input_image(path)` 尝试上传
- 如果上传结果为空，则直接把原始 `path` 返回

而 `save_input_image(...)` 在以下场景都会返回空字符串：

- 本地文件不存在
- 上传到存储失败

这意味着像 `/tmp/bot_fsm_tmp/xxx.png` 这样的本地路径，在上传失败时不会被拦截，而是会继续向下游扩散。

这也是为什么说它是**直接根因**：因为 `/tmp/...` 这类值正是在这里首次被默认视为“可继续使用的输入”。

### 3.2 第二道防线缺失：worker 对输入处理失败缺少 fail-fast

worker 在处理 `image` / `image2` / `face_image` / `body_image` / `video` 等输入时，会先尝试从 MinIO 下载到本地，再上传到 ComfyUI。

但当前实现里，如果输入处理失败：

- MinIO 下载失败时，只会记录错误日志
- 上传到 ComfyUI API 失败时，也只是记 `warning`
- 不会立刻 `raise`
- 也不会阻止后续 workflow patch / prompt 提交

因此它更准确的定位是：

- **不是制造脏输入的首因**
- **而是没有及时兜底，导致故障继续蔓延到 ComfyUI**

换句话说，worker 这里更像是“故障放大器”或“第二道防线失效”，而不是 `/tmp/... -> NoSuchKey` 这条链路的首个源头。

### 3.3 不能从当前代码直接推出的结论：FSM 提前删文件

当前代码中，`receive_prompt(...)` 在调用 `create_background_task(...)` 之前，已经先执行了：

```python
image_path = fsm_data.pop("image_path", None)
```

随后虽然确实调用了 `_cleanup_context(...)`，但 `_cleanup_context(...)` 读取的是 `context.user_data["custom_video_data"]["image_path"]`；该值已经被 `pop` 掉，因此这一步不会删掉刚刚提交给后台任务的那张图。

也就是说：

- “FSM 调用了 `_cleanup_context(...)`” 这件事是真的
- “这次 `_cleanup_context(...)` 删掉了当前提交任务所需图片” 这个结论，与当前代码不一致

更进一步，`TaskService.process_custom_video_task(...)` 虽然在 `finally` 里调用了 `_cleanup_files([image_path])`，但 `_cleanup_files(...)` 只会删除 `TMP_DIR` 前缀路径；而 `custom_video` 实际把图片保存在 `/tmp/bot_fsm_tmp/...`。

因此按当前实现来看：

- `_cleanup_context(...)` 不会删除当前提交任务所需图片
- `TaskService` 的 `finally` 也**删不到**这张 `/tmp/bot_fsm_tmp/...` 图片

所以更准确的结论是：**当前代码不能证明“文件被提前删除”；相反，它更能证明这条链路存在“临时文件可能遗留”的清理缺口。**

## 4. 关键证据链

### 4.1 代码层证据

- [custom_video_fsm.py](file:///home/hfy/APP/All_bot/src/handlers/fsm/custom_video_fsm.py#L34-L42)
  - `_cleanup_context()` 会删除 `custom_video_data["image_path"]`

- [custom_video_fsm.py](file:///home/hfy/APP/All_bot/src/handlers/fsm/custom_video_fsm.py#L244-L270)
  - `receive_prompt(...)` 会先 `pop("image_path")`，再启动后台任务，再调用 `_cleanup_context(...)`

- [task_service.py](file:///home/hfy/APP/All_bot/src/services/task_service.py#L926-L1002)
  - `process_custom_video_task(...)` 的后台任务里才会构造 `inputs` 并调用 `process_and_submit_task(...)`

- [task_service.py](file:///home/hfy/APP/All_bot/src/services/task_service.py#L1096-L1102)
  - 后台任务 `finally` 的确会尝试清理 `image_path`

- [task_service.py](file:///home/hfy/APP/All_bot/src/services/task_service.py#L1648-L1653)
  - `_cleanup_files(...)` 只会删除 `TMP_DIR` 前缀路径

- [constants.py](file:///home/hfy/APP/All_bot/src/constants.py#L1-L5)
  - `TMP_DIR` 当前是 `./tg_tmp`，与 `custom_video` 实际使用的 `/tmp/bot_fsm_tmp` 不一致

- [task_core.py](file:///home/hfy/APP/All_bot/src/core/task_core.py#L13-L29)
  - `_process_input_path(...)` 在上传结果为空时，会回退返回原始路径

- [task_core.py](file:///home/hfy/APP/All_bot/src/core/task_core.py#L246-L255)
  - `process_and_submit_task(...)` 会把 `_process_input_path(...)` 的返回值写入 `saved_input_images`

- [logger.py](file:///home/hfy/APP/All_bot/src/logger.py#L63-L88)
  - `save_input_image(...)` 在本地文件不存在或上传失败时，返回空字符串而不是抛异常

- [task_dispatcher.py](file:///home/hfy/APP/All_bot/src/core/task_dispatcher.py#L209-L255)
  - 视频策略会把 `saved_input_images[0]` 直接当作 `image_path` 分发给视频提交接口

- [api_client.py](file:///home/hfy/APP/All_bot/src/api_client.py#L110-L135)
  - `submit_perfect_video_edit()` 明确要求 `image_path` 必须是 MinIO Object Key

- [agent_main.py](file:///home/hfy/APP/All_bot/workers/comfy_agent/agent_main.py#L279-L294)
  - worker 会把收到的 `image` 参数当成 MinIO object name 去下载

- [agent_main.py](file:///home/hfy/APP/All_bot/workers/comfy_agent/agent_main.py#L357-L385)
  - 输入下载失败时，worker 当前只记日志，不会立刻中止；上传到 ComfyUI API 失败时也只是 `warning`

- [workflow_patcher.py](file:///home/hfy/APP/All_bot/workers/comfy_agent/workflow_patcher.py#L101-L108)
  - params 中残留的坏输入仍可能被 patch 到工作流节点

### 4.2 日志层证据

如果现场失败日志里同时出现以下组合：

- `comfy-agent` 在下载如下值时报错：

```text
/tmp/bot_fsm_tmp/xxxx_custom_vid.png
```

- MinIO 返回 `NoSuchKey`
- ComfyUI 提示：

```text
Invalid image file
Prompt outputs failed validation
```

那么可以较高置信度地反推出：worker 收到的并不是类似

```text
10000000031798/input_images/xxxx_custom_vid.png
```

这种正常对象 key，而是 bot 侧本地临时路径或其他非法对象名。

## 5. 哪些问题可以排除，哪些不能

### 5.1 可以基本排除：ComfyUI 工作流模板先天损坏

从当前代码看，worker 会先把输入文件名 patch 到工作流中；如果传入参数本身就是脏值，那么即使工作流模板结构正常，也会在 `LoadImage` 节点失败。

因此当前更像是“输入污染触发工作流报错”，而不是“工作流模板本身先天损坏”。

### 5.2 不能仅凭代码直接推出：MinIO 整体不可用

当前代码能证明的是：当 worker 把 `/tmp/...` 这类本地路径当成 object name 去 MinIO 下载时，会触发 `NoSuchKey`。

这并不能直接推出：

- MinIO 主服务宕机
- 网络整体不可用
- 存储层一定存在全局故障

### 5.3 不能在没有现场日志时完全排除：配置类问题

仓库中已有运维文档记录过另一类相似故障：如果 worker 使用的 `MINIO_INPUT_BUCKET` 与主服务写入使用的 bucket 不一致，也可能出现 `NoSuchKey` / ComfyUI 400。

相关证据：

- [workers/docker-compose.yml](file:///home/hfy/APP/All_bot/workers/docker-compose.yml#L23-L35)
  - worker 通过环境变量注入 `MINIO_INPUT_BUCKET`

- [ops_deployment.md](file:///home/hfy/APP/All_bot/docs/%E5%AD%90%E6%A8%A1%E5%9D%97_%E8%BF%90%E7%BB%B4%E6%8C%87%E5%8D%97%E4%B8%8E%E5%AE%B9%E5%99%A8%E7%AE%A1%E7%90%86_ops_deployment.md#L71-L82)
  - 文档明确记录了“桶名不一致会导致 Agent 报 `NoSuchKey` 或 ComfyUI 400”

因此更严谨的说法应该是：

- **如果现场日志已经明确显示 worker 正在下载 `/tmp/bot_fsm_tmp/...`，那么本次问题基本可以定位为“本地路径被透传”**
- **如果没有这条日志，仅凭 `NoSuchKey + ComfyUI 400` 还不能完全排除 bucket 配置错误等其他输入侧问题**

### 5.4 不是单机 worker 特例

从代码结构看，所有 worker 都采用同样的输入下载逻辑；因此如果上游传入同样的脏参数，理论上任何承担该任务类型的 worker 都可能复现同类问题。

## 6. 影响范围

当前已确认会影响 `custom_video` 这条视频任务链路，因为它满足以下条件：

- 用户输入先落到本地临时目录
- 后台任务会在后续步骤中再把本地图上传到 MinIO
- 上传失败时，链路没有在 bot/core 层硬失败
- worker 下载失败时，也没有立刻终止

但“临时目录与清理职责不一致”这个问题并不只存在于 `custom_video`。

当前仓库中，多个 FSM 都直接使用 `/tmp/bot_fsm_tmp` 落盘，例如：

- [custom_video_fsm.py](file:///home/hfy/APP/All_bot/src/handlers/fsm/custom_video_fsm.py#L102-L107)
- [quick_video_fsm.py](file:///home/hfy/APP/All_bot/src/handlers/fsm/quick_video_fsm.py#L120-L125)
- [video_lora_fsm.py](file:///home/hfy/APP/All_bot/src/handlers/fsm/video_lora_fsm.py#L143-L148)
- [ltx_video_fsm.py](file:///home/hfy/APP/All_bot/src/handlers/fsm/ltx_video_fsm.py#L99-L104)

而统一清理逻辑仍只认 `TMP_DIR`：

- [task_service.py](file:///home/hfy/APP/All_bot/src/services/task_service.py#L1648-L1653)

因此建议把这个问题视为**共享基础设施问题**，而不是 `custom_video` 独有问题。

## 7. 推荐解决方案

### 方案 A：给 `_process_input_path(...)` 增加硬校验

这是首要修复项。

建议规则：

- 如果传入值是本地绝对路径，且文件不存在，直接抛出明确异常
- 如果 `save_input_image(...)` 返回空字符串，不允许默认回退原路径
- 对视频任务这类“下游明确要求对象 key”的场景，应强制保证输出只能是合法对象 key

优点：

- 错误更早暴露
- 日志更容易定位
- 可以阻止 `/tmp/...` 这类本地路径继续扩散到下游

### 方案 B：worker 侧对输入处理失败立即硬失败

这是必须补的第二道防线。

建议改法：

1. `process_single_image(...)` 在下载 MinIO 输入失败时直接抛异常
2. 上传到 ComfyUI API 失败时也直接中止，而不是只记 `warning`
3. 阻止后续 workflow patch / prompt 提交
4. 对外明确上报“上游传入非法对象 key”或“输入文件下载失败”

优点：

- 失败位置更接近真实问题
- 不会再把脏输入继续污染到 ComfyUI
- 错误语义比 `Prompt outputs failed validation` 更准确

### 方案 C：统一 FSM 临时目录与清理职责

当前问题不是 `custom_video` 独有的，而是同类 FSM 普遍存在的目录不一致问题。

建议统一策略：

1. 要么把相关 FSM 下载目录统一切到 `TMP_DIR`
2. 要么扩展 `_cleanup_files(...)`，让它能清理 `/tmp/bot_fsm_tmp/...`
3. 明确谁负责最终清理，避免 FSM 和 `TaskService` 之间职责含糊
4. 给 `receive_prompt(...)` 增加注释，明确说明先 `pop image_path` 再 `_cleanup_context(...)` 的意图不是“提交后立即删图”

这样可以避免后续维护者误判当前生命周期设计，也能防止临时文件长期残留。

### 方案 D：补充回归测试

建议增加三类测试：

1. `_process_input_path(...)` / `save_input_image(...)` 单测
   - 当传入本地路径但文件不存在时，应明确失败，而不是返回原路径

2. worker 输入处理单测
   - 当 MinIO 下载输入失败时，应直接中止任务，而不是继续 patch workflow
   - 当上传到 ComfyUI API 失败时，也应直接中止

3. 临时文件清理测试
   - 验证 `custom_video` 以及同类视频 FSM 任务结束后，本地临时图能被正确清理

## 8. 推荐修复顺序

建议按这个顺序处理：

1. 先修 `task_core.py` 的输入路径校验
2. 再修 worker 的输入下载失败处理
3. 再统一 FSM 临时目录与清理逻辑
4. 最后补回归测试和必要注释

如果后续又观察到“文件在上传前就被实际删除”的日志证据，再单独回头审视文件生命周期问题。

## 9. 预期修复结果

修复完成后，这类视频链路应该满足：

- bot/core 不会再把本地临时路径当成合法输入继续往下传
- 下游只会收到合法的 MinIO Object Key
- worker 遇到非法对象 key 或输入上传失败，会在输入处理阶段直接失败
- ComfyUI 不再因为脏输入走到 `LoadImage` 才报 `400`
- 用户侧失败信息更接近真实原因
- 本地临时文件在任务结束后能被稳定清理

## 10. 一句话结论

按当前代码来看，`custom_video` 这次问题的更严谨表述应为：

**最早可确认的直接缺陷，是 bot/core 在输入上传失败时把原始本地路径继续透传；worker 的 fail-fast 缺失则放大了这个问题，使错误延后到 ComfyUI 的 `LoadImage` 阶段才暴露。与此同时，FSM 临时目录与统一清理目录不一致，构成了一个独立但同样需要修补的共享清理缺口。**
