# 测试指南 (Testing Guide)

本项目使用 `pytest` 和 `pytest-asyncio` 框架来进行自动化单元测试和集成测试，以确保核心业务逻辑（如权限验证、排队状态解析、灵石扣费系统等）的正确性和稳定性。

## 1. 测试环境要求

本项目建议使用 `conda` 维护独立的测试环境。如果你还没有配置过测试环境，请按照以下步骤创建。**如果你已经创建过该环境，只需直接激活即可。**

### 1.1 激活或创建 Conda 环境
在项目的根目录执行以下命令：

```bash
# 1. 激活已有的测试环境
conda activate bot_test_env

# ----------------------------------------------------
# 2. 【仅首次】如果环境不存在，请先创建并安装依赖：
conda create -n bot_test_env python=3.10 -y
conda activate bot_test_env
pip install -r requirements.txt
pip install pytest pytest-asyncio
# ----------------------------------------------------
```

## 2. 运行测试

所有的测试代码都存放在 `src/tests/` 目录下。

### 运行所有测试
在项目的根目录（`/home/hfy/APP/All_bot`）下，确保已激活测试环境，并添加 `PYTHONPATH`（否则可能会报模块找不到的错误），然后执行：

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
pytest src/tests/
```

或者查看详细输出：

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
pytest -v src/tests/
```

### 运行单个测试文件
如果你只想运行某个特定的测试模块（例如权限计算逻辑），可以指定文件路径：

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
pytest src/tests/test_dynamic_priority.py -v
```

## 3. 测试覆盖的核心领域

目前系统包含以下几个核心领域的测试用例：

### 3.1 动态排队优先级测试 (`test_dynamic_priority.py`)
测试 `PermissionService` 的排队加速计算逻辑是否符合设计。
* **涵盖场景**:
  * **新手加速 (Newbie Bonus)**：测试用户历史生成次数 < 2 时，是否正确获得固定的 +30 极速优先级。
  * **境界衰减机制**：测试不同修为（金丹期、筑基期、练气期、凡人）的加成是否按照当日生成次数准确衰减（例如金丹期超过 100 次后降为 0）。
  * **身份与修为叠加**：验证“修为优先级”与“身份优先级”（如真传弟子）叠加计算的结果是否正确。

### 3.2 单轨制积分系统测试 (`test_points_system.py`)
测试 `QuotaManager` 管理的“永久灵石”逻辑。
* **涵盖场景**:
  * **初始化与结构**：验证新用户初始灵石分配是否正确。
  * **每日签到**：测试签到操作是否正确发放永久灵石。
  * **扣费逻辑**：验证生成任务时，是否正确扣除灵石，并判断余额是否充足。

### 3.3 队列状态解析测试 (`test_queue_logic.py`)
测试底层 API 通信（`api_client.py`）以及排队状态显示（`TaskService`）的容错性。
* **涵盖场景**:
  * **非规范化返回**：测试当后端 API 返回的 payload 缺少特定字段时，客户端是否能正确降级处理（例如仅有 `queue_remaining` 而无 `queue_pos`）。
  * **状态展示**：验证 UI 层提取并显示“当前在第 X 位”的逻辑是否准确。

### 3.4 业务流程与扣费流转测试 (`test_text_to_image.py`)
测试文生图（Text-to-Image）以及其他生成任务的流程流转。
* **涵盖场景**:
  * **成功流转**：模拟用户发送 Prompt，系统完成权限校验、扣费、后端任务提交、轮询进度，最后成功返回成品的完整链路。
  * **余额不足拦截**：模拟用户灵石不足时，系统是否能正确拦截请求并发送失败提示，且不执行后端提交。

## 4. 编写新测试的注意事项

如果你在未来为项目开发新功能，请遵循以下规范编写测试：

1. **异步支持**: 由于本系统大量使用 `asyncio` 和 `httpx`，大部分测试必须使用 `@pytest.mark.asyncio` 装饰器。
2. **Mock 的使用**: 涉及到外部 API 调用（如请求 ComfyUI 后端）或 Telegram Bot 接口发送消息的逻辑，请务必使用 `unittest.mock.AsyncMock` 和 `patch` 进行拦截，**绝对不要**在单元测试中发起真实的外部网络请求。
3. **数据库隔离**: 对于涉及 `users` 或 `user_logs` 的测试，在 `setup_db` fixture 中要确保测试完成后进行彻底的数据清理 (`Cleanup`)，防止污染本地或测试服数据库。
