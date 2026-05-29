# Debug Session: wan22-video-output [OPEN]

## Symptoms
- Web 端 `wan22_video_v2` 任务 `b2249682-5154-4db5-a169-c739feff809e` 出现 `stream` 请求中断。
- 主视频 URL `https://r2-test.aivison.it.com/history/b2249682-5154-4db5-a169-c739feff809e/original.mp4` 请求失败。
- 页面能看到尾帧图片，但视频播放失败。
- 用户在 ComfyUI 节点侧观察到只输出了图片，但耗时约 140 秒。

## Expected
- 同一任务应产出主视频，并在开启 `extract_last_frame` 时额外产出尾帧图片。

## Initial Hypotheses
- H1: ComfyUI 工作流实际没有产出视频，worker 误把图片链路当成成功结果处理。
- H2: ComfyUI 同时产出视频和尾帧，但 worker 在 history 解析或上传阶段只拿到了图片资产。
- H3: 主视频已由 worker 上报，但 Web 历史持久化或 R2 warmup 没落到 `original.mp4`，导致前端访问 404/abort。
- H4: `/api/tasks/{id}/stream` 中断并非根因，而是任务已进入终态/持久化异常后的前端表现。
- H5: `wan22_video_v2` 的主结果选择逻辑与 `extract_last_frame` 支路之间仍有节点或结果键优先级冲突。

## Evidence To Collect
- central-api / worker / web-api 对该 task_id 的运行日志
- history 表该 task_id 的 `output_file` 与 `extra_outputs`
- MinIO / R2 上该 task_id 的实际对象存在情况
- ComfyUI history 返回的 outputs 结构

## Status
- Session initialized, collecting runtime evidence only.

## Evidence Collected
- `GET /status/b2249682-5154-4db5-a169-c739feff809e` 返回：
  - `status=done`
  - `result_path=b2249682-5154-4db5-a169-c739feff809e__wan22_video_v2_324490337883535_last_frame_00001_.png`
  - `extra_outputs.last_frame.path` 与 `result_path` 相同
- `history` 表记录：
  - `type=wan22_video_v2`
  - `output_file=44/output_images/b2249682-5154-4db5-a169-c739feff809e.mp4`
  - `extra_outputs.last_frame.path=b2249682-5154-4db5-a169-c739feff809e__wan22_video_v2_324490337883535_last_frame_00001_.png`
- MinIO 对象头校验：
  - `comfyui-temp-test/<result_path>` 的字节头是 PNG (`89 50 4E 47`)
  - `bot-data-test/44/output_images/...mp4` 的字节头也是 PNG，但 content-type 被写成 `video/mp4`
- `central-api-test` 日志显示 `/video/{task_id}` 实际从 MinIO 拉取的是 `...last_frame_00001_.png`

## Hypothesis Status
- H1 Rejected: 不能仅说“ComfyUI 只输出了图片”，因为系统已进入视频任务成功落库链。
- H2 Confirmed: worker 结果选择/上报链把图片资产当成主结果。
- H3 Confirmed-partial: history 的 `.mp4` 实际承载的是 PNG 字节，持久化链被错误主结果污染。
- H4 Rejected: `stream` abort 不是根因，是错误终态结果的表象。
- H5 Confirmed: `extract_last_frame` 支路与主结果选择逻辑存在覆盖冲突。

## Minimal Fix Applied
- `workers/comfy_agent/agent_main.py`
  - `_pick_first_output_asset(...)` 改为“先按资产类型优先级，再遍历节点”，对 `wan22_video_v2` 全局优先 `videos -> gifs -> images`
  - 新增 `_result_asset_priority(...)`，给 `wan22_video_v2` 的 WS `executed` 结果选择增加优先级门禁，防止尾帧图片覆盖已选中的视频结果
  - `history` 回查命中主结果后，同步刷新 `self.task_result` 与优先级
  - 上传前对 `wan22_video_v2` 强制以 `history_result.safe_name` 作为最终主结果真值

## Verification Status
- Static verification:
  - `python -m py_compile workers/comfy_agent/agent_main.py` passed
  - `pytest -q tests/workers/test_comfy_agent.py tests/workers/test_workflow_patcher.py` passed (`9 passed`)
- Runtime verification:
  - 已重建并替换测试 worker `comfy-agent-test-5`
  - 已提交 post-fix 任务 `8ef3931e-2e93-445e-a3b4-37d885ff06ff`
  - 该任务最终失败，`GET /status/8ef3931e-2e93-445e-a3b4-37d885ff06ff` 返回：
    - `status=error`
    - `progress=1.0`
    - `error=Result processing failed: <urlopen error [Errno 111] Connection refused>`
  - `comfy-agent-test-5` 日志显示：
    - `20:29:50 Failed to fetch history: <urlopen error [Errno 111] Connection refused>`
    - 随后 `Task ... failed: Result processing failed: <urlopen error [Errno 111] Connection refused>`
  - 该错误由本次调试插桩访问 Debug Server 时连接被拒绝触发，导致“获取 history / 结果处理”阶段被异常打断
  - 结论：这条 post-fix 样本不是有效业务验证结果，需移除或降级调试插桩的失败影响后重新复跑

## Third-Round Evidence
- 对比两台 Comfy 实例：
  - `177:8188` 正常视频样本 `086559ae-106d-4b6c-bfed-756c3f134c6e`
    - `outputs_to_execute=["290"]`
    - `history.outputs["290"].gifs[0].filename="AnimateDiff_156600.mp4"`
  - `252:8189` 异常 `wan22` 样本 `a61aa188-e546-4900-93f6-352e1e68ea20`
    - `outputs_to_execute=["2573","2547","2623","2501","2615","2602","2624","2601","2584","2548","2605"]`
    - `history.outputs` 只有 `2503.images`，主视频节点 `28` 未进入执行输出集合
- `252:8189` 的节点 schema 显示：
  - `VHS_VideoCombine.output_node=true`
  - `PreviewAny.output_node=true`
  - `SaveImage.output_node=true`
  - `DaSiWa_NodeStatusSwitch.output_node=true`
- 结论：`wan22` 的 `outputs_to_execute` 只包含一批 utility/switch 输出节点，不是 worker 读取错误，而是提交给 Comfy 的这张图本身没有把 `28` 视为最终执行输出。

## Probe Results
- 极简探针 `LoadImage -> VHS_VideoCombine`
  - `177:8188`：`outputs_to_execute=["2"]`，正常输出 mp4
  - `252:8189`：最终也能输出 mp4，`history.outputs["2"].gifs[0].filename="trae_vhs_probe_...mp4"`
- 带尾帧支路探针 `VHS_VideoCombine + ImageFromBatch + SaveImage`
  - `252:8189`：`outputs_to_execute=["4","2"]`
  - 同时输出 `2.gifs(mp4)` 与 `4.images(png)`
- 增量探针继续接回 `wan22` 的关键公共链路后仍然正常：
  - `VHS_GetImageCount + ComfyMathExpression(frame_rate)` 正常
  - `BatchResizeWithLanczos` 正常
  - `DaSiWa_NodeStatusSwitch` 正常
  - `ComfySwitchNode` 正常
  - 额外挂一个未接 `images` 的坏 `VHS_VideoCombine` 输出节点，也不会打掉正常 mp4 输出

## Current Conclusion
- 已证伪：
  - 不是 `VHS_VideoCombine` 节点在 `252` 上整体失效
  - 不是“同时要视频 + 尾帧”这个模式导致 mp4 被排除
  - 不是 `frame_rate` 动态计算链导致 `28` 消失
  - 不是 `BatchResizeWithLanczos` / `DaSiWa_NodeStatusSwitch` / `ComfySwitchNode` 单独存在就会打掉视频输出
- 当前最可能根因：
  - `WAN 2.2 i2v -AiO.json` 的完整 API 图里，存在一组只服务 UI 调试/预览/模式切换的输出节点组合，使新版 Comfy 0.22 在收集 `outputs_to_execute` 时优先保留了这些 utility 输出，而未把主视频节点 `28` 纳入最终执行输出集合。
- 下一步修法建议：
  - 在 `workflow_patcher._patch_wan22_video_v2()` 中增加“API 精简拓扑”步骤：
    - 删除纯预览输出节点，如 `2547`、`2548`、`2587`、`2589`
    - 如有必要，进一步移除不会影响推理结果、但会作为 `output_node` 参与收集的 UI 辅助节点
  - 目标不是改 worker 结果协议，而是让提交到 Comfy 的最终图重新满足：
    - `outputs_to_execute` 至少包含 `28`
    - `history.outputs` 同时出现主视频和尾帧图片

## Third-Round Patch Applied
- `workers/comfy_agent/workflow_patcher.py`
  - 新增 `WAN22_VIDEO_V2_REMOVABLE_NODE_IDS`
  - `wan22_video_v2` patch 时移除：
    - `9` (`VHS_PruneOutputs`)
    - `2502`（mini gif preview）
    - `2547`、`2548`、`2587`、`2589`（`PreviewAny`）
    - `2623`、`2624`（无业务作用的 mute toggle）
- 定向验证：
  - `pytest -q tests/workers/test_workflow_patcher.py tests/workers/test_comfy_agent.py` passed
  - `python -m py_compile workers/comfy_agent/workflow_patcher.py` passed
- 测试环境发布：
  - 已重建 `comfy-agent-test-5`
  - 期间发现 `docker-compose` 插值没有读取 `.env.test` 的真实 `AGENT_SECRET_TOKEN`，导致新容器初次启动对 `8004` 拉任务返回 `401`
  - 已用测试 token 显式重建同一容器，随后日志恢复 `GET /api/agent/task/pop -> 200` 与 `heartbeat -> 200`

## Third-Round Runtime Signal
- 使用当前仓库代码直接生成 patched `wan22_video_v2` prompt 并提交到 `252:8189`
  - `prompt_id=8e7d472a-0f47-496f-b049-566ad8aec5bc`
  - `queue_pending` 中的 `outputs_to_execute` 变为：
    - `["2573", "2501", "2615", "2602", "2503", "28", "2601", "2584", "2605"]`
- 这是本次调试里第一次确认：
  - `28` 已重新进入 `outputs_to_execute`
  - `2503` 尾帧支路仍保留在终端输出集合中
- 结论：
  - 第三轮“API 精简拓扑”修法至少命中了核心中间指标
  - 还需等待该 prompt 真正跑完，确认 `history.outputs` 是否最终同时出现主视频和尾帧

## Fourth-Round Evidence
- 针对真实测试任务 `probe-d0d2d7896d5948118cbfef04c0f79eda`
  - `prompt_id=296fb3b0-78f9-4a5f-ac91-22f622cd0994`
  - 最终 backend 状态：
    - `status=error`
    - `error="Task completed but no result path found"`
  - `GET /history/{prompt_id}` 与 `GET /api/jobs/{prompt_id}` 结果一致：
    - `outputs_count=1`
    - 仅有 `2503.images`
    - `preview_output.nodeId="2503"`
    - 主视频节点 `28` 无任何输出条目
- 直接访问 `/view` 猜测 `wan22_video_v2_254956149004195_video_00001.mp4` 等文件名全部 `404`
  - 说明不是“history 丢了，但磁盘上其实有 mp4”
  - 当前是 `28` 对应 mp4 本身没有被落出来

## Fourth-Round Probe Findings
- `252:8189` 上 `VHS_VideoCombine` 的 schema 显示：
  - `frame_rate.min = 1`
  - `frame_rate.step = 1`
- 独立探针验证：
  - `frame_rate=0` 或 `0.0` 时，任务成功但 `outputs=null`
  - `frame_rate=0.2` 时，只输出尾帧 `SaveImage`，不输出 mp4
  - `frame_rate>=1` 的极简探针可以输出 mp4
- 结论：
  - `wan22` 原工作流的 `2581 = (a - 1) / b` 在 `252` 环境下确实存在“生成 `<1` fps 导致视频静默不产出”的真实风险
  - 但这不是全部根因；把已有 prompt 的 `28.frame_rate` 强行改成 `1.0` 后，真实 `wan22` 图仍然没有落出主视频

## Fourth-Round Patch Applied
- `workers/comfy_agent/workflow_patcher.py`
  - 在 `_patch_wan22_video_v2()` 中新增：
    - `2581.expression = "max(1, round(( a - 1 ) / b))"`
  - 含义：
    - 保留“按帧数推导时长”的原意
    - 但把 fps 收口到 `>=1` 的整数，匹配 `252` 上 `VHS_VideoCombine` 的节点约束
- 定向测试：
  - `pytest -q tests/workers/test_workflow_patcher.py tests/workers/test_comfy_agent.py` passed
  - `python -m py_compile workers/comfy_agent/workflow_patcher.py` passed

## Current Working Theory
- 已确认的真实问题有两层：
  1. `wan22` 的动态 fps 公式与 `252` 上 `VHS_VideoCombine` 的最小值/整数约束不兼容
  2. 即便修掉 fps 约束冲突，这张完整 WAN 图里的 `DaSiWa_NodeStatusSwitch` / 输出拓扑仍会让主视频节点 `28` 无法稳定成为最终物化输出
- 当前仍在验证：
  - 是否可以通过进一步简化/重写 API 提交图中的 switch 输出拓扑，让 `28` 真正落出 mp4

## Root Cause Confirmed
- `252:8189` 上 `DaSiWa_NodeStatusSwitch` 的 schema 明确为：
  - `output_node = true`
- 这意味着当原始 WAN UI 图直接作为 API prompt 提交时：
  - `2501 / 2573 / 2584 / 2615 / 2601 / 2602 / 2605`
  - 这些 UI 状态开关会被 Comfy 当成最终输出节点
  - 导致 `outputs_to_execute` 被它们占满，`28` / `2503` 无法稳定进入最终输出收集
- 进一步证据：
  - 仅移除性能开关 `2601/2602/2605` 时，`outputs_to_execute` 收缩为 `['2573', '2615', '2584', '2501']`
  - 说明真正劫持输出收集的正是这批 `DaSiWa` 开关节点

## API Rewire Experiment
- 直接从失败样本 `24c4ca93-01c8-4448-b751-d552bfdc2b7f` 的 prompt 出发：
  - 去掉全部 `DaSiWa_NodeStatusSwitch`
  - 将 `use_end_frame=false` 时的 `24.image` 回填为起始图，避免 `LoadImage(None)` 校验失败
  - 按 bypass 语义直接把 `28.images` 和 `2700.image` 接到真实帧序列输出
- 对照样本：
  - `prompt_id=d7b6371a-2027-4469-a2ec-32d9f7f2ef6d`
- 结果：
  - `outputs_to_execute = ['2503', '28']`
  - `outputs` 同时包含：
    - `2503.images`
    - `28.gifs -> mp4`
- 结论：
  - 根因不是 `VHS_VideoCombine` 本身失效
  - 而是原工作流中的 UI 开关节点不适合作为 API 执行图直接提交

## Final Fix Applied
- `workers/comfy_agent/workflow_patcher.py`
  - 将 `2501 / 2573 / 2584 / 2615 / 2601 / 2602 / 2605 / 2623 / 2624` 统一视为 API 模式下应移除的 UI-only 输出节点
  - 保留并继续使用 `2557` 这个真正的数据分支开关（`ComfySwitchNode`，非 output node）
  - 根据布尔参数直接重写真实连线：
    - `color_match=false` 时，将 loop 链输入从 `2614` 改为 `2612`
    - `perfect_loop=false` 时，视频链直接跳过 `2542/2543/2558/2574`
    - `upscale=false` 时，`28` 和 `2700` 直接吃未放大的帧序列
    - `extract_last_frame=false` 时，直接删除 `2503/2700`
    - `use_end_frame=false` 时，把 `24.image` 回填为起始图，防止 API 校验触发 `LoadImage(None)`

## Verified Real Task
- 新镜像发布到测试 worker 后，真实 backend 样本：
  - `task_id=probe-53c4558c0e4542dbac4f1a7536fe9c5c`
  - `prompt_id=48d16890-1dba-4886-9a40-a67d66205593`
- 最终结果：
  - backend `/status/{task_id}`:
    - `status=done`
    - `result_path=...video_00001.mp4`
    - `extra_outputs.last_frame.path=...last_frame_00001_.png`
  - Comfy `/api/jobs/{prompt_id}`:
    - `outputs_count=2`
    - `outputs.28.gifs[0].filename = wan22_video_v2_668187022124171_video_00001.mp4`
    - `outputs.2503.images[0].filename = wan22_video_v2_668187022124171_last_frame_00001_.png`

## Current Status
- `wan22_video_v2` 的测试主链已恢复：
  - backend -> queue -> worker -> Comfy -> history/jobs -> backend result
- 当前默认验证通过的是：
  - `use_end_frame=false`
  - `color_match=false`
  - `perfect_loop=false`
  - `upscale=false`
  - `extract_last_frame=true`
- 下一步建议：
  - 继续做 1-2 组非默认开关组合的真实复跑
  - 若这些也通过，即可通知用户去 Web 测试验收

## Extra Regression Runs
- 真实回归组 1：
  - `task_id=probe-26ef6cf4c3e54526a710953a9383c7e8`
  - `prompt_id=bd94a87c-21ed-46a0-ab94-684d538082f1`
  - 参数：
    - `use_end_frame=false`
    - `color_match=true`
    - `perfect_loop=true`
    - `upscale=false`
    - `extract_last_frame=true`
  - 结果：
    - backend `status=done`
    - `/api/jobs/{prompt_id}`:
      - `outputs_count=2`
      - `28.gifs[0].filename = wan22_video_v2_375979853239007_video_00001.mp4`
      - `2503.images[0].filename = wan22_video_v2_375979853239007_last_frame_00001_.png`

- 真实回归组 2（首次失败）：
  - `task_id=probe-fee9bd2ec0f24f499c4ee7f917004ea2`
  - 参数：
    - `use_end_frame=true`
    - `color_match=false`
    - `perfect_loop=false`
    - `upscale=true`
    - `extract_last_frame=true`
  - 初次失败原因：
    - worker `_prepare_task_inputs()` 漏掉 `end_image`
    - 导致 `24.image` 仍是原始对象键 `13/input_images/...png`
    - Comfy `/prompt` 校验失败：
      - `node_errors.24.details = "image - Invalid image file: 13/input_images/...png"`

## Final Follow-up Fix
- `workers/comfy_agent/agent_main.py`
  - 在 `_prepare_task_inputs()` 的附加输入处理列表中加入 `end_image`
  - 让 `use_end_frame=true` 时的第二张图也会执行：
    - MinIO 下载
    - 本地安全文件名替换
    - Comfy `/upload/image`
    - 参数回填为本地化文件名
- `tests/workers/test_comfy_agent.py`
  - 增加静态回归断言，确保 `end_image` 不再从输入准备列表中漏掉

## Extra Regression Runs After Fix
- 真实回归组 2（修复后复跑）：
  - `task_id=probe-fbecc9786c0040939fba0be7bdcaa5c8`
  - `prompt_id=afa4da21-7d0a-45af-8a40-480befa0301d`
  - 结果：
    - backend `status=done`
    - `result_path=...wan22_video_v2_550670548067897_video_00001.mp4`
    - `extra_outputs.last_frame.path=...wan22_video_v2_550670548067897_last_frame_00001_.png`
    - `/api/jobs/{prompt_id}`:
      - `outputs_count=2`
      - `28.gifs[0].filename = wan22_video_v2_550670548067897_video_00001.mp4`
      - `2503.images[0].filename = wan22_video_v2_550670548067897_last_frame_00001_.png`

## Updated Validation Scope
- 当前已通过真实测试的组合至少包括：
  - 默认主线：
    - `use_end_frame=false`
    - `color_match=false`
    - `perfect_loop=false`
    - `upscale=false`
    - `extract_last_frame=true`
  - 增强组合 A：
    - `color_match=true`
    - `perfect_loop=true`
  - 增强组合 B：
    - `use_end_frame=true`
    - `upscale=true`
