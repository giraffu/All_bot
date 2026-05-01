# 系统 Bug 排查与修复方案记录

## 1. P0 级核心异常：`NameError: name 'logger' is not defined`

### 异常情况
- **报错位置**：`src/handlers/error_handlers.py` 第 22 行左右。
- **影响范围**：全局异常处理机制失效。
- **详细描述**：当系统捕获到任何业务异常（如业务逻辑报错）并进入统一的错误处理模块时，由于该文件内部未正确导入或定义 `logger` 对象，导致在记录日志时自身抛出 `NameError`。这不仅阻断了正常的错误上报流程，还掩盖了真实的业务报错堆栈。

### 解决方案
- **修复代码**：在 `src/handlers/error_handlers.py` 文件顶部补充正确的日志实例化代码。
  ```python
  import logging
  logger = logging.getLogger(__name__)
  ```
  *(注：如果项目有统一的日志工具文件，例如 `from src.utils.logger import logger`，请使用项目统一的导入方式。)*
- **执行建议**：此为最高优先级（P0）修复，必须立即执行，以恢复系统的基础监控和排障能力。

---

## 2. P1 级业务异常：`KeyError: 'custom_video_data'`

### 异常情况
- **报错位置**：业务处理模块（具体位置被上述的 P0 异常掩盖，推测在自定义视频相关的 FSM 或 Handler 中）。
- **详细描述**：代码在某处尝试从字典（通常是 Telegram 的 `context.user_data` 或某业务数据字典）中直接读取 `custom_video_data` 键，但该键尚未被初始化或已被清空，从而触发 `KeyError`。

### 解决方案
- **防御性编程**：将直接的字典访问 `data['custom_video_data']` 修改为安全的 `.get()` 方法：
  ```python
  video_data = context.user_data.get('custom_video_data', default_value)
  if not video_data:
      # 处理数据缺失的逻辑，例如提示用户重新操作
      return
  ```
- **生命周期核查**：检查对应的状态机（FSM）前置流转节点，确保在用户进入当前步骤前，`custom_video_data` 已经被正确赋值并写入上下文。
- **执行建议**：在修复 `error_handlers.py` 的 P0 缺陷后，再次触发该功能以获取完整的错误堆栈，从而精确定位并修复。
