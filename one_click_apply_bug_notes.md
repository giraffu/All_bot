# 一键应用 Bug 记录：LTX Video 时长恢复与扣费不稳

本文档只聚焦 1 个问题：

- `ltx_video` 在一键应用链路中的时长恢复不稳定，可能导致恢复出更低时长，并进一步造成低扣费

不展开讨论其他模板类型，也不讨论 TG 广场白名单扩展等旁支问题，避免范围漂移。

---

## 结论

按当前代码，`ltx_video` 的问题本质上是两件事叠加：

1. 提交给 Worker 时把“秒”直接当成了 `length`
2. 历史恢复链缺少稳定的“请求时长 canonical”

因此它不是单纯的“计费兜底异常”，而是一个从**任务提交**到**历史落库**再到**Web / TG 一键应用恢复**的链路问题。

当前修复重点应明确为：

1. 先修提交语义错误
2. 再补稳定的请求时长字段
3. 明确“新数据只信数据库，旧前缀只做兼容”
4. 最后统一恢复优先级与旧数据兼容

---

## 当前代码下的已确认事实

### 1. LTX 提交时把秒数直接传给了 Worker `length`

代码链路：

- [task_dispatcher.py](file:///home/hfy/APP/All_bot/src/core/task_dispatcher.py#L280-L309)
- [image_service.py](file:///home/hfy/APP/All_bot/src/services/image_service.py#L22-L40)
- [api_client.py](file:///home/hfy/APP/All_bot/src/api_client.py#L349-L377)

其中：

- `submit_ltx_video()` 默认 `length=241`
- 这已经明显体现 `length` 是帧语义
- 但当前 `LtxVideoStrategy.submit_task()` 仍把 `5/10/20` 这种秒数直接传进去

也就是说，当前实现实际存在“秒传帧”的提交错误。

### 2. 视频完成后写入历史的 `duration` 是输出媒体元数据，不是请求档位

代码位置：

- [task_service.py](file:///home/hfy/APP/All_bot/src/services/task_service.py#L1457-L1480)
- [logger.py](file:///home/hfy/APP/All_bot/src/logger.py#L125-L183)

当前完成链路会在下载成片后探测媒体信息，并把 `width / height / duration` 写入 `History`。

这里的 `duration` 语义是：

- 输出成片的媒体时长
- 或最佳努力探测值

它并不是稳定的“用户原始请求时长档位”。

### 3. Web apply-context 会把数据库中的 `duration` 暴露给前端作为恢复来源之一

代码位置：

- [users.py](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L699-L747)
- [templateVideoApplyState.ts](file:///home/hfy/APP/All_bot/frontend/src/utils/templateVideoApplyState.ts#L55-L96)

也就是说，Web 一键应用当前在恢复 LTX 模板时，确实可能使用历史中的 `duration`。

但上面已经确认，这个 `duration` 目前只是历史表中的媒体元数据/最佳努力值，不是请求档位 canonical，因此它只能算补充来源，不能算稳定恢复依据。

### 4. TG 广场 apply 对 LTX 仍优先依赖 prompt 前缀

代码位置：

- [gallery_apply_fsm.py](file:///home/hfy/APP/All_bot/src/handlers/fsm/gallery_apply_fsm.py#L141-L160)

当前逻辑会解析：

- `[resolution|duration] prompt`

若解析不到前缀，则直接回退：

- 分辨率：`1280x704`
- 时长：`5s`

### 5. `process_ltx_video_task()` 保存历史时不会把 `[resolution|duration]` 前缀写回 prompt

代码位置：

- [process_ltx_video_task](file:///home/hfy/APP/All_bot/src/services/task_service.py#L59-L168)

对比模板视频专用入口，后者在保存历史时会显式写回前缀：

- [_process_video_task_template](file:///home/hfy/APP/All_bot/src/services/task_service.py#L771-L785)

这意味着当前 LTX 自己的专用提交流程，并没有给 TG 广场 apply 留下稳定的 prompt 前缀恢复依据。

同时还要注意一个实现边界：

- Web apply-context 当前不会剥离 `[resolution|duration]` 前缀
- 前端工作台会直接把返回的 `prompt` 原样回填

因此旧前缀只能作为 **TG 旧历史兼容来源**，不能继续被当成新的跨端 canonical，也不建议再把结构化参数回写进新 prompt。

### 6. 当前没有稳定的请求时长字段

现有历史相关字段里：

- `billing_resolution` 已承担请求分辨率 canonical 职责
- `width / height / duration` 主要承载输出媒体元数据或最佳努力探测值

但当前没有稳定的：

- `requested_duration`

因此 LTX 的时长恢复目前会在以下来源之间摇摆：

- prompt 前缀
- 数据库中的媒体元数据 `duration`
- 默认值 `5s`

这就是恢复不稳定的根本原因。

---

## 问题如何形成

以 `ltx_video 20s` 为例，当前问题链路可以概括为：

1. 用户请求的是 `20s`
2. 提交阶段却把 `20` 直接作为 Worker `length`
3. Worker 侧 `length` 实际是帧语义，生成结果与“20 秒请求”不一致
4. 完成后历史里写入的是成片实际 `duration`，而不是请求时长档位
5. Web / TG 一键应用恢复时，又分别从数据库中的媒体元数据或 prompt 前缀里尝试还原时长
6. 一旦前缀缺失、元数据异常或历史不完整，就可能回退到更低档位
7. 最终表现为：恢复时长变低，扣费也随之变低

所以这个 bug 的主修点不是“只在计费时兜底补丁”，而是要把**提交语义**和**恢复 canonical**一起修正。

---

## 字段语义约束

为了避免修复时继续混淆字段职责，本文统一按下面语义描述：

### 1. `billing_resolution`

- 当前继续作为请求分辨率 canonical
- 普通视频任务存 `512/720/1024`
- `ltx_video` 存精确分辨率，如 `1280x704`

在当前问题范围内，不建议并行新增 `requested_resolution`。

### 2. `requested_duration`

- 建议新增的请求时长 canonical
- 表达的是用户选择的模板请求档位
- 不表达成片真实时长
- 新数据恢复时应优先读取它，而不是继续猜测 prompt 或媒体元数据

### 3. `width / height / duration`

- 统一理解为输出媒体元数据或最佳努力探测值
- 只能作为兼容读取时的补充来源
- 不应直接等同于模板请求参数

### 4. `prompt` 中的 `[resolution|duration]` 前缀

- 只作为 **旧历史 / TG legacy** 的兼容读取来源
- 不作为新任务的 canonical 存储位置
- 不建议继续把结构化视频参数写回新 prompt
- Web 侧不应再依赖它恢复新任务参数

---

## 推荐修复

### 1. 先修提交语义

把 LTX 提交给 Worker 的 `length` 改成明确帧数：

- `length = duration_seconds * 24 + 1`

也就是：

- `5s -> 121`
- `10s -> 241`
- `20s -> 481`

这一步是必须先做的，因为它直接决定新任务写入历史时是否继续制造脏数据。

### 2. 新增 `requested_duration`

只新增：

- `requested_duration`

不建议同时新增：

- `requested_resolution`

原因是：

- 当前 `billing_resolution` 已可继续承担分辨率 canonical
- 本次问题的核心缺口在“时长没有稳定 canonical”
- 同时引入两个 canonical 字段会扩大改动面，也更容易制造双真相源

### 3. 明确新旧数据边界

统一约束为：

- 新任务时长参数一律以数据库字段 `requested_duration` 为准
- 旧的 prompt 前缀只做历史兼容，不再作为新数据真相源
- 新任务不再依赖 prompt 前缀恢复时长
- 只有旧历史缺少结构化字段时，TG legacy 才允许回退读前缀

这是本次修复必须写清楚的边界，否则很容易出现“写入数据库了，但读取时还是先信前缀”的双真相源问题。

### 4. 统一 LTX 恢复优先级

LTX 时长恢复不能再只写一套笼统优先级，而应区分新数据与旧兼容：

对于 **新数据**：

- `requested_duration > 数据库中的媒体 duration > 默认值`

LTX 分辨率恢复建议统一为：

- `billing_resolution > width/height`

其中：

- prompt 前缀只作为旧历史/TG legacy 过渡兼容来源
- 媒体元数据只作为后置补充来源
- 默认值只能放在所有来源都缺失时最后兜底

对于 **旧历史兼容**：

- Web: `requested_duration > 数据库中的媒体 duration > 默认值`
- TG legacy: `requested_duration > prompt 前缀 > 默认值`

也就是说：

- Web 新链路不应再依赖 prompt 前缀
- TG 若未来接入结构化字段，也应优先读数据库，再把前缀降级为兼容兜底

### 5. 新写路径优先写干净

新任务完成时，应同步落稳定模板参数，避免继续依赖读路径修复。

至少要保证：

- 新 LTX 历史能稳定得到 `billing_resolution`
- 新 LTX 历史能稳定得到 `requested_duration`

这样 Web / TG 恢复才能逐步从“猜测恢复”切到“按 canonical 恢复”。

另外需要明确，当前存在两条历史写入链，修改时不能只修一边：

- Web 完成链路
- TG / Bot 完成链路

如果只在其中一条链上写 `requested_duration`，最终仍会出现同类任务因来源不同而恢复结果不一致。

### 6. 旧历史只做有限兼容

过渡期不建议做无依据的全量回填。

只在能从可靠来源确定原始请求时长时，才回填：

- `requested_duration`

不应做的事：

- 仅凭 `History.duration` 批量反推请求档位
- 把当前媒体元数据一律视为历史请求时长
- 继续把 prompt 前缀当作新任务的主恢复来源

---

## 不建议的修法

以下修法看起来快，但都容易留下隐患：

### 1. 只在计费阶段对 `"1s"`、`"19s"` 等值做特殊归一化

这只能缓解扣费异常，不能修正恢复链和历史脏数据来源。

### 2. 只修秒转帧，不补 `requested_duration`

这只能保证新任务不再继续制造同类问题，但旧历史和跨端恢复仍会继续不稳定。

### 3. 把 `History.duration` 一律当成旧历史请求时长

这会把输出媒体元数据误当成模板 canonical，继续放大历史脏值。

### 4. 继续把 prompt 前缀当成新数据主真相源

这会导致数据库字段和 prompt 前缀并存，形成双真相源；同时 Web 端当前并不会剥离该前缀，容易把结构化参数污染到用户 prompt。

### 5. 额外引入 `requested_resolution`

本问题当前没有必要扩大到分辨率字段重构；若并行新增，会抬高修改复杂度。

---

## 推荐落地顺序

### 第一阶段

1. 修 `ltx_video` 秒转帧
2. 保持 `billing_resolution` 继续承担分辨率 canonical

### 第二阶段

3. 新增 `requested_duration`
4. Web 与 TG 两条写入链都写入稳定时长 canonical
5. 新数据统一优先读取 `billing_resolution + requested_duration`
6. 明确 prompt 前缀仅用于旧历史兼容，不再参与新数据主链

### 第三阶段

7. 为旧历史保留兼容读取顺序
8. 只对有可靠证据的历史回填 `requested_duration`
9. 避免把媒体元数据直接升级为 canonical

---

## 最低回归集

### 核心回归

- 生成一个 `ltx_video 20s` 任务，再次一键应用后，仍恢复为 `20s`
- 同一任务再次一键应用时，扣费仍按 `20s` 档位计算
- TG 广场 apply 对缺少 prompt 前缀的 LTX 历史，不再直接回退到 `5s`
- Web 与 TG 对同一条具备 canonical 时长的 LTX 历史，恢复出一致时长
- `5s / 10s / 15s / 20s` 四个档位都应验证秒转帧结果分别为 `121 / 241 / 361 / 481`
- 新历史在数据库中已有 `requested_duration` 时，Web 与 TG 都优先读数据库，不再优先信 prompt 前缀

### 旧历史兼容

- 旧历史缺少 `requested_duration` 时，仍可通过兼容路径恢复
- 兼容恢复不得把明显异常的媒体 `duration` 直接固化成 canonical
- 旧历史允许 TG 从 prompt 前缀兜底恢复，但该逻辑不得反向污染 Web prompt 展示/回填

### 至少应覆盖的测试文件

- [templateVideoApplyState.test.ts](file:///home/hfy/APP/All_bot/frontend/src/utils/templateVideoApplyState.test.ts)
- [test_users_apply_context.py](file:///home/hfy/APP/All_bot/tests/web_api/test_users_apply_context.py)
- [test_gallery_apply_context.py](file:///home/hfy/APP/All_bot/tests/web_api/test_gallery_apply_context.py)
- [gallery_apply_fsm.py](file:///home/hfy/APP/All_bot/src/handlers/fsm/gallery_apply_fsm.py) 对应的 TG apply 用例
- [task_core.py](file:///home/hfy/APP/All_bot/src/core/task_core.py) 对应的 Web 历史写入用例

---

## 最终结论

按当前代码，这个 bug 的正确修复顺序应是：

1. 先修 `ltx_video` 秒转帧
2. 再补 `requested_duration`
3. 保留 `billing_resolution`，不新增 `requested_resolution`
4. 新数据统一以数据库字段恢复，旧前缀只做历史兼容
5. 最后统一 Web / TG 的 LTX 恢复优先级，并对旧历史做有限兼容

一句话概括：

- 这个问题的本质不是“计费倍率兜底不够”，而是“提交语义错误 + 时长 canonical 缺失”共同导致的一键应用恢复不稳；其中新数据应统一信数据库，旧前缀只做兼容
