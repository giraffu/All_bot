# 代码静态分析与质量评估报告

## 📊 核心量化指标

- **分析范围**: `src/`, `backend/`, `workers/`, `cs_bot/`, `frontend/src/`
- **代码总行数 (LOC)**: ~33,734 行 (仅计算后端与脚本部分)
- **平均圈复杂度 (Cyclomatic Complexity)**: **4.38 (A级)** - 整体处于优秀水平，但局部存在极高复杂度的方法。
- **代码重复率 (Duplication Rate)**: **17.69%** (其中 JSON 配置高达 44.69%，Vue 前端 27.19%，Python 后端 6.34%)
- **死代码比例 (Dead Code Ratio)**: 约 **2.3%** (~800行)

---

## 🚨 问题详细分类

### 1. 架构问题 (Architecture Issues)
**严重程度: High**

* **违反单一职责原则与过度耦合**
  * **文件/模块**: `workers/agent.py`
  * **行号**: ~278 (`ComfyAgent.process_task` 方法)
  * **描述**: 该方法圈复杂度评级为 **F**，包含了大量的分支判断和复杂的任务处理逻辑，业务逻辑与网络通信逻辑深度耦合。
  * **重构建议**: 采用**策略模式 (Strategy Pattern)**。将不同类型的任务处理逻辑抽离到独立的 Handler 类中（如 `ImageTaskHandler`, `VideoTaskHandler`），`ComfyAgent` 仅负责调度和状态汇报。
* **FSM (状态机) 逻辑过载**
  * **文件/模块**: `src/handlers/fsm/utils.py` (`process_and_submit_task`), `src/handlers/callbacks/gallery_callbacks.py` (`gallery_sort_page_callback`)
  * **描述**: 圈复杂度分别达到 **E** 和 **F**。状态机和回调中混合了过多的校验、数据组装和业务逻辑。
  * **重构建议**: 将复杂的业务校验与数据组装下沉至 `src/services/` 层，Handler/FSM 层仅保留参数获取、Service 调用与返回结果的视图格式化。

### 2. 代码坏味道 (Code Smells)
**严重程度: Medium**

* **过长的函数/过深的嵌套**
  * **文件**: `src/handlers/callbacks/gallery_callbacks.py` (Line ~339: `gallery_sort_page_callback` - 评级 F)
  * **文件**: `src/services/task_service.py` (Line ~1090: `_handle_task_completion` - 评级 E)
  * **文件**: `workers/comfy_agent/workflow_patcher.py` (Line ~159: `heuristic_patch` - 评级 E)
  * **描述**: 函数体积庞大，包含多层 `if-else` 或 `try-except` 嵌套，极难维护。
* **单行语句过多**
  * **描述**: Ruff 检测到 23 处 `E701 (Multiple statements on one line)` 错误。
  * **建议**: 使用 Black 或 Ruff formatter 进行全代码格式化。

### 3. 性能问题 (Performance Issues)
**严重程度: High**

* **同步操作阻塞事件循环**
  * **文件**: `src/api_client.py` (Line 308: `listen_for_progress` - 评级 D)
  * **描述**: 此处复杂度较高且处理长链接/流式监听，若在其中混入任何同步阻塞调用（如文件IO或同步网络请求），会导致整个异步事件循环被阻塞。
* **频繁的重复文件解析 (JSON)**
  * **描述**: 多个工作流文件 (`perfect_video_insert.json`, `perfect_video_edit.json`, `Qwen-Rapid-AIO.json`) 存在极高的代码重复度（超过 1500 tokens 重复）。这不仅是代码冗余，在每次加载工作流时也会带来额外的解析开销。

### 4. 代码重复 (Code Duplication)
**严重程度: Medium**

* **Vue 前端高度相似的组件**
  * **文件**: `frontend/src/views/FaceSwap.vue` vs `frontend/src/views/VideoSwap.vue`
  * **行号**: 跨越数百行，高达 27% 的重复率。
  * **描述**: 大量标记和逻辑被直接复制粘贴。
  * **建议**: 提取可复用的组合式 API (`useSwapLogic.ts`) 以及公共 UI 组件 (`UploadArea.vue`, `ResultPreview.vue`)。
* **FSM 状态机逻辑复制粘贴**
  * **文件**: `src/handlers/fsm/quick_video_fsm.py` vs `src/handlers/fsm/video_lora_fsm.py`
  * **描述**: 存在高达 30 行以上 (347 tokens) 的完全一致逻辑。
  * **建议**: 抽取公共的状态基类或混合类 (Mixin) 来处理公共的步骤（如“接收提示词”、“接收参考图”）。

### 5. 作用域分析 (Scope Analysis)
**严重程度: Low**

* **变量覆盖与重定义**
  * **文件**: `src/handlers/callbacks/gallery_callbacks.py`
  * **行号**: 259
  * **描述**: `F811 Redefinition of unused 'contextlib' from line 28`。上下文管理器导入发生重定义。
* **局部变量赋值未使用**
  * **文件**: `src/web_api/routers/gallery.py`
  * **行号**: 326
  * **描述**: `F841 Local variable 'e' is assigned to but never used`。捕获了异常但未处理或记录。

### 6. 导入优化 (Import Optimization)
**严重程度: Low**

* **未使用的导入 (Unused Imports)**
  * **文件**: `src/core/auth_core.py` (Line 11: `AsyncSession`, Line 14: `PROXY_URL`)
  * **文件**: `src/core/gallery_core.py` (Line 6: `IntegrityError`)
  * **文件**: `src/handlers/fsm/gallery_apply_fsm.py` (Line 69: `UserInteraction`)
  * **描述**: Ruff F401，导入了模块但从未在文件中使用，增加命名空间污染。
* **导入顺序异常**
  * **文件**: `src/api_client.py` (Line 34), `src/bot_test.py` (Line 66)
  * **描述**: `E402 Module level import not at top of file`，包导入语句位于逻辑代码（如实例化变量）之后，不符合 PEP8 规范。

### 7. 死代码检测 (Dead Code)
**严重程度: Low**

* **未调用的函数/变量 (Unused Functions/Variables)**
  * **文件**: `backend/app/main.py`
  * **行号**: 104-214 之间的多个路由函数 (如 `create_img2img_task`, `create_face_swap_task`) 被 Vulture 标记为 unused。
  * **注**: 虽然 FastAPI 路由可能通过装饰器注册，但如果确实没有内部调用，可确认是否为废弃的旧版本 API。
  * **文件**: `backend/app/models.py`
  * **行号**: 45-63 之间的类属性 (如 `last_seen`, `current_task_type`) 疑似废弃。

### 8. 注释清理 (Comment Cleanup)
**严重程度: Low**

* **检测结果**: 全局搜索 `TODO` 与 `FIXME` 标签，当前代码库**未发现**遗留的未处理技术债标记。这表明团队在代码提交流程中对待办事项的管理较为规范。

---

## 💡 总结与建议行动项

1. **[Critical]** 立即处理 `gallery_sort_page_callback` 和 `ComfyAgent.process_task` 的极高复杂度（F级），这部分代码是系统崩溃和难以维护的重灾区。
2. **[High]** 重构前端组件，将 `FaceSwap.vue` 和 `VideoSwap.vue` 中的重复逻辑抽离为 Composition API，可大幅降低前端维护成本。
3. **[Medium]** 运行 `ruff check --fix` 和 `ruff format`，自动修复所有未使用的导入和排版问题。
4. **[Low]** 清理 `backend/app/models.py` 中的冗余字段，确保数据库实体与实际使用一致。
