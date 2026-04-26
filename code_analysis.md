# 全局代码静态分析与质量评估报告

## 📊 可量化指标汇总

- **平均代码复杂度 (Cyclomatic Complexity)**: 5.37
- **高复杂度代码块数量 (>10)**: 79
- **死代码/未引用对象数量**: 17
- **TODO/FIXME 遗留注释数量**: 18
- **代码重复段落数**: 11

## 💡 架构重构建议

1. **单一职责原则(SRP)**: 对于包含过多公共方法或属性的类，建议将其拆分为更小、职责更单一的组件（如将数据库访问、业务逻辑和API响应分离）。
2. **依赖倒置与解耦**: 发现较多全局变量滥用和作用域冲突，建议使用依赖注入或上下文传递代替直接导入全局状态。
3. **并发锁与队列**: 在涉及到长耗时任务时，发现潜在的阻塞或缺少状态同步（详见并发、排队与任务调度规范）。

## 📁 按文件结构的详细分析

### 📄 `backend/app/config.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 3 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 6 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 7 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 10 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 19 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 23 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 24 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 24 | 一般代码规范 | **Low** | Too few public methods (0/2) (too-few-public-methods) |


### 📄 `backend/app/main.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 9 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 11 | 一般代码规范 | **Low** | Line too long (286/120) (line-too-long) |
| 27 | 一般代码规范 | **Low** | Constant name "minio_client" doesn't conform to UPPER_CASE naming style (invalid-name) |
| 30 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 38 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 41 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 49 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 50 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 54 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 56 | 作用域分析 | **Medium** | Using the global statement (global-statement) |
| 57 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 66 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 67 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 68 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 71 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 74 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 80 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 83 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 91 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 94 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 102 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 105 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 113 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 116 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 124 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 127 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 135 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 138 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 142 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 148 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 151 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 159 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 162 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 170 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 173 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 181 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 181 | 代码坏味道 | **Low** | Too many local variables (19/15) (too-many-locals) |
| 181 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `create_t2i_pornmaster_turbo_task`): Cyclomatic Complexity = 12 |
| 186 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 189 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 190 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 194 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 199 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 204 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 206 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 207 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise HTTPException(status_code=500, detail='Internal server error') from e' (raise-missing-from) |
| 208 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 217 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 219 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 221 | 一般代码规范 | **Low** | Unnecessary "elif" after "return", remove the leading "el" from "elif" (no-else-return) |
| 225 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 229 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 231 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 233 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 234 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 236 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 240 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 243 | 一般代码规范 | **Medium** | Unused argument 'token' (unused-argument) |
| 251 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 258 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 262 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 266 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 272 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 284 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 291 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 295 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 300 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 311 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 318 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 322 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 325 | 一般代码规范 | **Low** | Import outside toplevel (tempfile) (import-outside-toplevel) |
| 326 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 329 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 331 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 335 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 343 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 344 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise HTTPException(status_code=404, detail='File not found in storage') from e' (raise-missing-from) |
| 347 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 354 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 358 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 359 | 一般代码规范 | **Low** | Import outside toplevel (tempfile) (import-outside-toplevel) |
| 360 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 363 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 365 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 369 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 377 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 378 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise HTTPException(status_code=404, detail='File not found in storage') from e' (raise-missing-from) |
| 381 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 391 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 396 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 399 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 401 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `backend/app/models.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "typing.Optional" should be placed before third party import "pydantic.BaseModel" (wrong-import-order) |
| 3 | 导入优化 | **Low** | standard import "enum.Enum" should be placed before third party import "pydantic.BaseModel" (wrong-import-order) |
| 5 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 12 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 23 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 26 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 30 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 39 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 49 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 53 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 59 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 70 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 83 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 88 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 96 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 104 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 113 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 120 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 126 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 132 | 一般代码规范 | **Low** | Final newline missing (missing-final-newline) |


### 📄 `backend/app/queue_manager.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 7 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 9 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 18 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 21 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 23 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 37 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 41 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 47 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 50 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 54 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 59 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 59 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `dequeue_task`): Cyclomatic Complexity = 12 |
| 75 | 一般代码规范 | **Low** | Line too long (123/120) (line-too-long) |
| 78 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 82 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 87 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 95 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 107 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 113 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 117 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 125 | 一般代码规范 | **Low** | Line too long (141/120) (line-too-long) |
| 127 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 134 | 一般代码规范 | **Low** | Line too long (121/120) (line-too-long) |
| 136 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 139 | 一般代码规范 | **Low** | Line too long (121/120) (line-too-long) |
| 140 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 141 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 145 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 152 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 155 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 157 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 158 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 166 | 一般代码规范 | **Low** | "cursor == 0" can be simplified to "not cursor", if it is strictly an int, as 0 is falsey (use-implicit-booleaness-not-comparison-to-zero) |
| 170 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 183 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 192 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 194 | 一般代码规范 | **Low** | "cursor == 0" can be simplified to "not cursor", if it is strictly an int, as 0 is falsey (use-implicit-booleaness-not-comparison-to-zero) |
| 198 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 212 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 223 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 225 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 228 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 231 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 238 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 240 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 248 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 251 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |


### 📄 `backend/app/routers/agent.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 3 | 导入优化 | **Low** | standard import "typing.Optional" should be placed before third party imports "fastapi.APIRouter", "pydantic.BaseModel" (wrong-import-order) |
| 4 | 导入优化 | **Low** | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "pydantic.BaseModel" (wrong-import-order) |
| 7 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 17 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 25 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 28 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 35 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 40 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 45 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 46 | 作用域分析 | **Medium** | Redefining name 'settings' from outer scope (line 9) (redefined-outer-name) |
| 46 | 导入优化 | **Medium** | Reimport 'settings' (imported line 9) (reimported) |
| 46 | 一般代码规范 | **Low** | Import outside toplevel (app.config.settings) (import-outside-toplevel) |
| 57 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 59 | 一般代码规范 | **Medium** | Unused argument 'authorized' (unused-argument) |
| 59 | 死代码检测 | **Low** | unused variable 'authorized' (100% confidence) |
| 65 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 69 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 72 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 75 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 79 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 81 | 一般代码规范 | **Medium** | Unused argument 'authorized' (unused-argument) |
| 81 | 死代码检测 | **Low** | unused variable 'authorized' (100% confidence) |
| 90 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 91 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 92 | 一般代码规范 | **Medium** | Unused argument 'authorized' (unused-argument) |
| 92 | 死代码检测 | **Low** | unused variable 'authorized' (100% confidence) |
| 98 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 104 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 108 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 109 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 110 | 一般代码规范 | **Medium** | Unused argument 'authorized' (unused-argument) |
| 110 | 死代码检测 | **Low** | unused variable 'authorized' (100% confidence) |
| 117 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 122 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 124 | 一般代码规范 | **Medium** | Unused argument 'authorized' (unused-argument) |
| 124 | 死代码检测 | **Low** | unused variable 'authorized' (100% confidence) |
| 134 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 136 | 一般代码规范 | **Medium** | Unused argument 'authorized' (unused-argument) |
| 136 | 死代码检测 | **Low** | unused variable 'authorized' (100% confidence) |


### 📄 `backend/tests/conftest.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "unittest.mock.AsyncMock" should be placed before third party import "pytest" (wrong-import-order) |
| 10 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 25 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 25 | 作用域分析 | **Medium** | Redefining name 'mock_queue_manager' from outer scope (line 10) (redefined-outer-name) |
| 28 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 31 | 一般代码规范 | **High** | Module 'app.main' has no 'comfy_client' member (no-member) |
| 32 | 一般代码规范 | **High** | Module 'app.main' has no 'comfy_client' member (no-member) |
| 33 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 36 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 39 | 一般代码规范 | **High** | Module 'app.main' has no 'comfy_client' member (no-member) |
| 42 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |


### 📄 `backend/tests/test_api.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 3 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 11 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 20 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 22 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 30 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 34 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 36 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 47 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 51 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 53 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 61 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 65 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 67 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 75 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 79 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 89 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 97 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 102 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 107 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 111 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 114 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 119 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 128 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 133 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `backend/tests/test_auth.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 1 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 12 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 24 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 32 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `backend/tests/test_t2i_pornmaster.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "unittest.mock.patch" should be placed before third party import "pytest" (wrong-import-order) |
| 5 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 8 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 14 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 20 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 23 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 30 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 34 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 36 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 42 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 49 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 57 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 65 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 74 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 77 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 83 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 86 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 88 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 94 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 98 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 101 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 104 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 108 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 111 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 117 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 120 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 127 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 135 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 136 | 一般代码规范 | **High** | Unable to import 'app.worker' (import-error) |
| 136 | 一般代码规范 | **Low** | Import outside toplevel (app.worker.Worker) (import-outside-toplevel) |
| 136 | 一般代码规范 | **High** | No name 'worker' in module 'app' (no-name-in-module) |
| 137 | 一般代码规范 | **High** | Unable to import 'app.comfy_client' (import-error) |
| 137 | 一般代码规范 | **Low** | Import outside toplevel (app.comfy_client.ComfyClient) (import-outside-toplevel) |
| 137 | 一般代码规范 | **High** | No name 'comfy_client' in module 'app' (no-name-in-module) |
| 138 | 一般代码规范 | **Low** | Import outside toplevel (app.queue_manager.QueueManager) (import-outside-toplevel) |
| 139 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 142 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 144 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 151 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 158 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 165 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 167 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 172 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 173 | 一般代码规范 | **High** | Unable to import 'app.worker' (import-error) |
| 173 | 一般代码规范 | **Low** | Import outside toplevel (app.worker.Worker) (import-outside-toplevel) |
| 173 | 一般代码规范 | **High** | No name 'worker' in module 'app' (no-name-in-module) |
| 174 | 一般代码规范 | **High** | Unable to import 'app.comfy_client' (import-error) |
| 174 | 一般代码规范 | **Low** | Import outside toplevel (app.comfy_client.ComfyClient) (import-outside-toplevel) |
| 174 | 一般代码规范 | **High** | No name 'comfy_client' in module 'app' (no-name-in-module) |
| 175 | 一般代码规范 | **Low** | Import outside toplevel (app.queue_manager.QueueManager) (import-outside-toplevel) |
| 176 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 179 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 181 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 188 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 191 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 198 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 200 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `backend/workflows/Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 551 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "text": "<lora:Mystic-XXX-ZIT-V5:0.10>", |
| 555 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "name": "Mystic-XXX-ZIT-V5", |


### 📄 `cs_bot/bot.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 5 | 导入优化 | **Low** | standard import "time" should be placed before third party import "httpx" (wrong-import-order) |
| 6 | 导入优化 | **Low** | standard import "collections.defaultdict" should be placed before third party import "httpx" (wrong-import-order) |
| 14 | 导入优化 | **Low** | standard import "re" should be placed before third party imports "httpx", "dotenv.load_dotenv", "telegram.Update" (...) "telegram.request.HTTPXRequest", "langgraph_client.get_langgraph_reply", "db.init_db" (wrong-import-order) |
| 23 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 29 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 42 | 一般代码规范 | **Medium** | Keyword argument before variable positional arguments list in the definition of custom_download_as_bytearray function (keyword-arg-before-vararg) |
| 42 | 一般代码规范 | **Medium** | Unused argument 'out' (unused-argument) |
| 42 | 一般代码规范 | **Medium** | Unused argument 'custom_path' (unused-argument) |
| 42 | 一般代码规范 | **Medium** | Unused argument 'args' (unused-argument) |
| 42 | 一般代码规范 | **Medium** | Unused argument 'kwargs' (unused-argument) |
| 42 | 死代码检测 | **Low** | unused variable 'out' (100% confidence) |
| 49 | 一般代码规范 | **Low** | Import outside toplevel (urllib.parse) (import-outside-toplevel) |
| 52 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 58 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 59 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 60 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 66 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 68 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 90 | 一般代码规范 | **Medium** | Unused argument 'context' (unused-argument) |
| 98 | 代码坏味道 | **Low** | Too many local variables (22/15) (too-many-locals) |
| 98 | 代码坏味道 | **Low** | Too many branches (18/12) (too-many-branches) |
| 98 | 代码坏味道 | **Low** | Too many statements (57/50) (too-many-statements) |
| 98 | 代码坏味道 | **High** | 高复杂度代码块 (function `handle_group_message`): Cyclomatic Complexity = 36 |
| 108 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 112 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 116 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 132 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 137 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 141 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 153 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 160 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 167 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 172 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 184 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 204 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 205 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 215 | 代码坏味道 | **Low** | Too many branches (13/12) (too-many-branches) |
| 215 | 一般代码规范 | **Medium** | Unused argument 'context' (unused-argument) |
| 215 | 代码坏味道 | **High** | 高复杂度代码块 (function `silent_logger_handler`): Cyclomatic Complexity = 23 |
| 222 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 223 | 一般代码规范 | **Medium** | Unused variable 'chat_type' (unused-variable) |
| 225 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 230 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 241 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 243 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 248 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 272 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 291 | 一般代码规范 | **Medium** | Unused argument 'application' (unused-argument) |
| 295 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 302 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 308 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 311 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 333 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `cs_bot/db.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "os" should be placed before third party import "aiosqlite" (wrong-import-order) |
| 3 | 导入优化 | **Low** | standard import "logging" should be placed before third party import "aiosqlite" (wrong-import-order) |
| 4 | 导入优化 | **Low** | standard import "json" should be placed before third party import "aiosqlite" (wrong-import-order) |
| 28 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 32 | 一般代码规范 | **Low** | Import outside toplevel (datetime) (import-outside-toplevel) |
| 37 | 代码坏味道 | **Low** | Too many arguments (8/5) (too-many-arguments) |
| 37 | 一般代码规范 | **Low** | Too many positional arguments (8/5) (too-many-positional-arguments) |
| 63 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 64 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |


### 📄 `cs_bot/langgraph_client.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 24 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 57 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 60 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 63 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 64 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 65 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 84 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 125 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 126 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 139 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 155 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 159 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 163 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 164 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 165 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |


### 📄 `cs_bot/skill_manager.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 3 | 导入优化 | **Medium** | Unused import importlib.util (unused-import) |
| 4 | 导入优化 | **Medium** | Unused import inspect (unused-import) |
| 4 | 死代码检测 | **Low** | unused import 'inspect' (90% confidence) |
| 6 | 导入优化 | **Medium** | Unused tool imported from langchain_core.tools (unused-import) |
| 8 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 33 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 37 | 作用域分析 | **Medium** | Redefining name 'importlib' from outer scope (line 3) (redefined-outer-name) |
| 37 | 一般代码规范 | **Low** | Import outside toplevel (importlib) (import-outside-toplevel) |
| 38 | 作用域分析 | **Medium** | Redefining name 'inspect' from outer scope (line 4) (redefined-outer-name) |
| 38 | 导入优化 | **Medium** | Reimport 'inspect' (imported line 4) (reimported) |
| 38 | 一般代码规范 | **Low** | Import outside toplevel (inspect) (import-outside-toplevel) |
| 38 | 导入优化 | **Medium** | Unused import inspect (unused-import) |
| 38 | 死代码检测 | **Low** | unused import 'inspect' (90% confidence) |
| 39 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 44 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 50 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `cs_bot/skills/system_status_skill.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==comfy_agent2.agent_main:[16:551] ==comfy_agent4.agent_main:[16:551] load_dotenv()  # Unset proxies to prevent internal requests from being routed through system VPN/proxies for proxy_var in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:     os.environ.pop(proxy_var, None) os.environ["NO_PROXY"] = "*" os.environ["no_proxy"] = "*"  class CorrelationIdFilter(logging.Filter):     def filter(self, record):         trace_id = correlation_id.get()         record.correlation_id = f"TraceID: {trace_id}" if trace_id else "TraceID: None"         return True  log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s' handler = logging.StreamHandler(sys.stdout) handler.setFormatter(logging.Formatter(log_format)) handler.addFilter(CorrelationIdFilter())  logging.basicConfig(     level=logging.INFO,     handlers=[handler] ) logger = logging.getLogger("agent_main")  # Configuration AGENT_ID = os.getenv("AGENT_ID", "worker_local_01") SUPPORTED_TASK_TYPES = os.getenv("SUPPORTED_TASK_TYPES", "") # e.g. "img2img,face_swap" MASTER_API_URL = os.getenv("MASTER_API_URL", "http://127.0.0.1:8000") AGENT_SECRET_TOKEN = os.getenv("AGENT_SECRET_TOKEN", "")  COMFY_API_URL = os.getenv("COMFY_API_URL", "http://127.0.0.1:8188") COMFY_WS_URL = os.getenv("COMFY_WS_URL", "ws://127.0.0.1:8188/ws") COMFY_INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/home/ubantu/comfyui/input") COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "/home/ubantu/comfyui/output")  MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "play.min.io:9000") MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "your_key") MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "your_secret") MINIO_INPUT_BUCKET = os.getenv("MINIO_INPUT_BUCKET", "comfyui-input") MINIO_RESULT_BUCKET = os.getenv("MINIO_RESULT_BUCKET", "comfyui-output")  class ComfyAgent:     def __init__(self):         self.comfy_client = ComfyClient(base_url=COMFY_API_URL)         self.patcher = WorkflowPatcher(workflows_dir=os.path.join(os.path.dirname(__file__), "workflows"))         self.master_client = httpx.AsyncClient(             base_url=MASTER_API_URL,             headers={"Authorization": f"Bearer {AGENT_SECRET_TOKEN}"},             timeout=30.0         )          # Init MinIO         try:             self.minio_client = Minio(                 MINIO_ENDPOINT,                 access_key=MINIO_ACCESS_KEY,                 secret_key=MINIO_SECRET_KEY,                 secure=False  # Set to True if using HTTPS             )             logger.info("MinIO client initialized")         except Exception as e:             logger.error(f"Failed to init MinIO: {e}")             self.minio_client = None          self.current_task_id: Optional[str] = None         self.current_prompt_id: Optional[str] = None         self.task_completed_event = asyncio.Event()         self.task_result: Optional[str] = None         self.task_error: Optional[str] = None         self.running = False      async def report_heartbeat(self):         try:             status = "running" if self.current_task_id else "idle"             await self.master_client.post("/api/agent/task/heartbeat", json={                 "agent_id": AGENT_ID,                 "types": SUPPORTED_TASK_TYPES,                 "status": status             })             if self.current_task_id:                 # Add task heartbeat specifically                 await self.master_client.post("/api/agent/task/task_heartbeat", json={                     "task_id": self.current_task_id                 })         except Exception as e:             logger.debug(f"Failed to report heartbeat: {e}")      async def heartbeat_loop(self):         logger.info(f"Agent {AGENT_ID} started heartbeat loop...")         while getattr(self, 'running', True):             await self.report_heartbeat()             await asyncio.sleep(15)  # Send heartbeat every 15 seconds      async def report_status(self, task_id: str, status: str, progress: float = 0.0, error: str = ""):         try:             await self.master_client.post("/api/agent/task/status", json={                 "task_id": task_id,                 "agent_id": AGENT_ID,                 "status": status,                 "progress": progress,                 "error": error             })         except Exception as e:             logger.error(f"Failed to report status for task {task_id}: {e}")      async def report_complete(self, task_id: str, result_path: str):         try:             await self.master_client.post("/api/agent/task/complete", json={                 "task_id": task_id,                 "agent_id": AGENT_ID,                 "result": result_path             })         except Exception as e:             logger.error(f"Failed to report completion for task {task_id}: {e}")      async def ws_listener_loop(self):         client_id = f"agent_{AGENT_ID}"         uri = f"{COMFY_WS_URL}?clientId={client_id}"          while getattr(self, 'running', True):             try:                 async with websockets.connect(uri, max_size=None, ping_interval=20, ping_timeout=20) as websocket:                     logger.info(f"Connected to ComfyUI WebSocket at {uri}")                     while True:                         try:                             # Use timeout to periodically check connection state                             message = await asyncio.wait_for(websocket.recv(), timeout=60.0)                         except asyncio.TimeoutError:                             if websocket.closed:                                 logger.error("WebSocket closed unexpectedly")                                 break                             try:                                 await websocket.ping()                             except Exception as e:                                 logger.error(f"WebSocket ping failed: {e}")                                 break                             continue                          if isinstance(message, bytes):                             continue                          data = json.loads(message)                         msg_type = data.get("type")                         data_content = data.get("data", {})                          prompt_id = data_content.get("prompt_id")                          if not prompt_id or prompt_id != self.current_prompt_id:                             continue                          if msg_type == "execution_start":                             logger.info(f"Execution started for prompt {prompt_id}")                             if self.current_task_id:                                 await self.report_status(self.current_task_id, "running")                          elif msg_type == "progress":                             value = data_content.get("value", 0)                             max_val = data_content.get("max", 1)                             if max_val > 0 and self.current_task_id:                                 progress = value / max_val                                 await self.report_status(self.current_task_id, "running", progress=progress)                          elif msg_type == "executing":                             node = data_content.get("node")                             if node is None:                                 logger.info(f"Execution fully completed for prompt {prompt_id}")                                 self.task_completed_event.set()                          elif msg_type == "execution_success":                             logger.info(f"Execution success received for prompt {prompt_id}")                             self.task_completed_event.set()                          elif msg_type == "executed":                             logger.info(f"Node executed for prompt {prompt_id}")                             output = data_content.get("output", {})                             images = output.get("images", [])                             gifs = output.get("gifs", [])                             videos = output.get("videos", [])                              result_path = ""                             if images:                                 img = images[0]                                 result_path = f"{img.get('subfolder', '')}/{img.get('filename')}".lstrip('/')                             elif gifs:                                 gif = gifs[0]                                 result_path = f"{gif.get('subfolder', '')}/{gif.get('filename')}".lstrip('/')                             elif videos:                                 video = videos[0]                                 result_path = f"{video.get('subfolder', '')}/{video.get('filename')}".lstrip('/')                              if result_path:                                 self.task_result = result_path                                 # We now wait for executing node=None to set the completion event                          elif msg_type == "execution_error":                             error_msg = str(data_content.get("exception_message", "Unknown error"))                             logger.error(f"Execution error for prompt {prompt_id}: {error_msg}")                             self.task_error = error_msg                             self.task_completed_event.set()              except Exception as e:                 logger.error(f"WebSocket connection error: {e}")                 await asyncio.sleep(5)      def download_input_from_minio(self, object_name: str, local_path: str):         if not self.minio_client:             raise Exception("MinIO client not initialized")          bucket_name = "bot-data"         real_object_name = object_name          if object_name.startswith("template:"):             bucket_name = "bot-template"             real_object_name = object_name.replace("template:", "")          logger.info(f"Downloading {real_object_name} from MinIO bucket {bucket_name} to {local_path}")         self.minio_client.fget_object(bucket_name, real_object_name, local_path)      def upload_result_to_minio(self, local_path: str, object_name: str):         if not self.minio_client:             raise Exception("MinIO client not initialized")          content_type = "image/png"         if object_name.endswith(".mp4"):             content_type = "video/mp4"         elif object_name.endswith(".gif"):             content_type = "image/gif"         elif object_name.endswith(".jpg") or object_name.endswith(".jpeg"):             content_type = "image/jpeg"          logger.info(f"Uploading {local_path} to MinIO bucket {MINIO_RESULT_BUCKET} as {object_name}")         self.minio_client.fput_object(MINIO_RESULT_BUCKET, object_name, local_path, content_type=content_type)      async def check_task_cancelled(self, task_id: str) -> bool:         try:             response = await self.master_client.get(f"/api/agent/task/check/{task_id}")             if response.status_code == 200:                 data = response.json()                 if data.get("status") == "cancelled":                     return True         except Exception as e:             logger.debug(f"Failed to check task status: {e}")         return False      async def process_task(self, task: Dict[str, Any]):         trace_id = task.get("trace_id", "")         if trace_id:             correlation_id.set(trace_id)          task_id = str(task.get("task_id", ""))         if not task_id:             logger.error("Received task without task_id")             return          task_type = str(task.get("type", ""))         params_str = task.get("params", "{}")          if isinstance(params_str, str):             params = json.loads(params_str)         else:             params = params_str          logger.info(f"Processing task {task_id} of type {task_type}")         self.current_task_id = task_id         self.task_completed_event.clear()         self.task_result = None         self.task_error = None          downloaded_input_paths = []          try:             if await self.check_task_cancelled(task_id):                 logger.info(f"Task {task_id} was cancelled before processing.")                 return              # Helper for downloading and uploading single image             async def process_single_image(img_filename: str, param_key: str):                 local_safe_filename = img_filename.replace("/", "_").replace("template:", "")                 local_img_path = os.path.join(COMFY_INPUT_DIR, local_safe_filename)                 try:                     await asyncio.to_thread(self.download_input_from_minio, img_filename, local_img_path)                     logger.info(f"Downloaded {param_key} to {local_img_path}")                     try:                         with open(local_img_path, "rb") as f:                             img_data = f.read()                         await self.comfy_client.upload_image(img_data, local_safe_filename)                         logger.info(f"Uploaded {local_safe_filename} to ComfyUI via API")                     except Exception as upload_err:                         logger.warning(f"Failed to upload {local_safe_filename} to ComfyUI via API: {upload_err}")                     params[param_key] = local_safe_filename                     if local_img_path not in downloaded_input_paths:                         downloaded_input_paths.append(local_img_path)                 except Exception as e:                     logger.error(f"Failed to process {param_key} {img_filename}: {e}")              # 1. Handle multi-image concurrent download if `images` list is provided             if "images" in params and isinstance(params["images"], list) and len(params["images"]) > 0:                 images_list = params["images"]                 tasks = []                 keys = ["image", "image2", "image3"]                 for i, img_filename in enumerate(images_list[:3]):                     tasks.append(process_single_image(img_filename, keys[i]))                 if tasks:                     await asyncio.gather(*tasks)             else:                 # Fallback to legacy single image keys                 legacy_tasks = []                 if "image" in params and params["image"]:                     legacy_tasks.append(process_single_image(params["image"], "image"))                 if "image2" in params and params["image2"]:                     legacy_tasks.append(process_single_image(params["image2"], "image2"))                 if legacy_tasks:                     await asyncio.gather(*legacy_tasks)              # Also check for other potential image inputs (like face_image, body_image, video)             other_tasks = []             for key in ["face_image", "body_image", "video"]:                 if key in params and params[key]:                     other_tasks.append(process_single_image(params[key], key))             if other_tasks:                 await asyncio.gather(*other_tasks)              # 2. Load and patch workflow             workflow = self.patcher.load_workflow(task_type)             if not workflow:                 raise ValueError(f"Workflow for {task_type} not found")              patched_workflow = self.patcher.patch_workflow(task_type, workflow, params)              # 3. Submit to ComfyUI             client_id = f"agent_{AGENT_ID}"             self.current_prompt_id = await self.comfy_client.queue_prompt(patched_workflow, client_id)             logger.info(f"Submitted task {task_id} to ComfyUI, prompt_id: {self.current_prompt_id}")              await self.report_status(task_id, "running")              # 4. Wait for completion (via WS listener)             # Timeout after 10 minutes to avoid hanging forever             try:                 await asyncio.wait_for(self.task_completed_event.wait(), timeout=600.0)             except asyncio.TimeoutError:                 logger.warning(f"Task execution timed out for {task_id}, will attempt to fetch result from history.")              if self.task_error:                 raise Exception(self.task_error)              if not self.task_result:                 logger.info(f"Task result not set via WS, checking history for prompt {self.current_prompt_id}")                 try:                     history = await self.comfy_client.get_history(self.current_prompt_id)                     if history and self.current_prompt_id in history:                         outputs = history[self.current_prompt_id].get("outputs", {})                         for node_id, node_output in outputs.items():                             images = node_output.get("images", [])                             gifs = node_output.get("gifs", [])                             videos = node_output.get("videos", [])                              if images:                                 img = images[0]                                 self.task_result = f"{img.get('subfolder', '')}/{img.get('filename')}".lstrip('/')                                 break                             elif gifs:                                 gif = gifs[0]                                 self.task_result = f"{gif.get('subfolder', '')}/{gif.get('filename')}".lstrip('/')                                 break                             elif videos:                                 video = videos[0]                                 self.task_result = f"{video.get('subfolder', '')}/{video.get('filename')}".lstrip('/')                                 break                 except Exception as e:                     logger.warning(f"Failed to fetch history: {e}")              if not self.task_result:                 raise Exception("Task completed but no result path found")              if await self.check_task_cancelled(task_id):                 logger.info(f"Task {task_id} was cancelled during execution, skipping upload.")                 return              # 5. Fetch result from ComfyUI API and Upload to MinIO             # We must fetch the file via the ComfyUI /view API since Agent might not have direct local disk access             # or the file might be in temp/output directories on the ComfyUI server.             try:                 # Assuming task_result format is like "subfolder/filename.png" or "filename.png"                 parts = self.task_result.split('/')                 if len(parts) > 1:                     subfolder = '/'.join(parts[:-1])                     filename = parts[-1]                 else:                     subfolder = ""                     filename = self.task_result                  # We need to determine the type based on the path. Often it's 'output', but if it contains 'temp'                 # (like ComfyUI_temp_xxx), it might be in the 'temp' type.                 # However, get_view defaults to 'output' or 'temp' based on how ComfyUI saves it.                 view_type = "temp" if "temp" in filename.lower() else "output"                  logger.info(f"Fetching result {filename} from ComfyUI API (subfolder: '{subfolder}', type: '{view_type}')")                  # We use the existing comfy_client.get_view method                 file_data = await self.comfy_client.get_view(filename, subfolder, type=view_type)                  # Upload the fetched bytes directly to MinIO                 import io                 content_type = "image/png"                 if filename.endswith(".mp4"):                     content_type = "video/mp4"                 elif filename.endswith(".gif"):                     content_type = "image/gif"                 elif filename.endswith(".jpg") or filename.endswith(".jpeg"):                     content_type = "image/jpeg"                  logger.info(f"Uploading result {self.task_result} to MinIO bucket {MINIO_RESULT_BUCKET}")                 await asyncio.to_thread(                     self.minio_client.put_object,                     MINIO_RESULT_BUCKET,                     self.task_result,                     io.BytesIO(file_data),                     len(file_data),                     content_type=content_type                 )              except Exception as e:                 logger.error(f"Failed to fetch from ComfyUI or upload to MinIO: {e}")                 raise Exception(f"Result processing failed: {e}")              # 6. Report completion             await self.report_complete(task_id, self.task_result)             logger.info(f"Task {task_id} completed successfully")          except Exception as e:             logger.error(f"Task {task_id} failed: {e}")             await self.report_status(task_id, "failed", error=str(e))         finally:             self.current_task_id = None             self.current_prompt_id = None             for path in downloaded_input_paths:                 try:                     if os.path.exists(path):                         os.remove(path)                         logger.info(f"Cleaned up input file: {path}")                 except Exception as e:                     logger.warning(f"Failed to clean up input file {path}: {e}")      async def poll_loop(self):         logger.info(f"Agent {AGENT_ID} started polling {MASTER_API_URL} for tasks (types: {SUPPORTED_TASK_TYPES or 'all'})...")         while getattr(self, 'running', True):             try:                 # Poll for tasks with optional type filtering                 params = {}                 if SUPPORTED_TASK_TYPES:                     params["types"] = SUPPORTED_TASK_TYPES                  response = await self.master_client.get("/api/agent/task/pop", params=params)                 if response.status_code == 200:                     data = response.json()                     task = data.get("task")                     if task:                         await self.process_task(task)                         continue  # Immediately poll again after finishing                 elif response.status_code != 404: # 404 means no tasks, which is fine                     logger.warning(f"Unexpected response from master: {response.status_code}")              except httpx.RequestError as e:                 logger.error(f"Connection to master failed: {e}")             except Exception as e:                 logger.error(f"Polling error: {e}")              # Wait before next poll             await asyncio.sleep(2)      async def start(self):         # Ensure directories exist         os.makedirs(COMFY_INPUT_DIR, exist_ok=True)         os.makedirs(COMFY_OUTPUT_DIR, exist_ok=True)          # Start WS listener, polling loops, and heartbeat         self.running = True         self.tasks = [             asyncio.create_task(self.ws_listener_loop()),             asyncio.create_task(self.poll_loop()),             asyncio.create_task(self.heartbeat_loop())         ]         await asyncio.gather(*self.tasks)      async def shutdown(self):         logger.info("Initiating graceful shutdown...")         self.running = False          # If there is a task currently running, report it as failed/interrupted back to master         if self.current_task_id:             logger.info(f"Returning task {self.current_task_id} to master due to shutdown")             try:                 await self.report_status(                     self.current_task_id,                     "failed",                     error="Agent was shut down while processing the task. Task should be retried."                 )             except Exception as e:                 logger.error(f"Failed to report task failure during shutdown: {e}")          # Cancel all running background loops         for task in self.tasks:             task.cancel()          # Close HTTP clients         await self.master_client.aclose()         await self.comfy_client.close()         logger.info("Shutdown complete.")  if __name__ == "__main__":     agent = ComfyAgent()      # Setup graceful shutdown signals     import signal     import sys     loop = asyncio.get_event_loop()      if sys.platform != 'win32':         for sig in (signal.SIGINT, signal.SIGTERM):             loop.add_signal_handler(                 sig,                 lambda: asyncio.create_task(agent.shutdown())             )      try:         loop.run_until_complete(agent.start())     except asyncio.CancelledError:         pass     except KeyboardInterrupt:         # 捕获 Ctrl+C，触发优雅退出逻辑，防止 Master 端任务卡死         loop.run_until_complete(agent.shutdown())     finally:         loop.close() (duplicate-code) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==comfy_agent1.agent_main:[16:551] ==comfy_agent5.agent_main:[16:551] load_dotenv()  # Unset proxies to prevent internal requests from being routed through system VPN/proxies for proxy_var in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:     os.environ.pop(proxy_var, None) os.environ["NO_PROXY"] = "*" os.environ["no_proxy"] = "*"  class CorrelationIdFilter(logging.Filter):     def filter(self, record):         trace_id = correlation_id.get()         record.correlation_id = f"TraceID: {trace_id}" if trace_id else "TraceID: None"         return True  log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s' handler = logging.StreamHandler(sys.stdout) handler.setFormatter(logging.Formatter(log_format)) handler.addFilter(CorrelationIdFilter())  logging.basicConfig(     level=logging.INFO,     handlers=[handler] ) logger = logging.getLogger("agent_main")  # Configuration AGENT_ID = os.getenv("AGENT_ID", "worker_local_01") SUPPORTED_TASK_TYPES = os.getenv("SUPPORTED_TASK_TYPES", "") # e.g. "img2img,face_swap" MASTER_API_URL = os.getenv("MASTER_API_URL", "http://127.0.0.1:8000") AGENT_SECRET_TOKEN = os.getenv("AGENT_SECRET_TOKEN", "")  COMFY_API_URL = os.getenv("COMFY_API_URL", "http://127.0.0.1:8188") COMFY_WS_URL = os.getenv("COMFY_WS_URL", "ws://127.0.0.1:8188/ws") COMFY_INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/home/ubantu/comfyui/input") COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "/home/ubantu/comfyui/output")  MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "play.min.io:9000") MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "your_key") MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "your_secret") MINIO_INPUT_BUCKET = os.getenv("MINIO_INPUT_BUCKET", "comfyui-input") MINIO_RESULT_BUCKET = os.getenv("MINIO_RESULT_BUCKET", "comfyui-output")  class ComfyAgent:     def __init__(self):         self.comfy_client = ComfyClient(base_url=COMFY_API_URL)         self.patcher = WorkflowPatcher(workflows_dir=os.path.join(os.path.dirname(__file__), "workflows"))         self.master_client = httpx.AsyncClient(             base_url=MASTER_API_URL,             headers={"Authorization": f"Bearer {AGENT_SECRET_TOKEN}"},             timeout=30.0         )          # Init MinIO         try:             self.minio_client = Minio(                 MINIO_ENDPOINT,                 access_key=MINIO_ACCESS_KEY,                 secret_key=MINIO_SECRET_KEY,                 secure=False  # Set to True if using HTTPS             )             logger.info("MinIO client initialized")         except Exception as e:             logger.error(f"Failed to init MinIO: {e}")             self.minio_client = None          self.current_task_id: Optional[str] = None         self.current_prompt_id: Optional[str] = None         self.task_completed_event = asyncio.Event()         self.task_result: Optional[str] = None         self.task_error: Optional[str] = None         self.running = False      async def report_heartbeat(self):         try:             status = "running" if self.current_task_id else "idle"             await self.master_client.post("/api/agent/task/heartbeat", json={                 "agent_id": AGENT_ID,                 "types": SUPPORTED_TASK_TYPES,                 "status": status             })             if self.current_task_id:                 # Add task heartbeat specifically                 await self.master_client.post("/api/agent/task/task_heartbeat", json={                     "task_id": self.current_task_id                 })         except Exception as e:             logger.debug(f"Failed to report heartbeat: {e}")      async def heartbeat_loop(self):         logger.info(f"Agent {AGENT_ID} started heartbeat loop...")         while getattr(self, 'running', True):             await self.report_heartbeat()             await asyncio.sleep(15)  # Send heartbeat every 15 seconds      async def report_status(self, task_id: str, status: str, progress: float = 0.0, error: str = ""):         try:             await self.master_client.post("/api/agent/task/status", json={                 "task_id": task_id,                 "agent_id": AGENT_ID,                 "status": status,                 "progress": progress,                 "error": error             })         except Exception as e:             logger.error(f"Failed to report status for task {task_id}: {e}")      async def report_complete(self, task_id: str, result_path: str):         try:             await self.master_client.post("/api/agent/task/complete", json={                 "task_id": task_id,                 "agent_id": AGENT_ID,                 "result": result_path             })         except Exception as e:             logger.error(f"Failed to report completion for task {task_id}: {e}")      async def ws_listener_loop(self):         client_id = f"agent_{AGENT_ID}"         uri = f"{COMFY_WS_URL}?clientId={client_id}"          while getattr(self, 'running', True):             try:                 async with websockets.connect(uri, max_size=None, ping_interval=20, ping_timeout=20) as websocket:                     logger.info(f"Connected to ComfyUI WebSocket at {uri}")                     while True:                         try:                             # Use timeout to periodically check connection state                             message = await asyncio.wait_for(websocket.recv(), timeout=60.0)                         except asyncio.TimeoutError:                             if websocket.closed:                                 logger.error("WebSocket closed unexpectedly")                                 break                             try:                                 await websocket.ping()                             except Exception as e:                                 logger.error(f"WebSocket ping failed: {e}")                                 break                             continue                          if isinstance(message, bytes):                             continue                          data = json.loads(message)                         msg_type = data.get("type")                         data_content = data.get("data", {})                          prompt_id = data_content.get("prompt_id")                          if not prompt_id or prompt_id != self.current_prompt_id:                             continue                          if msg_type == "execution_start":                             logger.info(f"Execution started for prompt {prompt_id}")                             if self.current_task_id:                                 await self.report_status(self.current_task_id, "running")                          elif msg_type == "progress":                             value = data_content.get("value", 0)                             max_val = data_content.get("max", 1)                             if max_val > 0 and self.current_task_id:                                 progress = value / max_val                                 await self.report_status(self.current_task_id, "running", progress=progress)                          elif msg_type == "executing":                             node = data_content.get("node")                             if node is None:                                 logger.info(f"Execution fully completed for prompt {prompt_id}")                                 self.task_completed_event.set()                          elif msg_type == "execution_success":                             logger.info(f"Execution success received for prompt {prompt_id}")                             self.task_completed_event.set()                          elif msg_type == "executed":                             logger.info(f"Node executed for prompt {prompt_id}")                             output = data_content.get("output", {})                             images = output.get("images", [])                             gifs = output.get("gifs", [])                             videos = output.get("videos", [])                              result_path = ""                             if images:                                 img = images[0]                                 result_path = f"{img.get('subfolder', '')}/{img.get('filename')}".lstrip('/')                             elif gifs:                                 gif = gifs[0]                                 result_path = f"{gif.get('subfolder', '')}/{gif.get('filename')}".lstrip('/')                             elif videos:                                 video = videos[0]                                 result_path = f"{video.get('subfolder', '')}/{video.get('filename')}".lstrip('/')                              if result_path:                                 self.task_result = result_path                                 # We now wait for executing node=None to set the completion event                          elif msg_type == "execution_error":                             error_msg = str(data_content.get("exception_message", "Unknown error"))                             logger.error(f"Execution error for prompt {prompt_id}: {error_msg}")                             self.task_error = error_msg                             self.task_completed_event.set()              except Exception as e:                 logger.error(f"WebSocket connection error: {e}")                 await asyncio.sleep(5)      def download_input_from_minio(self, object_name: str, local_path: str):         if not self.minio_client:             raise Exception("MinIO client not initialized")          bucket_name = "bot-data"         real_object_name = object_name          if object_name.startswith("template:"):             bucket_name = "bot-template"             real_object_name = object_name.replace("template:", "")          logger.info(f"Downloading {real_object_name} from MinIO bucket {bucket_name} to {local_path}")         self.minio_client.fget_object(bucket_name, real_object_name, local_path)      def upload_result_to_minio(self, local_path: str, object_name: str):         if not self.minio_client:             raise Exception("MinIO client not initialized")          content_type = "image/png"         if object_name.endswith(".mp4"):             content_type = "video/mp4"         elif object_name.endswith(".gif"):             content_type = "image/gif"         elif object_name.endswith(".jpg") or object_name.endswith(".jpeg"):             content_type = "image/jpeg"          logger.info(f"Uploading {local_path} to MinIO bucket {MINIO_RESULT_BUCKET} as {object_name}")         self.minio_client.fput_object(MINIO_RESULT_BUCKET, object_name, local_path, content_type=content_type)      async def check_task_cancelled(self, task_id: str) -> bool:         try:             response = await self.master_client.get(f"/api/agent/task/check/{task_id}")             if response.status_code == 200:                 data = response.json()                 if data.get("status") == "cancelled":                     return True         except Exception as e:             logger.debug(f"Failed to check task status: {e}")         return False      async def process_task(self, task: Dict[str, Any]):         trace_id = task.get("trace_id", "")         if trace_id:             correlation_id.set(trace_id)          task_id = str(task.get("task_id", ""))         if not task_id:             logger.error("Received task without task_id")             return          task_type = str(task.get("type", ""))         params_str = task.get("params", "{}")          if isinstance(params_str, str):             params = json.loads(params_str)         else:             params = params_str          logger.info(f"Processing task {task_id} of type {task_type}")         self.current_task_id = task_id         self.task_completed_event.clear()         self.task_result = None         self.task_error = None          downloaded_input_paths = []          try:             if await self.check_task_cancelled(task_id):                 logger.info(f"Task {task_id} was cancelled before processing.")                 return              # Helper for downloading and uploading single image             async def process_single_image(img_filename: str, param_key: str):                 local_safe_filename = img_filename.replace("/", "_").replace("template:", "")                 local_img_path = os.path.join(COMFY_INPUT_DIR, local_safe_filename)                 try:                     await asyncio.to_thread(self.download_input_from_minio, img_filename, local_img_path)                     logger.info(f"Downloaded {param_key} to {local_img_path}")                     try:                         with open(local_img_path, "rb") as f:                             img_data = f.read()                         await self.comfy_client.upload_image(img_data, local_safe_filename)                         logger.info(f"Uploaded {local_safe_filename} to ComfyUI via API")                     except Exception as upload_err:                         logger.warning(f"Failed to upload {local_safe_filename} to ComfyUI via API: {upload_err}")                     params[param_key] = local_safe_filename                     if local_img_path not in downloaded_input_paths:                         downloaded_input_paths.append(local_img_path)                 except Exception as e:                     logger.error(f"Failed to process {param_key} {img_filename}: {e}")              # 1. Handle multi-image concurrent download if `images` list is provided             if "images" in params and isinstance(params["images"], list) and len(params["images"]) > 0:                 images_list = params["images"]                 tasks = []                 keys = ["image", "image2", "image3"]                 for i, img_filename in enumerate(images_list[:3]):                     tasks.append(process_single_image(img_filename, keys[i]))                 if tasks:                     await asyncio.gather(*tasks)             else:                 # Fallback to legacy single image keys                 legacy_tasks = []                 if "image" in params and params["image"]:                     legacy_tasks.append(process_single_image(params["image"], "image"))                 if "image2" in params and params["image2"]:                     legacy_tasks.append(process_single_image(params["image2"], "image2"))                 if legacy_tasks:                     await asyncio.gather(*legacy_tasks)              # Also check for other potential image inputs (like face_image, body_image, video)             other_tasks = []             for key in ["face_image", "body_image", "video"]:                 if key in params and params[key]:                     other_tasks.append(process_single_image(params[key], key))             if other_tasks:                 await asyncio.gather(*other_tasks)              # 2. Load and patch workflow             workflow = self.patcher.load_workflow(task_type)             if not workflow:                 raise ValueError(f"Workflow for {task_type} not found")              patched_workflow = self.patcher.patch_workflow(task_type, workflow, params)              # 3. Submit to ComfyUI             client_id = f"agent_{AGENT_ID}"             self.current_prompt_id = await self.comfy_client.queue_prompt(patched_workflow, client_id)             logger.info(f"Submitted task {task_id} to ComfyUI, prompt_id: {self.current_prompt_id}")              await self.report_status(task_id, "running")              # 4. Wait for completion (via WS listener)             # Timeout after 10 minutes to avoid hanging forever             try:                 await asyncio.wait_for(self.task_completed_event.wait(), timeout=600.0)             except asyncio.TimeoutError:                 logger.warning(f"Task execution timed out for {task_id}, will attempt to fetch result from history.")              if self.task_error:                 raise Exception(self.task_error)              if not self.task_result:                 logger.info(f"Task result not set via WS, checking history for prompt {self.current_prompt_id}")                 try:                     history = await self.comfy_client.get_history(self.current_prompt_id)                     if history and self.current_prompt_id in history:                         outputs = history[self.current_prompt_id].get("outputs", {})                         for node_id, node_output in outputs.items():                             images = node_output.get("images", [])                             gifs = node_output.get("gifs", [])                             videos = node_output.get("videos", [])                              if images:                                 img = images[0]                                 self.task_result = f"{img.get('subfolder', '')}/{img.get('filename')}".lstrip('/')                                 break                             elif gifs:                                 gif = gifs[0]                                 self.task_result = f"{gif.get('subfolder', '')}/{gif.get('filename')}".lstrip('/')                                 break                             elif videos:                                 video = videos[0]                                 self.task_result = f"{video.get('subfolder', '')}/{video.get('filename')}".lstrip('/')                                 break                 except Exception as e:                     logger.warning(f"Failed to fetch history: {e}")              if not self.task_result:                 raise Exception("Task completed but no result path found")              if await self.check_task_cancelled(task_id):                 logger.info(f"Task {task_id} was cancelled during execution, skipping upload.")                 return              # 5. Fetch result from ComfyUI API and Upload to MinIO             # We must fetch the file via the ComfyUI /view API since Agent might not have direct local disk access             # or the file might be in temp/output directories on the ComfyUI server.             try:                 # Assuming task_result format is like "subfolder/filename.png" or "filename.png"                 parts = self.task_result.split('/')                 if len(parts) > 1:                     subfolder = '/'.join(parts[:-1])                     filename = parts[-1]                 else:                     subfolder = ""                     filename = self.task_result                  # We need to determine the type based on the path. Often it's 'output', but if it contains 'temp'                 # (like ComfyUI_temp_xxx), it might be in the 'temp' type.                 # However, get_view defaults to 'output' or 'temp' based on how ComfyUI saves it.                 view_type = "temp" if "temp" in filename.lower() else "output"                  logger.info(f"Fetching result {filename} from ComfyUI API (subfolder: '{subfolder}', type: '{view_type}')")                  # We use the existing comfy_client.get_view method                 file_data = await self.comfy_client.get_view(filename, subfolder, type=view_type)                  # Upload the fetched bytes directly to MinIO                 import io                 content_type = "image/png"                 if filename.endswith(".mp4"):                     content_type = "video/mp4"                 elif filename.endswith(".gif"):                     content_type = "image/gif"                 elif filename.endswith(".jpg") or filename.endswith(".jpeg"):                     content_type = "image/jpeg"                  logger.info(f"Uploading result {self.task_result} to MinIO bucket {MINIO_RESULT_BUCKET}")                 await asyncio.to_thread(                     self.minio_client.put_object,                     MINIO_RESULT_BUCKET,                     self.task_result,                     io.BytesIO(file_data),                     len(file_data),                     content_type=content_type                 )              except Exception as e:                 logger.error(f"Failed to fetch from ComfyUI or upload to MinIO: {e}")                 raise Exception(f"Result processing failed: {e}")              # 6. Report completion             await self.report_complete(task_id, self.task_result)             logger.info(f"Task {task_id} completed successfully")          except Exception as e:             logger.error(f"Task {task_id} failed: {e}")             await self.report_status(task_id, "failed", error=str(e))         finally:             self.current_task_id = None             self.current_prompt_id = None             for path in downloaded_input_paths:                 try:                     if os.path.exists(path):                         os.remove(path)                         logger.info(f"Cleaned up input file: {path}")                 except Exception as e:                     logger.warning(f"Failed to clean up input file {path}: {e}")      async def poll_loop(self):         logger.info(f"Agent {AGENT_ID} started polling {MASTER_API_URL} for tasks (types: {SUPPORTED_TASK_TYPES or 'all'})...")         while getattr(self, 'running', True):             try:                 # Poll for tasks with optional type filtering                 params = {}                 if SUPPORTED_TASK_TYPES:                     params["types"] = SUPPORTED_TASK_TYPES                  response = await self.master_client.get("/api/agent/task/pop", params=params)                 if response.status_code == 200:                     data = response.json()                     task = data.get("task")                     if task:                         await self.process_task(task)                         continue  # Immediately poll again after finishing                 elif response.status_code != 404: # 404 means no tasks, which is fine                     logger.warning(f"Unexpected response from master: {response.status_code}")              except httpx.RequestError as e:                 logger.error(f"Connection to master failed: {e}")             except Exception as e:                 logger.error(f"Polling error: {e}")              # Wait before next poll             await asyncio.sleep(2)      async def start(self):         # Ensure directories exist         os.makedirs(COMFY_INPUT_DIR, exist_ok=True)         os.makedirs(COMFY_OUTPUT_DIR, exist_ok=True)          # Start WS listener, polling loops, and heartbeat         self.running = True         self.tasks = [             asyncio.create_task(self.ws_listener_loop()),             asyncio.create_task(self.poll_loop()),             asyncio.create_task(self.heartbeat_loop())         ]         await asyncio.gather(*self.tasks)      async def shutdown(self):         logger.info("Initiating graceful shutdown...")         self.running = False          # If there is a task currently running, report it as failed/interrupted back to master         if self.current_task_id:             logger.info(f"Returning task {self.current_task_id} to master due to shutdown")             try:                 await self.report_status(                     self.current_task_id,                     "failed",                     error="Agent was shut down while processing the task. Task should be retried."                 )             except Exception as e:                 logger.error(f"Failed to report task failure during shutdown: {e}")          # Cancel all running background loops         for task in self.tasks:             task.cancel()          # Close HTTP clients         await self.master_client.aclose()         await self.comfy_client.close()         logger.info("Shutdown complete.")  if __name__ == "__main__":     agent = ComfyAgent()      # Setup graceful shutdown signals     import signal     import sys     loop = asyncio.get_event_loop()      if sys.platform != 'win32':         for sig in (signal.SIGINT, signal.SIGTERM):             loop.add_signal_handler(                 sig,                 lambda: asyncio.create_task(agent.shutdown())             )      try:         loop.run_until_complete(agent.start())     except asyncio.CancelledError:         pass     except KeyboardInterrupt:         # 捕获 Ctrl+C，触发优雅退出逻辑，防止 Master 端任务卡死         loop.run_until_complete(agent.shutdown())     finally:         loop.close() (duplicate-code) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==comfy_agent2.workflow_patcher:[5:213] ==comfy_agent4.workflow_patcher:[5:213] logger = logging.getLogger(__name__)  class WorkflowPatcher:     def __init__(self, workflows_dir: str):         self.workflows_dir = workflows_dir         self.mappings = self.load_mappings()      def load_mappings(self) -> Dict[str, Any]:         mapping_path = os.path.join(self.workflows_dir, "mappings.json")         if os.path.exists(mapping_path):             with open(mapping_path, "r", encoding="utf-8") as f:                 return json.load(f)         return {}      def strip_meta(self, data: Any) -> Any:         if isinstance(data, dict):             data.pop("_meta", None)             for key, value in data.items():                 data[key] = self.strip_meta(value)         elif isinstance(data, list):             for i in range(len(data)):                 data[i] = self.strip_meta(data[i])         return data      def load_workflow(self, task_type: str) -> Optional[Dict[str, Any]]:         filename = f"{task_type}.json"         # Map task types to filenames (matching backend worker.py logic)         if task_type == "img2img":             filename = "Qwen-Rapid-AIO.json"         elif task_type == "face_swap":             filename = "face_swap.json"         elif task_type == "video_insert":             filename = "perfect_video_insert.json"         elif task_type == "video_edit":             filename = "perfect_video_edit.json"         elif task_type == "face_video":             filename = "face_video.json"         elif task_type == "t2i-pornmaster-turbo":             filename = "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json"         elif task_type == "i2i_pro":             filename = "i2i_pro.json"         elif task_type == "img2img_lora":             filename = "Qwen-Rapid-AIO.json"         elif task_type == "ltx_video":             filename = "LTX 2.3 I2V.json"          path = os.path.join(self.workflows_dir, filename)         if not os.path.exists(path):             logger.error(f"Workflow file {path} not found")             return None          with open(path, "r", encoding="utf-8") as f:             data = json.load(f)             data = self.strip_meta(data)              if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):                 logger.warning(f"Workflow {filename} seems to be in UI format (contains 'nodes' list). Please export in API format.")             return data      def patch_workflow(self, task_type: str, workflow: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:         # Deep copy to avoid modifying template         wf = json.loads(json.dumps(workflow))          # Inject a random seed to prevent ComfyUI from fully caching the workflow         # which would result in no output generation and no history record.         import random         if "seed" not in params or params["seed"] is None:             # Use a smaller max integer to prevent "value_bigger_than_max" errors in rgthree nodes             params["seed"] = random.randint(1, 1125899906842624)          # Reload mappings to ensure it's up to date         self.mappings = self.load_mappings()          # If we have mappings, use them         mapping = self.mappings.get(task_type, {})          for key, value in params.items():             if key in mapping:                 node_id = str(mapping[key])                 input_name = mapping.get(f"{key}_input", "image") # Default input name                 if node_id in wf:                     if "inputs" not in wf[node_id]:                         wf[node_id]["inputs"] = {}                     wf[node_id]["inputs"][input_name] = value             else:                 # For heuristic patch of images where the mapping wasn't specific enough                 if key in ["image", "image2", "image3", "images", "face_image", "body_image"]:                     continue # Ignore heuristic patch for images to prevent overriding wrong nodes                  # Heuristic search                 self.heuristic_patch(wf, key, value)          # Dynamic JSON pruning for img2img task to avoid empty nodes and blank inputs         if task_type in ["img2img", "img2img_lora"]:             # Handle LoRA dynamically (default to no LoRA)             lora_name = params.get("lora_name", "")             if lora_name and str(lora_name).strip() != "":                 if "32" in wf and "inputs" in wf["32"]:                     wf["32"]["inputs"]["lora_name"] = lora_name                     if params.get("lora_strength") is not None:                         wf["32"]["inputs"]["strength_model"] = float(params["lora_strength"])             else:                 # Strip LoRA node and connect KSampler (2) directly to Checkpoint (1)                 if "2" in wf and "inputs" in wf["2"]:                     wf["2"]["inputs"]["model"] = ["1", 0]                 if "32" in wf:                     wf.pop("32", None)              # 3 is the TextEncodeQwenImageEditPlus node             text_encode_node_id = str(mapping.get("prompt", "3"))              # Clean up image2 if not provided             if "image2" not in params or not params["image2"]:                 if text_encode_node_id in wf and "inputs" in wf[text_encode_node_id]:                     wf[text_encode_node_id]["inputs"].pop("image2", None)                 node_to_pop = str(mapping.get("image2", "20"))                 if node_to_pop in wf:                     wf.pop(node_to_pop, None)                 if "21" in wf:                     wf.pop("21", None) # ImageScaleToTotalPixels node 21              # Clean up image3 if not provided             if "image3" not in params or not params["image3"]:                 if text_encode_node_id in wf and "inputs" in wf[text_encode_node_id]:                     wf[text_encode_node_id]["inputs"].pop("image3", None)                 node_to_pop = str(mapping.get("image3", "30"))                 if node_to_pop in wf:                     wf.pop(node_to_pop, None)                 if "31" in wf:                     wf.pop("31", None) # ImageScaleToTotalPixels node 31          elif task_type == "ltx_video":             # Remove the preview override node as it causes AttributeError in API mode (serv.last_node_id is None)             if "210" in wf:                 wf.pop("210", None)             if "5" in wf:                 wf.pop("5", None)             if "59" in wf:                 wf.pop("59", None)             # Route Node 7 directly to Node 8             if "8" in wf and "inputs" in wf["8"]:                 wf["8"]["inputs"]["model"] = ["7", 0]              # Prevent caching of output nodes by ensuring a unique filename_prefix per task             # Using random integer as task_id if not present (since workflow_patcher only gets params)             unique_id = params.get("seed", random.randint(1, 1125899906842624))             for node_id, node in wf.items():                 if isinstance(node, dict) and node.get("class_type") == "VHS_VideoCombine":                     if "inputs" in node:                         node["inputs"]["filename_prefix"] = f"ltx_video_{unique_id}_{node_id}"          return wf      def heuristic_patch(self, workflow: Dict[str, Any], key: str, value: Any):         # This is a best-effort patcher for API format workflows         for node_id, node in workflow.items():             if not isinstance(node, dict) or "inputs" not in node:                 continue              inputs = node["inputs"]             class_type = node.get("class_type", "")              if key == "prompt" and ("CLIPTextEncode" in class_type or "Prompt" in class_type or "TextEncode" in class_type):                 # Ensure we only patch Positive Prompts, not Negative Prompts                 meta_title = node.get("_meta", {}).get("title", "").lower()                 if "negative" not in meta_title:                     if "text" in inputs:                         inputs["text"] = value                     if "prompt" in inputs:                         inputs["prompt"] = value              elif key == "seed" and ("Sampler" in class_type or "Seed" in class_type):                 # Only inject seed if the current value is a placeholder or -1, or if we passed None but we shouldn't because json.loads might convert it                 if "seed" in inputs:                     if inputs["seed"] == -1 or inputs["seed"] is None:                         inputs["seed"] = value                 if "noise_seed" in inputs:                     if inputs["noise_seed"] == -1 or inputs["noise_seed"] is None:                         inputs["noise_seed"] = value              elif key == "steps" and "Sampler" in class_type:                 if "steps" in inputs:                     inputs["steps"] = value              elif key == "cfg" and "Sampler" in class_type:                 if "cfg" in inputs:                     inputs["cfg"] = value              elif key == "width" and "EmptyLatentImage" in class_type:                 inputs["width"] = value              elif key == "height" and "EmptyLatentImage" in class_type:                 inputs["height"] = value              elif key == "width" and "FindPerfectResolution" in class_type:                 inputs["desired_width"] = value              elif key == "height" and "FindPerfectResolution" in class_type:                 inputs["desired_height"] = value              elif key == "lora_name" and "Power Lora Loader (rgthree)" in class_type:                 if str(node_id) == "272":                     inputs["lora_1"] = {"on": True, "lora": f"{value}_high_noise.safetensors", "strength": 1}                 elif str(node_id) == "273":                     inputs["lora_1"] = {"on": True, "lora": f"{value}_low_noise.safetensors", "strength": 1}              elif key == "length" and "PainterI2V" in class_type:                 inputs["length"] = value (duplicate-code) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==comfy_agent1.workflow_patcher:[5:213] ==comfy_agent5.workflow_patcher:[5:213] logger = logging.getLogger(__name__)  class WorkflowPatcher:     def __init__(self, workflows_dir: str):         self.workflows_dir = workflows_dir         self.mappings = self.load_mappings()      def load_mappings(self) -> Dict[str, Any]:         mapping_path = os.path.join(self.workflows_dir, "mappings.json")         if os.path.exists(mapping_path):             with open(mapping_path, "r", encoding="utf-8") as f:                 return json.load(f)         return {}      def strip_meta(self, data: Any) -> Any:         if isinstance(data, dict):             data.pop("_meta", None)             for key, value in data.items():                 data[key] = self.strip_meta(value)         elif isinstance(data, list):             for i in range(len(data)):                 data[i] = self.strip_meta(data[i])         return data      def load_workflow(self, task_type: str) -> Optional[Dict[str, Any]]:         filename = f"{task_type}.json"         # Map task types to filenames (matching backend worker.py logic)         if task_type == "img2img":             filename = "Qwen-Rapid-AIO.json"         elif task_type == "face_swap":             filename = "face_swap.json"         elif task_type == "video_insert":             filename = "perfect_video_insert.json"         elif task_type == "video_edit":             filename = "perfect_video_edit.json"         elif task_type == "face_video":             filename = "face_video.json"         elif task_type == "t2i-pornmaster-turbo":             filename = "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json"         elif task_type == "i2i_pro":             filename = "i2i_pro.json"         elif task_type == "img2img_lora":             filename = "Qwen-Rapid-AIO.json"         elif task_type == "ltx_video":             filename = "LTX 2.3 I2V.json"          path = os.path.join(self.workflows_dir, filename)         if not os.path.exists(path):             logger.error(f"Workflow file {path} not found")             return None          with open(path, "r", encoding="utf-8") as f:             data = json.load(f)             data = self.strip_meta(data)              if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):                 logger.warning(f"Workflow {filename} seems to be in UI format (contains 'nodes' list). Please export in API format.")             return data      def patch_workflow(self, task_type: str, workflow: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:         # Deep copy to avoid modifying template         wf = json.loads(json.dumps(workflow))          # Inject a random seed to prevent ComfyUI from fully caching the workflow         # which would result in no output generation and no history record.         import random         if "seed" not in params or params["seed"] is None:             # Use a smaller max integer to prevent "value_bigger_than_max" errors in rgthree nodes             params["seed"] = random.randint(1, 1125899906842624)          # Reload mappings to ensure it's up to date         self.mappings = self.load_mappings()          # If we have mappings, use them         mapping = self.mappings.get(task_type, {})          for key, value in params.items():             if key in mapping:                 node_id = str(mapping[key])                 input_name = mapping.get(f"{key}_input", "image") # Default input name                 if node_id in wf:                     if "inputs" not in wf[node_id]:                         wf[node_id]["inputs"] = {}                     wf[node_id]["inputs"][input_name] = value             else:                 # For heuristic patch of images where the mapping wasn't specific enough                 if key in ["image", "image2", "image3", "images", "face_image", "body_image"]:                     continue # Ignore heuristic patch for images to prevent overriding wrong nodes                  # Heuristic search                 self.heuristic_patch(wf, key, value)          # Dynamic JSON pruning for img2img task to avoid empty nodes and blank inputs         if task_type in ["img2img", "img2img_lora"]:             # Handle LoRA dynamically (default to no LoRA)             lora_name = params.get("lora_name", "")             if lora_name and str(lora_name).strip() != "":                 if "32" in wf and "inputs" in wf["32"]:                     wf["32"]["inputs"]["lora_name"] = lora_name                     if params.get("lora_strength") is not None:                         wf["32"]["inputs"]["strength_model"] = float(params["lora_strength"])             else:                 # Strip LoRA node and connect KSampler (2) directly to Checkpoint (1)                 if "2" in wf and "inputs" in wf["2"]:                     wf["2"]["inputs"]["model"] = ["1", 0]                 if "32" in wf:                     wf.pop("32", None)              # 3 is the TextEncodeQwenImageEditPlus node             text_encode_node_id = str(mapping.get("prompt", "3"))              # Clean up image2 if not provided             if "image2" not in params or not params["image2"]:                 if text_encode_node_id in wf and "inputs" in wf[text_encode_node_id]:                     wf[text_encode_node_id]["inputs"].pop("image2", None)                 node_to_pop = str(mapping.get("image2", "20"))                 if node_to_pop in wf:                     wf.pop(node_to_pop, None)                 if "21" in wf:                     wf.pop("21", None) # ImageScaleToTotalPixels node 21              # Clean up image3 if not provided             if "image3" not in params or not params["image3"]:                 if text_encode_node_id in wf and "inputs" in wf[text_encode_node_id]:                     wf[text_encode_node_id]["inputs"].pop("image3", None)                 node_to_pop = str(mapping.get("image3", "30"))                 if node_to_pop in wf:                     wf.pop(node_to_pop, None)                 if "31" in wf:                     wf.pop("31", None) # ImageScaleToTotalPixels node 31          elif task_type == "ltx_video":             # Remove the preview override node as it causes AttributeError in API mode (serv.last_node_id is None)             if "210" in wf:                 wf.pop("210", None)             if "5" in wf:                 wf.pop("5", None)             if "59" in wf:                 wf.pop("59", None)             # Route Node 7 directly to Node 8             if "8" in wf and "inputs" in wf["8"]:                 wf["8"]["inputs"]["model"] = ["7", 0]              # Prevent caching of output nodes by ensuring a unique filename_prefix per task             # Using random integer as task_id if not present (since workflow_patcher only gets params)             unique_id = params.get("seed", random.randint(1, 1125899906842624))             for node_id, node in wf.items():                 if isinstance(node, dict) and node.get("class_type") == "VHS_VideoCombine":                     if "inputs" in node:                         node["inputs"]["filename_prefix"] = f"ltx_video_{unique_id}_{node_id}"          return wf      def heuristic_patch(self, workflow: Dict[str, Any], key: str, value: Any):         # This is a best-effort patcher for API format workflows         for node_id, node in workflow.items():             if not isinstance(node, dict) or "inputs" not in node:                 continue              inputs = node["inputs"]             class_type = node.get("class_type", "")              if key == "prompt" and ("CLIPTextEncode" in class_type or "Prompt" in class_type or "TextEncode" in class_type):                 # Ensure we only patch Positive Prompts, not Negative Prompts                 meta_title = node.get("_meta", {}).get("title", "").lower()                 if "negative" not in meta_title:                     if "text" in inputs:                         inputs["text"] = value                     if "prompt" in inputs:                         inputs["prompt"] = value              elif key == "seed" and ("Sampler" in class_type or "Seed" in class_type):                 # Only inject seed if the current value is a placeholder or -1, or if we passed None but we shouldn't because json.loads might convert it                 if "seed" in inputs:                     if inputs["seed"] == -1 or inputs["seed"] is None:                         inputs["seed"] = value                 if "noise_seed" in inputs:                     if inputs["noise_seed"] == -1 or inputs["noise_seed"] is None:                         inputs["noise_seed"] = value              elif key == "steps" and "Sampler" in class_type:                 if "steps" in inputs:                     inputs["steps"] = value              elif key == "cfg" and "Sampler" in class_type:                 if "cfg" in inputs:                     inputs["cfg"] = value              elif key == "width" and "EmptyLatentImage" in class_type:                 inputs["width"] = value              elif key == "height" and "EmptyLatentImage" in class_type:                 inputs["height"] = value              elif key == "width" and "FindPerfectResolution" in class_type:                 inputs["desired_width"] = value              elif key == "height" and "FindPerfectResolution" in class_type:                 inputs["desired_height"] = value              elif key == "lora_name" and "Power Lora Loader (rgthree)" in class_type:                 if str(node_id) == "272":                     inputs["lora_1"] = {"on": True, "lora": f"{value}_high_noise.safetensors", "strength": 1}                 elif str(node_id) == "273":                     inputs["lora_1"] = {"on": True, "lora": f"{value}_low_noise.safetensors", "strength": 1}              elif key == "length" and "PainterI2V" in class_type:                 inputs["length"] = value (duplicate-code) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==comfy_agent2.comfy_client:[4:82] ==comfy_agent4.comfy_client:[4:82] logger = logging.getLogger(__name__)  class ComfyClient:     def __init__(self, base_url: str):         self.base_url = base_url         self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)      async def check_connection(self) -> bool:         try:             response = await self.client.get("/system_stats")             return response.status_code == 200         except Exception as e:             logger.error(f"ComfyUI connection failed: {e}")             return False      async def upload_image(self, file_content: bytes, filename: str, subfolder: str = "") -> Dict[str, Any]:         """         Upload an image to ComfyUI input directory.         """         # The multipart format expected by ComfyUI         files = {"image": (filename, file_content, "image/png")}         data = {"overwrite": "true"}         if subfolder:             data["subfolder"] = subfolder          # Use multipart explicitly         response = await self.client.post("/upload/image", files=files, data=data)         if response.status_code != 200:             logger.error(f"ComfyUI upload error: {response.text}")         response.raise_for_status()         return response.json()      async def queue_prompt(self, prompt: Dict[str, Any], client_id: str) -> str:         """         Submit a workflow prompt to ComfyUI.         """         payload = {"prompt": prompt, "client_id": client_id}         response = await self.client.post("/prompt", json=payload)         if response.status_code != 200:             logger.error(f"ComfyUI prompt error: {response.text}")         response.raise_for_status()         data = response.json()         return data.get("prompt_id")      async def get_history(self, prompt_id: str) -> Dict[str, Any]:         """         Get execution history for a specific prompt_id.         """         response = await self.client.get(f"/history/{prompt_id}")         if response.status_code == 200:             return response.json()         return {}      async def get_view(self, filename: str, subfolder: str = "", type: str = "output") -> bytes:         """         Get the raw image/video data from ComfyUI output directory.         Includes a simple retry mechanism for file system I/O delays.         """         import asyncio         params = {"filename": filename, "subfolder": subfolder, "type": type}          max_retries = 3         for attempt in range(max_retries):             try:                 response = await self.client.get("/view", params=params)                 response.raise_for_status()                 return response.content             except Exception as e:                 if attempt < max_retries - 1:                     logger.warning(f"Failed to fetch {filename} (attempt {attempt + 1}/{max_retries}), retrying in 2 seconds... Error: {e}")                     await asyncio.sleep(2)                 else:                     logger.error(f"Failed to fetch {filename} after {max_retries} attempts.")                     raise e         raise Exception(f"Failed to fetch {filename}")      async def close(self):         await self.client.aclose() (duplicate-code) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==comfy_agent3.comfy_client:[4:82] ==comfy_agent5.comfy_client:[4:82] logger = logging.getLogger(__name__)  class ComfyClient:     def __init__(self, base_url: str):         self.base_url = base_url         self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)      async def check_connection(self) -> bool:         try:             response = await self.client.get("/system_stats")             return response.status_code == 200         except Exception as e:             logger.error(f"ComfyUI connection failed: {e}")             return False      async def upload_image(self, file_content: bytes, filename: str, subfolder: str = "") -> Dict[str, Any]:         """         Upload an image to ComfyUI input directory.         """         # The multipart format expected by ComfyUI         files = {"image": (filename, file_content, "image/png")}         data = {"overwrite": "true"}         if subfolder:             data["subfolder"] = subfolder          # Use multipart explicitly         response = await self.client.post("/upload/image", files=files, data=data)         if response.status_code != 200:             logger.error(f"ComfyUI upload error: {response.text}")         response.raise_for_status()         return response.json()      async def queue_prompt(self, prompt: Dict[str, Any], client_id: str) -> str:         """         Submit a workflow prompt to ComfyUI.         """         payload = {"prompt": prompt, "client_id": client_id}         response = await self.client.post("/prompt", json=payload)         if response.status_code != 200:             logger.error(f"ComfyUI prompt error: {response.text}")         response.raise_for_status()         data = response.json()         return data.get("prompt_id")      async def get_history(self, prompt_id: str) -> Dict[str, Any]:         """         Get execution history for a specific prompt_id.         """         response = await self.client.get(f"/history/{prompt_id}")         if response.status_code == 200:             return response.json()         return {}      async def get_view(self, filename: str, subfolder: str = "", type: str = "output") -> bytes:         """         Get the raw image/video data from ComfyUI output directory.         Includes a simple retry mechanism for file system I/O delays.         """         import asyncio         params = {"filename": filename, "subfolder": subfolder, "type": type}          max_retries = 3         for attempt in range(max_retries):             try:                 response = await self.client.get("/view", params=params)                 response.raise_for_status()                 return response.content             except Exception as e:                 if attempt < max_retries - 1:                     logger.warning(f"Failed to fetch {filename} (attempt {attempt + 1}/{max_retries}), retrying in 2 seconds... Error: {e}")                     await asyncio.sleep(2)                 else:                     logger.error(f"Failed to fetch {filename} after {max_retries} attempts.")                     raise e         raise Exception(f"Failed to fetch {filename}")      async def close(self):         await self.client.aclose() (duplicate-code) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==comfy_agent1.comfy_client:[33:90] ==comfy_agent4.comfy_client:[25:82]         data = {"overwrite": "true"}         if subfolder:             data["subfolder"] = subfolder          # Use multipart explicitly         response = await self.client.post("/upload/image", files=files, data=data)         if response.status_code != 200:             logger.error(f"ComfyUI upload error: {response.text}")         response.raise_for_status()         return response.json()      async def queue_prompt(self, prompt: Dict[str, Any], client_id: str) -> str:         """         Submit a workflow prompt to ComfyUI.         """         payload = {"prompt": prompt, "client_id": client_id}         response = await self.client.post("/prompt", json=payload)         if response.status_code != 200:             logger.error(f"ComfyUI prompt error: {response.text}")         response.raise_for_status()         data = response.json()         return data.get("prompt_id")      async def get_history(self, prompt_id: str) -> Dict[str, Any]:         """         Get execution history for a specific prompt_id.         """         response = await self.client.get(f"/history/{prompt_id}")         if response.status_code == 200:             return response.json()         return {}      async def get_view(self, filename: str, subfolder: str = "", type: str = "output") -> bytes:         """         Get the raw image/video data from ComfyUI output directory.         Includes a simple retry mechanism for file system I/O delays.         """         import asyncio         params = {"filename": filename, "subfolder": subfolder, "type": type}          max_retries = 3         for attempt in range(max_retries):             try:                 response = await self.client.get("/view", params=params)                 response.raise_for_status()                 return response.content             except Exception as e:                 if attempt < max_retries - 1:                     logger.warning(f"Failed to fetch {filename} (attempt {attempt + 1}/{max_retries}), retrying in 2 seconds... Error: {e}")                     await asyncio.sleep(2)                 else:                     logger.error(f"Failed to fetch {filename} after {max_retries} attempts.")                     raise e         raise Exception(f"Failed to fetch {filename}")      async def close(self):         await self.client.aclose() (duplicate-code) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==src.core.user_core:[16:30] ==src.quota:[43:55]         result = await session.execute(stmt)         user = result.scalar_one_or_none()          if user:             updated = False             if username and user.username != username:                 user.username = username                 updated = True             if full_name and user.full_name != full_name:                 user.full_name = full_name                 updated = True              if updated:                 await session.commit() (duplicate-code) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==src.web_api.dependencies:[61:74] ==src.web_api.routers.auth:[168:181]         stats = await permission_service.get_user_detailed_stats(user.telegram_id)         current_identity = stats.get("identity", user.current_identity)         current_group = stats.get("group", user.user_group)          allowed_identities = ["内门弟子", "核心弟子", "真传弟子"]         allowed_groups = ["金丹期", "元婴期", "化神期", "炼虚期", "合体期", "大乘期", "渡劫期"]          is_allowed_identity = current_identity in allowed_identities         is_allowed_group = current_group in allowed_groups          if not (is_allowed_identity or is_allowed_group):             raise HTTPException(                 status_code=status.HTTP_403_FORBIDDEN, (duplicate-code) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==comfy_agent1.comfy_client:[4:23] ==comfy_agent4.comfy_client:[4:24] logger = logging.getLogger(__name__)  class ComfyClient:     def __init__(self, base_url: str):         self.base_url = base_url         self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)      async def check_connection(self) -> bool:         try:             response = await self.client.get("/system_stats")             return response.status_code == 200         except Exception as e:             logger.error(f"ComfyUI connection failed: {e}")             return False      async def upload_image(self, file_content: bytes, filename: str, subfolder: str = "") -> Dict[str, Any]:         """         Upload an image or video to ComfyUI input directory.         """ (duplicate-code) |
| 1 | 代码重复 | **Low** | Similar lines in 2 files ==app.main:[30:41] ==app.routers.agent:[17:27]     redis = Redis.from_url(settings.redis_url)     try:         yield redis     finally:         await redis.close()  # Dependency for QueueManager async def get_queue_manager(redis: Redis = Depends(get_redis)):     return QueueManager(redis)  (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==comfy_agent2.agent_main:[16:551] ==comfy_agent4.agent_main:[16:551] load_dotenv()  # Unset proxies to prevent internal requests from being routed through system VPN/proxies for proxy_var in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:     os.environ.pop(proxy_var, None) os.environ["NO_PROXY"] = "*" os.environ["no_proxy"] = "*"  class CorrelationIdFilter(logging.Filter):     def filter(self, record):         trace_id = correlation_id.get()         record.correlation_id = f"TraceID: {trace_id}" if trace_id else "TraceID: None"         return True  log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s' handler = logging.StreamHandler(sys.stdout) handler.setFormatter(logging.Formatter(log_format)) handler.addFilter(CorrelationIdFilter())  logging.basicConfig(     level=logging.INFO,     handlers=[handler] ) logger = logging.getLogger("agent_main")  # Configuration AGENT_ID = os.getenv("AGENT_ID", "worker_local_01") SUPPORTED_TASK_TYPES = os.getenv("SUPPORTED_TASK_TYPES", "") # e.g. "img2img,face_swap" MASTER_API_URL = os.getenv("MASTER_API_URL", "http://127.0.0.1:8000") AGENT_SECRET_TOKEN = os.getenv("AGENT_SECRET_TOKEN", "")  COMFY_API_URL = os.getenv("COMFY_API_URL", "http://127.0.0.1:8188") COMFY_WS_URL = os.getenv("COMFY_WS_URL", "ws://127.0.0.1:8188/ws") COMFY_INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/home/ubantu/comfyui/input") COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "/home/ubantu/comfyui/output")  MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "play.min.io:9000") MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "your_key") MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "your_secret") MINIO_INPUT_BUCKET = os.getenv("MINIO_INPUT_BUCKET", "comfyui-input") MINIO_RESULT_BUCKET = os.getenv("MINIO_RESULT_BUCKET", "comfyui-output")  class ComfyAgent:     def __init__(self):         self.comfy_client = ComfyClient(base_url=COMFY_API_URL)         self.patcher = WorkflowPatcher(workflows_dir=os.path.join(os.path.dirname(__file__), "workflows"))         self.master_client = httpx.AsyncClient(             base_url=MASTER_API_URL,             headers={"Authorization": f"Bearer {AGENT_SECRET_TOKEN}"},             timeout=30.0         )          # Init MinIO         try:             self.minio_client = Minio(                 MINIO_ENDPOINT,                 access_key=MINIO_ACCESS_KEY,                 secret_key=MINIO_SECRET_KEY,                 secure=False  # Set to True if using HTTPS             )             logger.info("MinIO client initialized")         except Exception as e:             logger.error(f"Failed to init MinIO: {e}")             self.minio_client = None          self.current_task_id: Optional[str] = None         self.current_prompt_id: Optional[str] = None         self.task_completed_event = asyncio.Event()         self.task_result: Optional[str] = None         self.task_error: Optional[str] = None         self.running = False      async def report_heartbeat(self):         try:             status = "running" if self.current_task_id else "idle"             await self.master_client.post("/api/agent/task/heartbeat", json={                 "agent_id": AGENT_ID,                 "types": SUPPORTED_TASK_TYPES,                 "status": status             })             if self.current_task_id:                 # Add task heartbeat specifically                 await self.master_client.post("/api/agent/task/task_heartbeat", json={                     "task_id": self.current_task_id                 })         except Exception as e:             logger.debug(f"Failed to report heartbeat: {e}")      async def heartbeat_loop(self):         logger.info(f"Agent {AGENT_ID} started heartbeat loop...")         while getattr(self, 'running', True):             await self.report_heartbeat()             await asyncio.sleep(15)  # Send heartbeat every 15 seconds      async def report_status(self, task_id: str, status: str, progress: float = 0.0, error: str = ""):         try:             await self.master_client.post("/api/agent/task/status", json={                 "task_id": task_id,                 "agent_id": AGENT_ID,                 "status": status,                 "progress": progress,                 "error": error             })         except Exception as e:             logger.error(f"Failed to report status for task {task_id}: {e}")      async def report_complete(self, task_id: str, result_path: str):         try:             await self.master_client.post("/api/agent/task/complete", json={                 "task_id": task_id,                 "agent_id": AGENT_ID,                 "result": result_path             })         except Exception as e:             logger.error(f"Failed to report completion for task {task_id}: {e}")      async def ws_listener_loop(self):         client_id = f"agent_{AGENT_ID}"         uri = f"{COMFY_WS_URL}?clientId={client_id}"          while getattr(self, 'running', True):             try:                 async with websockets.connect(uri, max_size=None, ping_interval=20, ping_timeout=20) as websocket:                     logger.info(f"Connected to ComfyUI WebSocket at {uri}")                     while True:                         try:                             # Use timeout to periodically check connection state                             message = await asyncio.wait_for(websocket.recv(), timeout=60.0)                         except asyncio.TimeoutError:                             if websocket.closed:                                 logger.error("WebSocket closed unexpectedly")                                 break                             try:                                 await websocket.ping()                             except Exception as e:                                 logger.error(f"WebSocket ping failed: {e}")                                 break                             continue                          if isinstance(message, bytes):                             continue                          data = json.loads(message)                         msg_type = data.get("type")                         data_content = data.get("data", {})                          prompt_id = data_content.get("prompt_id")                          if not prompt_id or prompt_id != self.current_prompt_id:                             continue                          if msg_type == "execution_start":                             logger.info(f"Execution started for prompt {prompt_id}")                             if self.current_task_id:                                 await self.report_status(self.current_task_id, "running")                          elif msg_type == "progress":                             value = data_content.get("value", 0)                             max_val = data_content.get("max", 1)                             if max_val > 0 and self.current_task_id:                                 progress = value / max_val                                 await self.report_status(self.current_task_id, "running", progress=progress)                          elif msg_type == "executing":                             node = data_content.get("node")                             if node is None:                                 logger.info(f"Execution fully completed for prompt {prompt_id}")                                 self.task_completed_event.set()                          elif msg_type == "execution_success":                             logger.info(f"Execution success received for prompt {prompt_id}")                             self.task_completed_event.set()                          elif msg_type == "executed":                             logger.info(f"Node executed for prompt {prompt_id}")                             output = data_content.get("output", {})                             images = output.get("images", [])                             gifs = output.get("gifs", [])                             videos = output.get("videos", [])                              result_path = ""                             if images:                                 img = images[0]                                 result_path = f"{img.get('subfolder', '')}/{img.get('filename')}".lstrip('/')                             elif gifs:                                 gif = gifs[0]                                 result_path = f"{gif.get('subfolder', '')}/{gif.get('filename')}".lstrip('/')                             elif videos:                                 video = videos[0]                                 result_path = f"{video.get('subfolder', '')}/{video.get('filename')}".lstrip('/')                              if result_path:                                 self.task_result = result_path                                 # We now wait for executing node=None to set the completion event                          elif msg_type == "execution_error":                             error_msg = str(data_content.get("exception_message", "Unknown error"))                             logger.error(f"Execution error for prompt {prompt_id}: {error_msg}")                             self.task_error = error_msg                             self.task_completed_event.set()              except Exception as e:                 logger.error(f"WebSocket connection error: {e}")                 await asyncio.sleep(5)      def download_input_from_minio(self, object_name: str, local_path: str):         if not self.minio_client:             raise Exception("MinIO client not initialized")          bucket_name = "bot-data"         real_object_name = object_name          if object_name.startswith("template:"):             bucket_name = "bot-template"             real_object_name = object_name.replace("template:", "")          logger.info(f"Downloading {real_object_name} from MinIO bucket {bucket_name} to {local_path}")         self.minio_client.fget_object(bucket_name, real_object_name, local_path)      def upload_result_to_minio(self, local_path: str, object_name: str):         if not self.minio_client:             raise Exception("MinIO client not initialized")          content_type = "image/png"         if object_name.endswith(".mp4"):             content_type = "video/mp4"         elif object_name.endswith(".gif"):             content_type = "image/gif"         elif object_name.endswith(".jpg") or object_name.endswith(".jpeg"):             content_type = "image/jpeg"          logger.info(f"Uploading {local_path} to MinIO bucket {MINIO_RESULT_BUCKET} as {object_name}")         self.minio_client.fput_object(MINIO_RESULT_BUCKET, object_name, local_path, content_type=content_type)      async def check_task_cancelled(self, task_id: str) -> bool:         try:             response = await self.master_client.get(f"/api/agent/task/check/{task_id}")             if response.status_code == 200:                 data = response.json()                 if data.get("status") == "cancelled":                     return True         except Exception as e:             logger.debug(f"Failed to check task status: {e}")         return False      async def process_task(self, task: Dict[str, Any]):         trace_id = task.get("trace_id", "")         if trace_id:             correlation_id.set(trace_id)          task_id = str(task.get("task_id", ""))         if not task_id:             logger.error("Received task without task_id")             return          task_type = str(task.get("type", ""))         params_str = task.get("params", "{}")          if isinstance(params_str, str):             params = json.loads(params_str)         else:             params = params_str          logger.info(f"Processing task {task_id} of type {task_type}")         self.current_task_id = task_id         self.task_completed_event.clear()         self.task_result = None         self.task_error = None          downloaded_input_paths = []          try:             if await self.check_task_cancelled(task_id):                 logger.info(f"Task {task_id} was cancelled before processing.")                 return              # Helper for downloading and uploading single image             async def process_single_image(img_filename: str, param_key: str):                 local_safe_filename = img_filename.replace("/", "_").replace("template:", "")                 local_img_path = os.path.join(COMFY_INPUT_DIR, local_safe_filename)                 try:                     await asyncio.to_thread(self.download_input_from_minio, img_filename, local_img_path)                     logger.info(f"Downloaded {param_key} to {local_img_path}")                     try:                         with open(local_img_path, "rb") as f:                             img_data = f.read()                         await self.comfy_client.upload_image(img_data, local_safe_filename)                         logger.info(f"Uploaded {local_safe_filename} to ComfyUI via API")                     except Exception as upload_err:                         logger.warning(f"Failed to upload {local_safe_filename} to ComfyUI via API: {upload_err}")                     params[param_key] = local_safe_filename                     if local_img_path not in downloaded_input_paths:                         downloaded_input_paths.append(local_img_path)                 except Exception as e:                     logger.error(f"Failed to process {param_key} {img_filename}: {e}")              # 1. Handle multi-image concurrent download if `images` list is provided             if "images" in params and isinstance(params["images"], list) and len(params["images"]) > 0:                 images_list = params["images"]                 tasks = []                 keys = ["image", "image2", "image3"]                 for i, img_filename in enumerate(images_list[:3]):                     tasks.append(process_single_image(img_filename, keys[i]))                 if tasks:                     await asyncio.gather(*tasks)             else:                 # Fallback to legacy single image keys                 legacy_tasks = []                 if "image" in params and params["image"]:                     legacy_tasks.append(process_single_image(params["image"], "image"))                 if "image2" in params and params["image2"]:                     legacy_tasks.append(process_single_image(params["image2"], "image2"))                 if legacy_tasks:                     await asyncio.gather(*legacy_tasks)              # Also check for other potential image inputs (like face_image, body_image, video)             other_tasks = []             for key in ["face_image", "body_image", "video"]:                 if key in params and params[key]:                     other_tasks.append(process_single_image(params[key], key))             if other_tasks:                 await asyncio.gather(*other_tasks)              # 2. Load and patch workflow             workflow = self.patcher.load_workflow(task_type)             if not workflow:                 raise ValueError(f"Workflow for {task_type} not found")              patched_workflow = self.patcher.patch_workflow(task_type, workflow, params)              # 3. Submit to ComfyUI             client_id = f"agent_{AGENT_ID}"             self.current_prompt_id = await self.comfy_client.queue_prompt(patched_workflow, client_id)             logger.info(f"Submitted task {task_id} to ComfyUI, prompt_id: {self.current_prompt_id}")              await self.report_status(task_id, "running")              # 4. Wait for completion (via WS listener)             # Timeout after 10 minutes to avoid hanging forever             try:                 await asyncio.wait_for(self.task_completed_event.wait(), timeout=600.0)             except asyncio.TimeoutError:                 logger.warning(f"Task execution timed out for {task_id}, will attempt to fetch result from history.")              if self.task_error:                 raise Exception(self.task_error)              if not self.task_result:                 logger.info(f"Task result not set via WS, checking history for prompt {self.current_prompt_id}")                 try:                     history = await self.comfy_client.get_history(self.current_prompt_id)                     if history and self.current_prompt_id in history:                         outputs = history[self.current_prompt_id].get("outputs", {})                         for node_id, node_output in outputs.items():                             images = node_output.get("images", [])                             gifs = node_output.get("gifs", [])                             videos = node_output.get("videos", [])                              if images:                                 img = images[0]                                 self.task_result = f"{img.get('subfolder', '')}/{img.get('filename')}".lstrip('/')                                 break                             elif gifs:                                 gif = gifs[0]                                 self.task_result = f"{gif.get('subfolder', '')}/{gif.get('filename')}".lstrip('/')                                 break                             elif videos:                                 video = videos[0]                                 self.task_result = f"{video.get('subfolder', '')}/{video.get('filename')}".lstrip('/')                                 break                 except Exception as e:                     logger.warning(f"Failed to fetch history: {e}")              if not self.task_result:                 raise Exception("Task completed but no result path found")              if await self.check_task_cancelled(task_id):                 logger.info(f"Task {task_id} was cancelled during execution, skipping upload.")                 return              # 5. Fetch result from ComfyUI API and Upload to MinIO             # We must fetch the file via the ComfyUI /view API since Agent might not have direct local disk access             # or the file might be in temp/output directories on the ComfyUI server.             try:                 # Assuming task_result format is like "subfolder/filename.png" or "filename.png"                 parts = self.task_result.split('/')                 if len(parts) > 1:                     subfolder = '/'.join(parts[:-1])                     filename = parts[-1]                 else:                     subfolder = ""                     filename = self.task_result                  # We need to determine the type based on the path. Often it's 'output', but if it contains 'temp'                 # (like ComfyUI_temp_xxx), it might be in the 'temp' type.                 # However, get_view defaults to 'output' or 'temp' based on how ComfyUI saves it.                 view_type = "temp" if "temp" in filename.lower() else "output"                  logger.info(f"Fetching result {filename} from ComfyUI API (subfolder: '{subfolder}', type: '{view_type}')")                  # We use the existing comfy_client.get_view method                 file_data = await self.comfy_client.get_view(filename, subfolder, type=view_type)                  # Upload the fetched bytes directly to MinIO                 import io                 content_type = "image/png"                 if filename.endswith(".mp4"):                     content_type = "video/mp4"                 elif filename.endswith(".gif"):                     content_type = "image/gif"                 elif filename.endswith(".jpg") or filename.endswith(".jpeg"):                     content_type = "image/jpeg"                  logger.info(f"Uploading result {self.task_result} to MinIO bucket {MINIO_RESULT_BUCKET}")                 await asyncio.to_thread(                     self.minio_client.put_object,                     MINIO_RESULT_BUCKET,                     self.task_result,                     io.BytesIO(file_data),                     len(file_data),                     content_type=content_type                 )              except Exception as e:                 logger.error(f"Failed to fetch from ComfyUI or upload to MinIO: {e}")                 raise Exception(f"Result processing failed: {e}")              # 6. Report completion             await self.report_complete(task_id, self.task_result)             logger.info(f"Task {task_id} completed successfully")          except Exception as e:             logger.error(f"Task {task_id} failed: {e}")             await self.report_status(task_id, "failed", error=str(e))         finally:             self.current_task_id = None             self.current_prompt_id = None             for path in downloaded_input_paths:                 try:                     if os.path.exists(path):                         os.remove(path)                         logger.info(f"Cleaned up input file: {path}")                 except Exception as e:                     logger.warning(f"Failed to clean up input file {path}: {e}")      async def poll_loop(self):         logger.info(f"Agent {AGENT_ID} started polling {MASTER_API_URL} for tasks (types: {SUPPORTED_TASK_TYPES or 'all'})...")         while getattr(self, 'running', True):             try:                 # Poll for tasks with optional type filtering                 params = {}                 if SUPPORTED_TASK_TYPES:                     params["types"] = SUPPORTED_TASK_TYPES                  response = await self.master_client.get("/api/agent/task/pop", params=params)                 if response.status_code == 200:                     data = response.json()                     task = data.get("task")                     if task:                         await self.process_task(task)                         continue  # Immediately poll again after finishing                 elif response.status_code != 404: # 404 means no tasks, which is fine                     logger.warning(f"Unexpected response from master: {response.status_code}")              except httpx.RequestError as e:                 logger.error(f"Connection to master failed: {e}")             except Exception as e:                 logger.error(f"Polling error: {e}")              # Wait before next poll             await asyncio.sleep(2)      async def start(self):         # Ensure directories exist         os.makedirs(COMFY_INPUT_DIR, exist_ok=True)         os.makedirs(COMFY_OUTPUT_DIR, exist_ok=True)          # Start WS listener, polling loops, and heartbeat         self.running = True         self.tasks = [             asyncio.create_task(self.ws_listener_loop()),             asyncio.create_task(self.poll_loop()),             asyncio.create_task(self.heartbeat_loop())         ]         await asyncio.gather(*self.tasks)      async def shutdown(self):         logger.info("Initiating graceful shutdown...")         self.running = False          # If there is a task currently running, report it as failed/interrupted back to master         if self.current_task_id:             logger.info(f"Returning task {self.current_task_id} to master due to shutdown")             try:                 await self.report_status(                     self.current_task_id,                     "failed",                     error="Agent was shut down while processing the task. Task should be retried."                 )             except Exception as e:                 logger.error(f"Failed to report task failure during shutdown: {e}")          # Cancel all running background loops         for task in self.tasks:             task.cancel()          # Close HTTP clients         await self.master_client.aclose()         await self.comfy_client.close()         logger.info("Shutdown complete.")  if __name__ == "__main__":     agent = ComfyAgent()      # Setup graceful shutdown signals     import signal     import sys     loop = asyncio.get_event_loop()      if sys.platform != 'win32':         for sig in (signal.SIGINT, signal.SIGTERM):             loop.add_signal_handler(                 sig,                 lambda: asyncio.create_task(agent.shutdown())             )      try:         loop.run_until_complete(agent.start())     except asyncio.CancelledError:         pass     except KeyboardInterrupt:         # 捕获 Ctrl+C，触发优雅退出逻辑，防止 Master 端任务卡死         loop.run_until_complete(agent.shutdown())     finally:         loop.close() (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==comfy_agent1.agent_main:[16:551] ==comfy_agent5.agent_main:[16:551] load_dotenv()  # Unset proxies to prevent internal requests from being routed through system VPN/proxies for proxy_var in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:     os.environ.pop(proxy_var, None) os.environ["NO_PROXY"] = "*" os.environ["no_proxy"] = "*"  class CorrelationIdFilter(logging.Filter):     def filter(self, record):         trace_id = correlation_id.get()         record.correlation_id = f"TraceID: {trace_id}" if trace_id else "TraceID: None"         return True  log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s' handler = logging.StreamHandler(sys.stdout) handler.setFormatter(logging.Formatter(log_format)) handler.addFilter(CorrelationIdFilter())  logging.basicConfig(     level=logging.INFO,     handlers=[handler] ) logger = logging.getLogger("agent_main")  # Configuration AGENT_ID = os.getenv("AGENT_ID", "worker_local_01") SUPPORTED_TASK_TYPES = os.getenv("SUPPORTED_TASK_TYPES", "") # e.g. "img2img,face_swap" MASTER_API_URL = os.getenv("MASTER_API_URL", "http://127.0.0.1:8000") AGENT_SECRET_TOKEN = os.getenv("AGENT_SECRET_TOKEN", "")  COMFY_API_URL = os.getenv("COMFY_API_URL", "http://127.0.0.1:8188") COMFY_WS_URL = os.getenv("COMFY_WS_URL", "ws://127.0.0.1:8188/ws") COMFY_INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/home/ubantu/comfyui/input") COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "/home/ubantu/comfyui/output")  MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "play.min.io:9000") MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "your_key") MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "your_secret") MINIO_INPUT_BUCKET = os.getenv("MINIO_INPUT_BUCKET", "comfyui-input") MINIO_RESULT_BUCKET = os.getenv("MINIO_RESULT_BUCKET", "comfyui-output")  class ComfyAgent:     def __init__(self):         self.comfy_client = ComfyClient(base_url=COMFY_API_URL)         self.patcher = WorkflowPatcher(workflows_dir=os.path.join(os.path.dirname(__file__), "workflows"))         self.master_client = httpx.AsyncClient(             base_url=MASTER_API_URL,             headers={"Authorization": f"Bearer {AGENT_SECRET_TOKEN}"},             timeout=30.0         )          # Init MinIO         try:             self.minio_client = Minio(                 MINIO_ENDPOINT,                 access_key=MINIO_ACCESS_KEY,                 secret_key=MINIO_SECRET_KEY,                 secure=False  # Set to True if using HTTPS             )             logger.info("MinIO client initialized")         except Exception as e:             logger.error(f"Failed to init MinIO: {e}")             self.minio_client = None          self.current_task_id: Optional[str] = None         self.current_prompt_id: Optional[str] = None         self.task_completed_event = asyncio.Event()         self.task_result: Optional[str] = None         self.task_error: Optional[str] = None         self.running = False      async def report_heartbeat(self):         try:             status = "running" if self.current_task_id else "idle"             await self.master_client.post("/api/agent/task/heartbeat", json={                 "agent_id": AGENT_ID,                 "types": SUPPORTED_TASK_TYPES,                 "status": status             })             if self.current_task_id:                 # Add task heartbeat specifically                 await self.master_client.post("/api/agent/task/task_heartbeat", json={                     "task_id": self.current_task_id                 })         except Exception as e:             logger.debug(f"Failed to report heartbeat: {e}")      async def heartbeat_loop(self):         logger.info(f"Agent {AGENT_ID} started heartbeat loop...")         while getattr(self, 'running', True):             await self.report_heartbeat()             await asyncio.sleep(15)  # Send heartbeat every 15 seconds      async def report_status(self, task_id: str, status: str, progress: float = 0.0, error: str = ""):         try:             await self.master_client.post("/api/agent/task/status", json={                 "task_id": task_id,                 "agent_id": AGENT_ID,                 "status": status,                 "progress": progress,                 "error": error             })         except Exception as e:             logger.error(f"Failed to report status for task {task_id}: {e}")      async def report_complete(self, task_id: str, result_path: str):         try:             await self.master_client.post("/api/agent/task/complete", json={                 "task_id": task_id,                 "agent_id": AGENT_ID,                 "result": result_path             })         except Exception as e:             logger.error(f"Failed to report completion for task {task_id}: {e}")      async def ws_listener_loop(self):         client_id = f"agent_{AGENT_ID}"         uri = f"{COMFY_WS_URL}?clientId={client_id}"          while getattr(self, 'running', True):             try:                 async with websockets.connect(uri, max_size=None, ping_interval=20, ping_timeout=20) as websocket:                     logger.info(f"Connected to ComfyUI WebSocket at {uri}")                     while True:                         try:                             # Use timeout to periodically check connection state                             message = await asyncio.wait_for(websocket.recv(), timeout=60.0)                         except asyncio.TimeoutError:                             if websocket.closed:                                 logger.error("WebSocket closed unexpectedly")                                 break                             try:                                 await websocket.ping()                             except Exception as e:                                 logger.error(f"WebSocket ping failed: {e}")                                 break                             continue                          if isinstance(message, bytes):                             continue                          data = json.loads(message)                         msg_type = data.get("type")                         data_content = data.get("data", {})                          prompt_id = data_content.get("prompt_id")                          if not prompt_id or prompt_id != self.current_prompt_id:                             continue                          if msg_type == "execution_start":                             logger.info(f"Execution started for prompt {prompt_id}")                             if self.current_task_id:                                 await self.report_status(self.current_task_id, "running")                          elif msg_type == "progress":                             value = data_content.get("value", 0)                             max_val = data_content.get("max", 1)                             if max_val > 0 and self.current_task_id:                                 progress = value / max_val                                 await self.report_status(self.current_task_id, "running", progress=progress)                          elif msg_type == "executing":                             node = data_content.get("node")                             if node is None:                                 logger.info(f"Execution fully completed for prompt {prompt_id}")                                 self.task_completed_event.set()                          elif msg_type == "execution_success":                             logger.info(f"Execution success received for prompt {prompt_id}")                             self.task_completed_event.set()                          elif msg_type == "executed":                             logger.info(f"Node executed for prompt {prompt_id}")                             output = data_content.get("output", {})                             images = output.get("images", [])                             gifs = output.get("gifs", [])                             videos = output.get("videos", [])                              result_path = ""                             if images:                                 img = images[0]                                 result_path = f"{img.get('subfolder', '')}/{img.get('filename')}".lstrip('/')                             elif gifs:                                 gif = gifs[0]                                 result_path = f"{gif.get('subfolder', '')}/{gif.get('filename')}".lstrip('/')                             elif videos:                                 video = videos[0]                                 result_path = f"{video.get('subfolder', '')}/{video.get('filename')}".lstrip('/')                              if result_path:                                 self.task_result = result_path                                 # We now wait for executing node=None to set the completion event                          elif msg_type == "execution_error":                             error_msg = str(data_content.get("exception_message", "Unknown error"))                             logger.error(f"Execution error for prompt {prompt_id}: {error_msg}")                             self.task_error = error_msg                             self.task_completed_event.set()              except Exception as e:                 logger.error(f"WebSocket connection error: {e}")                 await asyncio.sleep(5)      def download_input_from_minio(self, object_name: str, local_path: str):         if not self.minio_client:             raise Exception("MinIO client not initialized")          bucket_name = "bot-data"         real_object_name = object_name          if object_name.startswith("template:"):             bucket_name = "bot-template"             real_object_name = object_name.replace("template:", "")          logger.info(f"Downloading {real_object_name} from MinIO bucket {bucket_name} to {local_path}")         self.minio_client.fget_object(bucket_name, real_object_name, local_path)      def upload_result_to_minio(self, local_path: str, object_name: str):         if not self.minio_client:             raise Exception("MinIO client not initialized")          content_type = "image/png"         if object_name.endswith(".mp4"):             content_type = "video/mp4"         elif object_name.endswith(".gif"):             content_type = "image/gif"         elif object_name.endswith(".jpg") or object_name.endswith(".jpeg"):             content_type = "image/jpeg"          logger.info(f"Uploading {local_path} to MinIO bucket {MINIO_RESULT_BUCKET} as {object_name}")         self.minio_client.fput_object(MINIO_RESULT_BUCKET, object_name, local_path, content_type=content_type)      async def check_task_cancelled(self, task_id: str) -> bool:         try:             response = await self.master_client.get(f"/api/agent/task/check/{task_id}")             if response.status_code == 200:                 data = response.json()                 if data.get("status") == "cancelled":                     return True         except Exception as e:             logger.debug(f"Failed to check task status: {e}")         return False      async def process_task(self, task: Dict[str, Any]):         trace_id = task.get("trace_id", "")         if trace_id:             correlation_id.set(trace_id)          task_id = str(task.get("task_id", ""))         if not task_id:             logger.error("Received task without task_id")             return          task_type = str(task.get("type", ""))         params_str = task.get("params", "{}")          if isinstance(params_str, str):             params = json.loads(params_str)         else:             params = params_str          logger.info(f"Processing task {task_id} of type {task_type}")         self.current_task_id = task_id         self.task_completed_event.clear()         self.task_result = None         self.task_error = None          downloaded_input_paths = []          try:             if await self.check_task_cancelled(task_id):                 logger.info(f"Task {task_id} was cancelled before processing.")                 return              # Helper for downloading and uploading single image             async def process_single_image(img_filename: str, param_key: str):                 local_safe_filename = img_filename.replace("/", "_").replace("template:", "")                 local_img_path = os.path.join(COMFY_INPUT_DIR, local_safe_filename)                 try:                     await asyncio.to_thread(self.download_input_from_minio, img_filename, local_img_path)                     logger.info(f"Downloaded {param_key} to {local_img_path}")                     try:                         with open(local_img_path, "rb") as f:                             img_data = f.read()                         await self.comfy_client.upload_image(img_data, local_safe_filename)                         logger.info(f"Uploaded {local_safe_filename} to ComfyUI via API")                     except Exception as upload_err:                         logger.warning(f"Failed to upload {local_safe_filename} to ComfyUI via API: {upload_err}")                     params[param_key] = local_safe_filename                     if local_img_path not in downloaded_input_paths:                         downloaded_input_paths.append(local_img_path)                 except Exception as e:                     logger.error(f"Failed to process {param_key} {img_filename}: {e}")              # 1. Handle multi-image concurrent download if `images` list is provided             if "images" in params and isinstance(params["images"], list) and len(params["images"]) > 0:                 images_list = params["images"]                 tasks = []                 keys = ["image", "image2", "image3"]                 for i, img_filename in enumerate(images_list[:3]):                     tasks.append(process_single_image(img_filename, keys[i]))                 if tasks:                     await asyncio.gather(*tasks)             else:                 # Fallback to legacy single image keys                 legacy_tasks = []                 if "image" in params and params["image"]:                     legacy_tasks.append(process_single_image(params["image"], "image"))                 if "image2" in params and params["image2"]:                     legacy_tasks.append(process_single_image(params["image2"], "image2"))                 if legacy_tasks:                     await asyncio.gather(*legacy_tasks)              # Also check for other potential image inputs (like face_image, body_image, video)             other_tasks = []             for key in ["face_image", "body_image", "video"]:                 if key in params and params[key]:                     other_tasks.append(process_single_image(params[key], key))             if other_tasks:                 await asyncio.gather(*other_tasks)              # 2. Load and patch workflow             workflow = self.patcher.load_workflow(task_type)             if not workflow:                 raise ValueError(f"Workflow for {task_type} not found")              patched_workflow = self.patcher.patch_workflow(task_type, workflow, params)              # 3. Submit to ComfyUI             client_id = f"agent_{AGENT_ID}"             self.current_prompt_id = await self.comfy_client.queue_prompt(patched_workflow, client_id)             logger.info(f"Submitted task {task_id} to ComfyUI, prompt_id: {self.current_prompt_id}")              await self.report_status(task_id, "running")              # 4. Wait for completion (via WS listener)             # Timeout after 10 minutes to avoid hanging forever             try:                 await asyncio.wait_for(self.task_completed_event.wait(), timeout=600.0)             except asyncio.TimeoutError:                 logger.warning(f"Task execution timed out for {task_id}, will attempt to fetch result from history.")              if self.task_error:                 raise Exception(self.task_error)              if not self.task_result:                 logger.info(f"Task result not set via WS, checking history for prompt {self.current_prompt_id}")                 try:                     history = await self.comfy_client.get_history(self.current_prompt_id)                     if history and self.current_prompt_id in history:                         outputs = history[self.current_prompt_id].get("outputs", {})                         for node_id, node_output in outputs.items():                             images = node_output.get("images", [])                             gifs = node_output.get("gifs", [])                             videos = node_output.get("videos", [])                              if images:                                 img = images[0]                                 self.task_result = f"{img.get('subfolder', '')}/{img.get('filename')}".lstrip('/')                                 break                             elif gifs:                                 gif = gifs[0]                                 self.task_result = f"{gif.get('subfolder', '')}/{gif.get('filename')}".lstrip('/')                                 break                             elif videos:                                 video = videos[0]                                 self.task_result = f"{video.get('subfolder', '')}/{video.get('filename')}".lstrip('/')                                 break                 except Exception as e:                     logger.warning(f"Failed to fetch history: {e}")              if not self.task_result:                 raise Exception("Task completed but no result path found")              if await self.check_task_cancelled(task_id):                 logger.info(f"Task {task_id} was cancelled during execution, skipping upload.")                 return              # 5. Fetch result from ComfyUI API and Upload to MinIO             # We must fetch the file via the ComfyUI /view API since Agent might not have direct local disk access             # or the file might be in temp/output directories on the ComfyUI server.             try:                 # Assuming task_result format is like "subfolder/filename.png" or "filename.png"                 parts = self.task_result.split('/')                 if len(parts) > 1:                     subfolder = '/'.join(parts[:-1])                     filename = parts[-1]                 else:                     subfolder = ""                     filename = self.task_result                  # We need to determine the type based on the path. Often it's 'output', but if it contains 'temp'                 # (like ComfyUI_temp_xxx), it might be in the 'temp' type.                 # However, get_view defaults to 'output' or 'temp' based on how ComfyUI saves it.                 view_type = "temp" if "temp" in filename.lower() else "output"                  logger.info(f"Fetching result {filename} from ComfyUI API (subfolder: '{subfolder}', type: '{view_type}')")                  # We use the existing comfy_client.get_view method                 file_data = await self.comfy_client.get_view(filename, subfolder, type=view_type)                  # Upload the fetched bytes directly to MinIO                 import io                 content_type = "image/png"                 if filename.endswith(".mp4"):                     content_type = "video/mp4"                 elif filename.endswith(".gif"):                     content_type = "image/gif"                 elif filename.endswith(".jpg") or filename.endswith(".jpeg"):                     content_type = "image/jpeg"                  logger.info(f"Uploading result {self.task_result} to MinIO bucket {MINIO_RESULT_BUCKET}")                 await asyncio.to_thread(                     self.minio_client.put_object,                     MINIO_RESULT_BUCKET,                     self.task_result,                     io.BytesIO(file_data),                     len(file_data),                     content_type=content_type                 )              except Exception as e:                 logger.error(f"Failed to fetch from ComfyUI or upload to MinIO: {e}")                 raise Exception(f"Result processing failed: {e}")              # 6. Report completion             await self.report_complete(task_id, self.task_result)             logger.info(f"Task {task_id} completed successfully")          except Exception as e:             logger.error(f"Task {task_id} failed: {e}")             await self.report_status(task_id, "failed", error=str(e))         finally:             self.current_task_id = None             self.current_prompt_id = None             for path in downloaded_input_paths:                 try:                     if os.path.exists(path):                         os.remove(path)                         logger.info(f"Cleaned up input file: {path}")                 except Exception as e:                     logger.warning(f"Failed to clean up input file {path}: {e}")      async def poll_loop(self):         logger.info(f"Agent {AGENT_ID} started polling {MASTER_API_URL} for tasks (types: {SUPPORTED_TASK_TYPES or 'all'})...")         while getattr(self, 'running', True):             try:                 # Poll for tasks with optional type filtering                 params = {}                 if SUPPORTED_TASK_TYPES:                     params["types"] = SUPPORTED_TASK_TYPES                  response = await self.master_client.get("/api/agent/task/pop", params=params)                 if response.status_code == 200:                     data = response.json()                     task = data.get("task")                     if task:                         await self.process_task(task)                         continue  # Immediately poll again after finishing                 elif response.status_code != 404: # 404 means no tasks, which is fine                     logger.warning(f"Unexpected response from master: {response.status_code}")              except httpx.RequestError as e:                 logger.error(f"Connection to master failed: {e}")             except Exception as e:                 logger.error(f"Polling error: {e}")              # Wait before next poll             await asyncio.sleep(2)      async def start(self):         # Ensure directories exist         os.makedirs(COMFY_INPUT_DIR, exist_ok=True)         os.makedirs(COMFY_OUTPUT_DIR, exist_ok=True)          # Start WS listener, polling loops, and heartbeat         self.running = True         self.tasks = [             asyncio.create_task(self.ws_listener_loop()),             asyncio.create_task(self.poll_loop()),             asyncio.create_task(self.heartbeat_loop())         ]         await asyncio.gather(*self.tasks)      async def shutdown(self):         logger.info("Initiating graceful shutdown...")         self.running = False          # If there is a task currently running, report it as failed/interrupted back to master         if self.current_task_id:             logger.info(f"Returning task {self.current_task_id} to master due to shutdown")             try:                 await self.report_status(                     self.current_task_id,                     "failed",                     error="Agent was shut down while processing the task. Task should be retried."                 )             except Exception as e:                 logger.error(f"Failed to report task failure during shutdown: {e}")          # Cancel all running background loops         for task in self.tasks:             task.cancel()          # Close HTTP clients         await self.master_client.aclose()         await self.comfy_client.close()         logger.info("Shutdown complete.")  if __name__ == "__main__":     agent = ComfyAgent()      # Setup graceful shutdown signals     import signal     import sys     loop = asyncio.get_event_loop()      if sys.platform != 'win32':         for sig in (signal.SIGINT, signal.SIGTERM):             loop.add_signal_handler(                 sig,                 lambda: asyncio.create_task(agent.shutdown())             )      try:         loop.run_until_complete(agent.start())     except asyncio.CancelledError:         pass     except KeyboardInterrupt:         # 捕获 Ctrl+C，触发优雅退出逻辑，防止 Master 端任务卡死         loop.run_until_complete(agent.shutdown())     finally:         loop.close() (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==comfy_agent2.workflow_patcher:[5:213] ==comfy_agent4.workflow_patcher:[5:213] logger = logging.getLogger(__name__)  class WorkflowPatcher:     def __init__(self, workflows_dir: str):         self.workflows_dir = workflows_dir         self.mappings = self.load_mappings()      def load_mappings(self) -> Dict[str, Any]:         mapping_path = os.path.join(self.workflows_dir, "mappings.json")         if os.path.exists(mapping_path):             with open(mapping_path, "r", encoding="utf-8") as f:                 return json.load(f)         return {}      def strip_meta(self, data: Any) -> Any:         if isinstance(data, dict):             data.pop("_meta", None)             for key, value in data.items():                 data[key] = self.strip_meta(value)         elif isinstance(data, list):             for i in range(len(data)):                 data[i] = self.strip_meta(data[i])         return data      def load_workflow(self, task_type: str) -> Optional[Dict[str, Any]]:         filename = f"{task_type}.json"         # Map task types to filenames (matching backend worker.py logic)         if task_type == "img2img":             filename = "Qwen-Rapid-AIO.json"         elif task_type == "face_swap":             filename = "face_swap.json"         elif task_type == "video_insert":             filename = "perfect_video_insert.json"         elif task_type == "video_edit":             filename = "perfect_video_edit.json"         elif task_type == "face_video":             filename = "face_video.json"         elif task_type == "t2i-pornmaster-turbo":             filename = "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json"         elif task_type == "i2i_pro":             filename = "i2i_pro.json"         elif task_type == "img2img_lora":             filename = "Qwen-Rapid-AIO.json"         elif task_type == "ltx_video":             filename = "LTX 2.3 I2V.json"          path = os.path.join(self.workflows_dir, filename)         if not os.path.exists(path):             logger.error(f"Workflow file {path} not found")             return None          with open(path, "r", encoding="utf-8") as f:             data = json.load(f)             data = self.strip_meta(data)              if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):                 logger.warning(f"Workflow {filename} seems to be in UI format (contains 'nodes' list). Please export in API format.")             return data      def patch_workflow(self, task_type: str, workflow: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:         # Deep copy to avoid modifying template         wf = json.loads(json.dumps(workflow))          # Inject a random seed to prevent ComfyUI from fully caching the workflow         # which would result in no output generation and no history record.         import random         if "seed" not in params or params["seed"] is None:             # Use a smaller max integer to prevent "value_bigger_than_max" errors in rgthree nodes             params["seed"] = random.randint(1, 1125899906842624)          # Reload mappings to ensure it's up to date         self.mappings = self.load_mappings()          # If we have mappings, use them         mapping = self.mappings.get(task_type, {})          for key, value in params.items():             if key in mapping:                 node_id = str(mapping[key])                 input_name = mapping.get(f"{key}_input", "image") # Default input name                 if node_id in wf:                     if "inputs" not in wf[node_id]:                         wf[node_id]["inputs"] = {}                     wf[node_id]["inputs"][input_name] = value             else:                 # For heuristic patch of images where the mapping wasn't specific enough                 if key in ["image", "image2", "image3", "images", "face_image", "body_image"]:                     continue # Ignore heuristic patch for images to prevent overriding wrong nodes                  # Heuristic search                 self.heuristic_patch(wf, key, value)          # Dynamic JSON pruning for img2img task to avoid empty nodes and blank inputs         if task_type in ["img2img", "img2img_lora"]:             # Handle LoRA dynamically (default to no LoRA)             lora_name = params.get("lora_name", "")             if lora_name and str(lora_name).strip() != "":                 if "32" in wf and "inputs" in wf["32"]:                     wf["32"]["inputs"]["lora_name"] = lora_name                     if params.get("lora_strength") is not None:                         wf["32"]["inputs"]["strength_model"] = float(params["lora_strength"])             else:                 # Strip LoRA node and connect KSampler (2) directly to Checkpoint (1)                 if "2" in wf and "inputs" in wf["2"]:                     wf["2"]["inputs"]["model"] = ["1", 0]                 if "32" in wf:                     wf.pop("32", None)              # 3 is the TextEncodeQwenImageEditPlus node             text_encode_node_id = str(mapping.get("prompt", "3"))              # Clean up image2 if not provided             if "image2" not in params or not params["image2"]:                 if text_encode_node_id in wf and "inputs" in wf[text_encode_node_id]:                     wf[text_encode_node_id]["inputs"].pop("image2", None)                 node_to_pop = str(mapping.get("image2", "20"))                 if node_to_pop in wf:                     wf.pop(node_to_pop, None)                 if "21" in wf:                     wf.pop("21", None) # ImageScaleToTotalPixels node 21              # Clean up image3 if not provided             if "image3" not in params or not params["image3"]:                 if text_encode_node_id in wf and "inputs" in wf[text_encode_node_id]:                     wf[text_encode_node_id]["inputs"].pop("image3", None)                 node_to_pop = str(mapping.get("image3", "30"))                 if node_to_pop in wf:                     wf.pop(node_to_pop, None)                 if "31" in wf:                     wf.pop("31", None) # ImageScaleToTotalPixels node 31          elif task_type == "ltx_video":             # Remove the preview override node as it causes AttributeError in API mode (serv.last_node_id is None)             if "210" in wf:                 wf.pop("210", None)             if "5" in wf:                 wf.pop("5", None)             if "59" in wf:                 wf.pop("59", None)             # Route Node 7 directly to Node 8             if "8" in wf and "inputs" in wf["8"]:                 wf["8"]["inputs"]["model"] = ["7", 0]              # Prevent caching of output nodes by ensuring a unique filename_prefix per task             # Using random integer as task_id if not present (since workflow_patcher only gets params)             unique_id = params.get("seed", random.randint(1, 1125899906842624))             for node_id, node in wf.items():                 if isinstance(node, dict) and node.get("class_type") == "VHS_VideoCombine":                     if "inputs" in node:                         node["inputs"]["filename_prefix"] = f"ltx_video_{unique_id}_{node_id}"          return wf      def heuristic_patch(self, workflow: Dict[str, Any], key: str, value: Any):         # This is a best-effort patcher for API format workflows         for node_id, node in workflow.items():             if not isinstance(node, dict) or "inputs" not in node:                 continue              inputs = node["inputs"]             class_type = node.get("class_type", "")              if key == "prompt" and ("CLIPTextEncode" in class_type or "Prompt" in class_type or "TextEncode" in class_type):                 # Ensure we only patch Positive Prompts, not Negative Prompts                 meta_title = node.get("_meta", {}).get("title", "").lower()                 if "negative" not in meta_title:                     if "text" in inputs:                         inputs["text"] = value                     if "prompt" in inputs:                         inputs["prompt"] = value              elif key == "seed" and ("Sampler" in class_type or "Seed" in class_type):                 # Only inject seed if the current value is a placeholder or -1, or if we passed None but we shouldn't because json.loads might convert it                 if "seed" in inputs:                     if inputs["seed"] == -1 or inputs["seed"] is None:                         inputs["seed"] = value                 if "noise_seed" in inputs:                     if inputs["noise_seed"] == -1 or inputs["noise_seed"] is None:                         inputs["noise_seed"] = value              elif key == "steps" and "Sampler" in class_type:                 if "steps" in inputs:                     inputs["steps"] = value              elif key == "cfg" and "Sampler" in class_type:                 if "cfg" in inputs:                     inputs["cfg"] = value              elif key == "width" and "EmptyLatentImage" in class_type:                 inputs["width"] = value              elif key == "height" and "EmptyLatentImage" in class_type:                 inputs["height"] = value              elif key == "width" and "FindPerfectResolution" in class_type:                 inputs["desired_width"] = value              elif key == "height" and "FindPerfectResolution" in class_type:                 inputs["desired_height"] = value              elif key == "lora_name" and "Power Lora Loader (rgthree)" in class_type:                 if str(node_id) == "272":                     inputs["lora_1"] = {"on": True, "lora": f"{value}_high_noise.safetensors", "strength": 1}                 elif str(node_id) == "273":                     inputs["lora_1"] = {"on": True, "lora": f"{value}_low_noise.safetensors", "strength": 1}              elif key == "length" and "PainterI2V" in class_type:                 inputs["length"] = value (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==comfy_agent1.workflow_patcher:[5:213] ==comfy_agent5.workflow_patcher:[5:213] logger = logging.getLogger(__name__)  class WorkflowPatcher:     def __init__(self, workflows_dir: str):         self.workflows_dir = workflows_dir         self.mappings = self.load_mappings()      def load_mappings(self) -> Dict[str, Any]:         mapping_path = os.path.join(self.workflows_dir, "mappings.json")         if os.path.exists(mapping_path):             with open(mapping_path, "r", encoding="utf-8") as f:                 return json.load(f)         return {}      def strip_meta(self, data: Any) -> Any:         if isinstance(data, dict):             data.pop("_meta", None)             for key, value in data.items():                 data[key] = self.strip_meta(value)         elif isinstance(data, list):             for i in range(len(data)):                 data[i] = self.strip_meta(data[i])         return data      def load_workflow(self, task_type: str) -> Optional[Dict[str, Any]]:         filename = f"{task_type}.json"         # Map task types to filenames (matching backend worker.py logic)         if task_type == "img2img":             filename = "Qwen-Rapid-AIO.json"         elif task_type == "face_swap":             filename = "face_swap.json"         elif task_type == "video_insert":             filename = "perfect_video_insert.json"         elif task_type == "video_edit":             filename = "perfect_video_edit.json"         elif task_type == "face_video":             filename = "face_video.json"         elif task_type == "t2i-pornmaster-turbo":             filename = "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json"         elif task_type == "i2i_pro":             filename = "i2i_pro.json"         elif task_type == "img2img_lora":             filename = "Qwen-Rapid-AIO.json"         elif task_type == "ltx_video":             filename = "LTX 2.3 I2V.json"          path = os.path.join(self.workflows_dir, filename)         if not os.path.exists(path):             logger.error(f"Workflow file {path} not found")             return None          with open(path, "r", encoding="utf-8") as f:             data = json.load(f)             data = self.strip_meta(data)              if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):                 logger.warning(f"Workflow {filename} seems to be in UI format (contains 'nodes' list). Please export in API format.")             return data      def patch_workflow(self, task_type: str, workflow: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:         # Deep copy to avoid modifying template         wf = json.loads(json.dumps(workflow))          # Inject a random seed to prevent ComfyUI from fully caching the workflow         # which would result in no output generation and no history record.         import random         if "seed" not in params or params["seed"] is None:             # Use a smaller max integer to prevent "value_bigger_than_max" errors in rgthree nodes             params["seed"] = random.randint(1, 1125899906842624)          # Reload mappings to ensure it's up to date         self.mappings = self.load_mappings()          # If we have mappings, use them         mapping = self.mappings.get(task_type, {})          for key, value in params.items():             if key in mapping:                 node_id = str(mapping[key])                 input_name = mapping.get(f"{key}_input", "image") # Default input name                 if node_id in wf:                     if "inputs" not in wf[node_id]:                         wf[node_id]["inputs"] = {}                     wf[node_id]["inputs"][input_name] = value             else:                 # For heuristic patch of images where the mapping wasn't specific enough                 if key in ["image", "image2", "image3", "images", "face_image", "body_image"]:                     continue # Ignore heuristic patch for images to prevent overriding wrong nodes                  # Heuristic search                 self.heuristic_patch(wf, key, value)          # Dynamic JSON pruning for img2img task to avoid empty nodes and blank inputs         if task_type in ["img2img", "img2img_lora"]:             # Handle LoRA dynamically (default to no LoRA)             lora_name = params.get("lora_name", "")             if lora_name and str(lora_name).strip() != "":                 if "32" in wf and "inputs" in wf["32"]:                     wf["32"]["inputs"]["lora_name"] = lora_name                     if params.get("lora_strength") is not None:                         wf["32"]["inputs"]["strength_model"] = float(params["lora_strength"])             else:                 # Strip LoRA node and connect KSampler (2) directly to Checkpoint (1)                 if "2" in wf and "inputs" in wf["2"]:                     wf["2"]["inputs"]["model"] = ["1", 0]                 if "32" in wf:                     wf.pop("32", None)              # 3 is the TextEncodeQwenImageEditPlus node             text_encode_node_id = str(mapping.get("prompt", "3"))              # Clean up image2 if not provided             if "image2" not in params or not params["image2"]:                 if text_encode_node_id in wf and "inputs" in wf[text_encode_node_id]:                     wf[text_encode_node_id]["inputs"].pop("image2", None)                 node_to_pop = str(mapping.get("image2", "20"))                 if node_to_pop in wf:                     wf.pop(node_to_pop, None)                 if "21" in wf:                     wf.pop("21", None) # ImageScaleToTotalPixels node 21              # Clean up image3 if not provided             if "image3" not in params or not params["image3"]:                 if text_encode_node_id in wf and "inputs" in wf[text_encode_node_id]:                     wf[text_encode_node_id]["inputs"].pop("image3", None)                 node_to_pop = str(mapping.get("image3", "30"))                 if node_to_pop in wf:                     wf.pop(node_to_pop, None)                 if "31" in wf:                     wf.pop("31", None) # ImageScaleToTotalPixels node 31          elif task_type == "ltx_video":             # Remove the preview override node as it causes AttributeError in API mode (serv.last_node_id is None)             if "210" in wf:                 wf.pop("210", None)             if "5" in wf:                 wf.pop("5", None)             if "59" in wf:                 wf.pop("59", None)             # Route Node 7 directly to Node 8             if "8" in wf and "inputs" in wf["8"]:                 wf["8"]["inputs"]["model"] = ["7", 0]              # Prevent caching of output nodes by ensuring a unique filename_prefix per task             # Using random integer as task_id if not present (since workflow_patcher only gets params)             unique_id = params.get("seed", random.randint(1, 1125899906842624))             for node_id, node in wf.items():                 if isinstance(node, dict) and node.get("class_type") == "VHS_VideoCombine":                     if "inputs" in node:                         node["inputs"]["filename_prefix"] = f"ltx_video_{unique_id}_{node_id}"          return wf      def heuristic_patch(self, workflow: Dict[str, Any], key: str, value: Any):         # This is a best-effort patcher for API format workflows         for node_id, node in workflow.items():             if not isinstance(node, dict) or "inputs" not in node:                 continue              inputs = node["inputs"]             class_type = node.get("class_type", "")              if key == "prompt" and ("CLIPTextEncode" in class_type or "Prompt" in class_type or "TextEncode" in class_type):                 # Ensure we only patch Positive Prompts, not Negative Prompts                 meta_title = node.get("_meta", {}).get("title", "").lower()                 if "negative" not in meta_title:                     if "text" in inputs:                         inputs["text"] = value                     if "prompt" in inputs:                         inputs["prompt"] = value              elif key == "seed" and ("Sampler" in class_type or "Seed" in class_type):                 # Only inject seed if the current value is a placeholder or -1, or if we passed None but we shouldn't because json.loads might convert it                 if "seed" in inputs:                     if inputs["seed"] == -1 or inputs["seed"] is None:                         inputs["seed"] = value                 if "noise_seed" in inputs:                     if inputs["noise_seed"] == -1 or inputs["noise_seed"] is None:                         inputs["noise_seed"] = value              elif key == "steps" and "Sampler" in class_type:                 if "steps" in inputs:                     inputs["steps"] = value              elif key == "cfg" and "Sampler" in class_type:                 if "cfg" in inputs:                     inputs["cfg"] = value              elif key == "width" and "EmptyLatentImage" in class_type:                 inputs["width"] = value              elif key == "height" and "EmptyLatentImage" in class_type:                 inputs["height"] = value              elif key == "width" and "FindPerfectResolution" in class_type:                 inputs["desired_width"] = value              elif key == "height" and "FindPerfectResolution" in class_type:                 inputs["desired_height"] = value              elif key == "lora_name" and "Power Lora Loader (rgthree)" in class_type:                 if str(node_id) == "272":                     inputs["lora_1"] = {"on": True, "lora": f"{value}_high_noise.safetensors", "strength": 1}                 elif str(node_id) == "273":                     inputs["lora_1"] = {"on": True, "lora": f"{value}_low_noise.safetensors", "strength": 1}              elif key == "length" and "PainterI2V" in class_type:                 inputs["length"] = value (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==comfy_agent2.comfy_client:[4:82] ==comfy_agent4.comfy_client:[4:82] logger = logging.getLogger(__name__)  class ComfyClient:     def __init__(self, base_url: str):         self.base_url = base_url         self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)      async def check_connection(self) -> bool:         try:             response = await self.client.get("/system_stats")             return response.status_code == 200         except Exception as e:             logger.error(f"ComfyUI connection failed: {e}")             return False      async def upload_image(self, file_content: bytes, filename: str, subfolder: str = "") -> Dict[str, Any]:         """         Upload an image to ComfyUI input directory.         """         # The multipart format expected by ComfyUI         files = {"image": (filename, file_content, "image/png")}         data = {"overwrite": "true"}         if subfolder:             data["subfolder"] = subfolder          # Use multipart explicitly         response = await self.client.post("/upload/image", files=files, data=data)         if response.status_code != 200:             logger.error(f"ComfyUI upload error: {response.text}")         response.raise_for_status()         return response.json()      async def queue_prompt(self, prompt: Dict[str, Any], client_id: str) -> str:         """         Submit a workflow prompt to ComfyUI.         """         payload = {"prompt": prompt, "client_id": client_id}         response = await self.client.post("/prompt", json=payload)         if response.status_code != 200:             logger.error(f"ComfyUI prompt error: {response.text}")         response.raise_for_status()         data = response.json()         return data.get("prompt_id")      async def get_history(self, prompt_id: str) -> Dict[str, Any]:         """         Get execution history for a specific prompt_id.         """         response = await self.client.get(f"/history/{prompt_id}")         if response.status_code == 200:             return response.json()         return {}      async def get_view(self, filename: str, subfolder: str = "", type: str = "output") -> bytes:         """         Get the raw image/video data from ComfyUI output directory.         Includes a simple retry mechanism for file system I/O delays.         """         import asyncio         params = {"filename": filename, "subfolder": subfolder, "type": type}          max_retries = 3         for attempt in range(max_retries):             try:                 response = await self.client.get("/view", params=params)                 response.raise_for_status()                 return response.content             except Exception as e:                 if attempt < max_retries - 1:                     logger.warning(f"Failed to fetch {filename} (attempt {attempt + 1}/{max_retries}), retrying in 2 seconds... Error: {e}")                     await asyncio.sleep(2)                 else:                     logger.error(f"Failed to fetch {filename} after {max_retries} attempts.")                     raise e         raise Exception(f"Failed to fetch {filename}")      async def close(self):         await self.client.aclose() (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==comfy_agent3.comfy_client:[4:82] ==comfy_agent5.comfy_client:[4:82] logger = logging.getLogger(__name__)  class ComfyClient:     def __init__(self, base_url: str):         self.base_url = base_url         self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)      async def check_connection(self) -> bool:         try:             response = await self.client.get("/system_stats")             return response.status_code == 200         except Exception as e:             logger.error(f"ComfyUI connection failed: {e}")             return False      async def upload_image(self, file_content: bytes, filename: str, subfolder: str = "") -> Dict[str, Any]:         """         Upload an image to ComfyUI input directory.         """         # The multipart format expected by ComfyUI         files = {"image": (filename, file_content, "image/png")}         data = {"overwrite": "true"}         if subfolder:             data["subfolder"] = subfolder          # Use multipart explicitly         response = await self.client.post("/upload/image", files=files, data=data)         if response.status_code != 200:             logger.error(f"ComfyUI upload error: {response.text}")         response.raise_for_status()         return response.json()      async def queue_prompt(self, prompt: Dict[str, Any], client_id: str) -> str:         """         Submit a workflow prompt to ComfyUI.         """         payload = {"prompt": prompt, "client_id": client_id}         response = await self.client.post("/prompt", json=payload)         if response.status_code != 200:             logger.error(f"ComfyUI prompt error: {response.text}")         response.raise_for_status()         data = response.json()         return data.get("prompt_id")      async def get_history(self, prompt_id: str) -> Dict[str, Any]:         """         Get execution history for a specific prompt_id.         """         response = await self.client.get(f"/history/{prompt_id}")         if response.status_code == 200:             return response.json()         return {}      async def get_view(self, filename: str, subfolder: str = "", type: str = "output") -> bytes:         """         Get the raw image/video data from ComfyUI output directory.         Includes a simple retry mechanism for file system I/O delays.         """         import asyncio         params = {"filename": filename, "subfolder": subfolder, "type": type}          max_retries = 3         for attempt in range(max_retries):             try:                 response = await self.client.get("/view", params=params)                 response.raise_for_status()                 return response.content             except Exception as e:                 if attempt < max_retries - 1:                     logger.warning(f"Failed to fetch {filename} (attempt {attempt + 1}/{max_retries}), retrying in 2 seconds... Error: {e}")                     await asyncio.sleep(2)                 else:                     logger.error(f"Failed to fetch {filename} after {max_retries} attempts.")                     raise e         raise Exception(f"Failed to fetch {filename}")      async def close(self):         await self.client.aclose() (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==comfy_agent1.comfy_client:[33:90] ==comfy_agent4.comfy_client:[25:82]         data = {"overwrite": "true"}         if subfolder:             data["subfolder"] = subfolder          # Use multipart explicitly         response = await self.client.post("/upload/image", files=files, data=data)         if response.status_code != 200:             logger.error(f"ComfyUI upload error: {response.text}")         response.raise_for_status()         return response.json()      async def queue_prompt(self, prompt: Dict[str, Any], client_id: str) -> str:         """         Submit a workflow prompt to ComfyUI.         """         payload = {"prompt": prompt, "client_id": client_id}         response = await self.client.post("/prompt", json=payload)         if response.status_code != 200:             logger.error(f"ComfyUI prompt error: {response.text}")         response.raise_for_status()         data = response.json()         return data.get("prompt_id")      async def get_history(self, prompt_id: str) -> Dict[str, Any]:         """         Get execution history for a specific prompt_id.         """         response = await self.client.get(f"/history/{prompt_id}")         if response.status_code == 200:             return response.json()         return {}      async def get_view(self, filename: str, subfolder: str = "", type: str = "output") -> bytes:         """         Get the raw image/video data from ComfyUI output directory.         Includes a simple retry mechanism for file system I/O delays.         """         import asyncio         params = {"filename": filename, "subfolder": subfolder, "type": type}          max_retries = 3         for attempt in range(max_retries):             try:                 response = await self.client.get("/view", params=params)                 response.raise_for_status()                 return response.content             except Exception as e:                 if attempt < max_retries - 1:                     logger.warning(f"Failed to fetch {filename} (attempt {attempt + 1}/{max_retries}), retrying in 2 seconds... Error: {e}")                     await asyncio.sleep(2)                 else:                     logger.error(f"Failed to fetch {filename} after {max_retries} attempts.")                     raise e         raise Exception(f"Failed to fetch {filename}")      async def close(self):         await self.client.aclose() (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==src.core.user_core:[16:30] ==src.quota:[43:55]         result = await session.execute(stmt)         user = result.scalar_one_or_none()          if user:             updated = False             if username and user.username != username:                 user.username = username                 updated = True             if full_name and user.full_name != full_name:                 user.full_name = full_name                 updated = True              if updated:                 await session.commit() (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==src.web_api.dependencies:[61:74] ==src.web_api.routers.auth:[168:181]         stats = await permission_service.get_user_detailed_stats(user.telegram_id)         current_identity = stats.get("identity", user.current_identity)         current_group = stats.get("group", user.user_group)          allowed_identities = ["内门弟子", "核心弟子", "真传弟子"]         allowed_groups = ["金丹期", "元婴期", "化神期", "炼虚期", "合体期", "大乘期", "渡劫期"]          is_allowed_identity = current_identity in allowed_identities         is_allowed_group = current_group in allowed_groups          if not (is_allowed_identity or is_allowed_group):             raise HTTPException(                 status_code=status.HTTP_403_FORBIDDEN, (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==comfy_agent1.comfy_client:[4:23] ==comfy_agent4.comfy_client:[4:24] logger = logging.getLogger(__name__)  class ComfyClient:     def __init__(self, base_url: str):         self.base_url = base_url         self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)      async def check_connection(self) -> bool:         try:             response = await self.client.get("/system_stats")             return response.status_code == 200         except Exception as e:             logger.error(f"ComfyUI connection failed: {e}")             return False      async def upload_image(self, file_content: bytes, filename: str, subfolder: str = "") -> Dict[str, Any]:         """         Upload an image to ComfyUI input directory.         """         # The multipart format expected by ComfyUI (duplicate-code) |
| 1 | 代码重复 | **Medium** | Similar lines in 2 files ==app.main:[30:41] ==app.routers.agent:[17:27]     redis = Redis.from_url(settings.redis_url)     try:         yield redis     finally:         await redis.close()  # Dependency for QueueManager async def get_queue_manager(redis: Redis = Depends(get_redis)):     return QueueManager(redis)  async def check_zombie_tasks_loop(): (duplicate-code) |
| 6 | 一般代码规范 | **Low** | Import outside toplevel (datetime.datetime) (import-outside-toplevel) |


### 📄 `src/api_client.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 4 | 导入优化 | **Low** | standard import "logging" should be placed before third party import "httpx" (wrong-import-order) |
| 5 | 导入优化 | **Low** | standard import "uuid" should be placed before third party import "httpx" (wrong-import-order) |
| 6 | 导入优化 | **Low** | standard import "typing.Optional" should be placed before third party import "httpx" (wrong-import-order) |
| 9 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 10 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 16 | 一般代码规范 | **Low** | Imports from package src are not grouped (ungrouped-imports) |
| 23 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 23 | 导入优化 | **Low** | Import "from asgi_correlation_id import correlation_id" should be placed at the top of the module (wrong-import-position) |
| 23 | 导入优化 | **Low** | third party import "asgi_correlation_id.correlation_id" should be placed before first party imports "src.utils.async_retry", "config.IMG2IMG_ENDPOINT", "src.circuit_breaker.CircuitBreaker"  (wrong-import-order) |
| 29 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 53 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 61 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 64 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 68 | 一般代码规范 | **Low** | Line too long (159/120) (line-too-long) |
| 68 | 代码坏味道 | **Low** | Too many arguments (7/5) (too-many-arguments) |
| 68 | 一般代码规范 | **Low** | Too many positional arguments (7/5) (too-many-positional-arguments) |
| 87 | 一般代码规范 | **Low** | Line too long (157/120) (line-too-long) |
| 87 | 代码坏味道 | **Low** | Too many arguments (7/5) (too-many-arguments) |
| 87 | 一般代码规范 | **Low** | Too many positional arguments (7/5) (too-many-positional-arguments) |
| 105 | 一般代码规范 | **Low** | Line too long (173/120) (line-too-long) |
| 105 | 代码坏味道 | **Low** | Too many arguments (8/5) (too-many-arguments) |
| 105 | 一般代码规范 | **Low** | Too many positional arguments (8/5) (too-many-positional-arguments) |
| 125 | 一般代码规范 | **Low** | Line too long (126/120) (line-too-long) |
| 142 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 147 | 一般代码规范 | **Low** | Line too long (144/120) (line-too-long) |
| 147 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 152 | 一般代码规范 | **Low** | Line too long (175/120) (line-too-long) |
| 152 | 代码坏味道 | **Low** | Too many arguments (7/5) (too-many-arguments) |
| 152 | 一般代码规范 | **Low** | Too many positional arguments (7/5) (too-many-positional-arguments) |
| 172 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 176 | 一般代码规范 | **Low** | Line too long (139/120) (line-too-long) |
| 176 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 195 | 一般代码规范 | **Low** | Line too long (121/120) (line-too-long) |
| 195 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 200 | 一般代码规范 | **Low** | Line too long (147/120) (line-too-long) |
| 200 | 代码坏味道 | **Low** | Too many arguments (6/5) (too-many-arguments) |
| 200 | 一般代码规范 | **Low** | Too many positional arguments (6/5) (too-many-positional-arguments) |
| 216 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 232 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 237 | 一般代码规范 | **Low** | Line too long (150/120) (line-too-long) |
| 237 | 代码坏味道 | **Low** | Too many arguments (7/5) (too-many-arguments) |
| 237 | 一般代码规范 | **Low** | Too many positional arguments (7/5) (too-many-positional-arguments) |
| 251 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 255 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 260 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 266 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 273 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise RuntimeError('后端未找到生成的图片（可能是因为节点保存到了 temp 文件夹而导致读取失败），请联系管理员修复后端工作流。') from e' (raise-missing-from) |
| 274 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise RuntimeError(f'获取图片失败: HTTP {e.response.status_code}') from e' (raise-missing-from) |
| 277 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 284 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise RuntimeError('后端未找到生成的视频文件。') from e' (raise-missing-from) |
| 285 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise RuntimeError(f'获取视频失败: HTTP {e.response.status_code}') from e' (raise-missing-from) |
| 287 | 代码坏味道 | **Low** | Too many local variables (18/15) (too-many-locals) |
| 287 | 代码坏味道 | **Low** | Too many branches (23/12) (too-many-branches) |
| 287 | 代码坏味道 | **Low** | Too many statements (79/50) (too-many-statements) |
| 287 | 一般代码规范 | **Medium** | Unused argument 'is_video' (unused-argument) |
| 287 | 代码坏味道 | **High** | 高复杂度代码块 (method `listen_for_progress`): Cyclomatic Complexity = 25 |
| 292 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 297 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 299 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 305 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 306 | 作用域分析 | **Medium** | Redefining name 'httpx' from outer scope (line 3) (redefined-outer-name) |
| 306 | 导入优化 | **Medium** | Reimport 'httpx' (imported line 3) (reimported) |
| 306 | 一般代码规范 | **Low** | Import outside toplevel (httpx) (import-outside-toplevel) |
| 307 | 一般代码规范 | **High** | Instance of 'Exception' has no 'response' member (no-member) |
| 308 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise RuntimeError(f'Task {task_id} not found on server (404).') from e' (raise-missing-from) |
| 309 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 312 | 一般代码规范 | **Low** | Import outside toplevel (redis.asyncio) (import-outside-toplevel) |
| 313 | 一般代码规范 | **Low** | Import outside toplevel (json) (import-outside-toplevel) |
| 314 | 一般代码规范 | **Low** | Import outside toplevel (config.REDIS_URL) (import-outside-toplevel) |
| 315 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 323 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 324 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 327 | 一般代码规范 | **Low** | Line too long (132/120) (line-too-long) |
| 332 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 333 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 335 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 346 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 357 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 362 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'except Exception as exc' and 'raise RuntimeError(info.get('error', 'generation failed or cancelled')) from exc' (raise-missing-from) |
| 363 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 364 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 371 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 376 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise RuntimeError(info.get('error', 'generation failed or cancelled')) from e' (raise-missing-from) |
| 377 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 379 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 380 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |


### 📄 `src/bot_test.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 11 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 12 | 导入优化 | **Low** | standard import "uuid" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id" (wrong-import-order) |
| 13 | 一般代码规范 | **Low** | Imports from package telegram are not grouped (ungrouped-imports) |
| 14 | 导入优化 | **Low** | standard import "logging" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest" (wrong-import-order) |
| 15 | 导入优化 | **Low** | standard import "os" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest" (wrong-import-order) |
| 22 | 导入优化 | **Low** | standard import "socket" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest" and first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  (wrong-import-order) |
| 22 | 导入优化 | **Medium** | Unused import socket (unused-import) |
| 22 | 死代码检测 | **Low** | unused import 'socket' (90% confidence) |
| 23 | 导入优化 | **Low** | standard import "urllib.parse.urlparse" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest" and first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  (wrong-import-order) |
| 23 | 导入优化 | **Medium** | Unused urlparse imported from urllib.parse (unused-import) |
| 26 | 导入优化 | **Low** | third party import "telegram.File" should be placed before first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  (wrong-import-order) |
| 26 | 一般代码规范 | **Low** | Imports from package telegram are not grouped (ungrouped-imports) |
| 27 | 导入优化 | **Low** | third party import "httpx" should be placed before first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  (wrong-import-order) |
| 28 | 导入优化 | **Medium** | Reimport 'os' (imported line 15) (reimported) |
| 28 | 导入优化 | **Low** | standard import "os" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest", "telegram.File", "httpx" and first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  (wrong-import-order) |
| 28 | 一般代码规范 | **Low** | Imports from package os are not grouped (ungrouped-imports) |
| 29 | 导入优化 | **Medium** | Reimport 'logging' (imported line 14) (reimported) |
| 29 | 导入优化 | **Low** | standard import "logging" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest", "telegram.File", "httpx" and first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  (wrong-import-order) |
| 29 | 一般代码规范 | **Low** | Imports from package logging are not grouped (ungrouped-imports) |
| 34 | 一般代码规范 | **Low** | Line too long (139/120) (line-too-long) |
| 34 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 34 | 代码坏味道 | **Low** | Too many arguments (6/5) (too-many-arguments) |
| 34 | 一般代码规范 | **Low** | Too many positional arguments (6/5) (too-many-positional-arguments) |
| 36 | 一般代码规范 | **Low** | Unnecessary "else" after "return", remove the "else" and de-indent the code inside it (no-else-return) |
| 37 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 40 | 作用域分析 | **Medium** | Redefining name 'urlparse' from outer scope (line 23) (redefined-outer-name) |
| 40 | 导入优化 | **Medium** | Reimport 'urlparse' (imported line 23) (reimported) |
| 40 | 一般代码规范 | **Low** | Import outside toplevel (urllib.parse.urlparse) (import-outside-toplevel) |
| 46 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 54 | 一般代码规范 | **Low** | Line too long (126/120) (line-too-long) |
| 54 | 一般代码规范 | **High** | Too many positional arguments for unbound method call (too-many-function-args) |
| 59 | 导入优化 | **Low** | Import "import asyncio" should be placed at the top of the module (wrong-import-position) |
| 59 | 导入优化 | **Low** | standard import "asyncio" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest", "telegram.File", "httpx" and first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  (wrong-import-order) |
| 60 | 导入优化 | **Low** | Import "from src.services.payment_validator import TonPaymentValidator" should be placed at the top of the module (wrong-import-position) |
| 60 | 一般代码规范 | **Low** | Imports from package src are not grouped (ungrouped-imports) |
| 61 | 导入优化 | **Low** | Import "from src.services.task_registry import TaskRegistry" should be placed at the top of the module (wrong-import-position) |
| 62 | 导入优化 | **Low** | Import "from src.services.recovery_service import recover_active_tasks" should be placed at the top of the module (wrong-import-position) |
| 66 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 67 | 一般代码规范 | **Low** | Import outside toplevel (src.services.zombie_cleaner_service.clean_zombies) (import-outside-toplevel) |
| 68 | 作用域分析 | **Medium** | Redefining name 'logger' from outer scope (line 30) (redefined-outer-name) |
| 72 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 73 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 76 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 76 | 一般代码规范 | **Medium** | Unused argument 'context' (unused-argument) |
| 79 | 作用域分析 | **Medium** | Redefining name 'logger' from outer scope (line 30) (redefined-outer-name) |
| 81 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 85 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 88 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 93 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 99 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 104 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 110 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 111 | 作用域分析 | **Medium** | Redefining name 'logger' from outer scope (line 30) (redefined-outer-name) |
| 114 | 一般代码规范 | **Low** | Import outside toplevel (src.services.redis_client.redis_client) (import-outside-toplevel) |
| 117 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 117 | 代码坏味道 | **Low** | Too many local variables (20/15) (too-many-locals) |
| 117 | 代码坏味道 | **Low** | Too many statements (52/50) (too-many-statements) |
| 119 | 作用域分析 | **Medium** | Redefining name 'logger' from outer scope (line 30) (redefined-outer-name) |
| 120 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 123 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 125 | 一般代码规范 | **Low** | Import outside toplevel (dotenv.dotenv_values) (import-outside-toplevel) |
| 127 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 129 | 一般代码规范 | **Low** | Line too long (143/120) (line-too-long) |
| 130 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 132 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 134 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 137 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 142 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 150 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 187 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 188 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.payment_handler.precheckout_callback, src.handlers.payment_handler.successful_payment_callback) (import-outside-toplevel) |
| 189 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.fsm.quick_image_fsm.get_quick_image_fsm_handler) (import-outside-toplevel) |
| 190 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.fsm.quick_video_fsm.get_quick_video_fsm_handler) (import-outside-toplevel) |
| 191 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.fsm.edit_image_fsm.get_edit_image_fsm_handler) (import-outside-toplevel) |
| 192 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.fsm.faceswap_fsm.get_faceswap_fsm_handler) (import-outside-toplevel) |
| 193 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.fsm.face_video_fsm.get_face_video_fsm_handler) (import-outside-toplevel) |
| 194 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.fsm.video_lora_fsm.get_video_lora_fsm_handler) (import-outside-toplevel) |
| 195 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.fsm.custom_video_fsm.get_custom_video_fsm_handler) (import-outside-toplevel) |
| 196 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.fsm.ltx_video_fsm.get_ltx_video_fsm_handler) (import-outside-toplevel) |
| 197 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.fsm.gallery_apply_fsm.get_gallery_apply_fsm_handler) (import-outside-toplevel) |
| 199 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 224 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |


### 📄 `src/circuit_breaker.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 7 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 12 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 15 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 23 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 31 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 36 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 41 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 56 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |


### 📄 `src/constants.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 170 | 一般代码规范 | **Low** | Line too long (166/120) (line-too-long) |
| 170 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 170 | 代码坏味道 | **Low** | Too many local variables (23/15) (too-many-locals) |
| 170 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `get_video_settings_keyboard`): Cyclomatic Complexity = 13 |
| 171 | 一般代码规范 | **Low** | Import outside toplevel (telegram.InlineKeyboardButton, telegram.InlineKeyboardMarkup) (import-outside-toplevel) |
| 175 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 179 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 181 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 188 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 199 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 206 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 212 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 215 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 218 | 一般代码规范 | **Low** | Line too long (150/120) (line-too-long) |
| 218 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 218 | 一般代码规范 | **Medium** | Unused argument 'user_group' (unused-argument) |
| 218 | 一般代码规范 | **Medium** | Unused argument 'user_identity' (unused-argument) |
| 218 | 一般代码规范 | **Medium** | Unused argument 'current_resolution' (unused-argument) |
| 219 | 一般代码规范 | **Low** | Import outside toplevel (telegram.InlineKeyboardButton, telegram.InlineKeyboardMarkup) (import-outside-toplevel) |
| 223 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 225 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 234 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 239 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `src/context.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |


### 📄 `src/core/billing_core.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 4 | 导入优化 | **Medium** | Unused AsyncSessionLocal imported from src.database.core (unused-import) |
| 5 | 导入优化 | **Medium** | Unused User imported from src.database.models (unused-import) |
| 18 | 一般代码规范 | **Low** | Import outside toplevel (src.api_client.get_system_status) (import-outside-toplevel) |
| 19 | 一般代码规范 | **Low** | Import outside toplevel (src.services.permission_service.permission_service) (import-outside-toplevel) |
| 29 | 一般代码规范 | **Low** | Line too long (152/120) (line-too-long) |
| 42 | 一般代码规范 | **Low** | Line too long (127/120) (line-too-long) |
| 58 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 59 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 71 | 一般代码规范 | **Low** | Import outside toplevel (src.services.permission_service.permission_service) (import-outside-toplevel) |


### 📄 `src/core/task_core.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 18 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 20 | 一般代码规范 | **Low** | Import outside toplevel (asyncio) (import-outside-toplevel) |
| 24 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 28 | 代码坏味道 | **Low** | Too many arguments (12/5) (too-many-arguments) |
| 28 | 一般代码规范 | **Low** | Too many positional arguments (12/5) (too-many-positional-arguments) |
| 28 | 代码坏味道 | **Low** | Too many local variables (18/15) (too-many-locals) |
| 40 | 一般代码规范 | **Medium** | Unused argument 'allow_contribute' (unused-argument) |
| 77 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 80 | 一般代码规范 | **High** | Class 'TaskRegistry' has no 'mark_task_status' member (no-member) |
| 85 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 86 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 95 | 代码坏味道 | **Low** | Too many arguments (17/5) (too-many-arguments) |
| 95 | 一般代码规范 | **Low** | Too many positional arguments (17/5) (too-many-positional-arguments) |
| 95 | 代码坏味道 | **Low** | Too many local variables (30/15) (too-many-locals) |
| 95 | 代码坏味道 | **Low** | Too many branches (24/12) (too-many-branches) |
| 95 | 代码坏味道 | **Low** | Too many statements (53/50) (too-many-statements) |
| 95 | 代码坏味道 | **High** | 高复杂度代码块 (function `core_submit_generation_task`): Cyclomatic Complexity = 26 |
| 105 | 一般代码规范 | **Medium** | Unused argument 'steps' (unused-argument) |
| 105 | 死代码检测 | **Low** | unused variable 'steps' (100% confidence) |
| 112 | 一般代码规范 | **Medium** | Unused argument 'allow_contribute' (unused-argument) |
| 149 | 一般代码规范 | **Low** | "len(saved_input_images) == 0" can be simplified to "not len(saved_input_images)", if it is strictly an int, as 0 is falsey (use-implicit-booleaness-not-comparison-to-zero) |
| 151 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 159 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 162 | 一般代码规范 | **Low** | Line too long (144/120) (line-too-long) |
| 168 | 一般代码规范 | **Medium** | No exception type(s) specified (bare-except) |
| 172 | 一般代码规范 | **Low** | Line too long (131/120) (line-too-long) |
| 185 | 一般代码规范 | **Low** | Consider merging these comparisons with 'in' by using 'task_type in ('i2i_pro', 'MODE_I2I_PRO')'. Use a set instead if elements are hashable. (consider-using-in) |
| 186 | 一般代码规范 | **Low** | Import outside toplevel (random) (import-outside-toplevel) |
| 194 | 一般代码规范 | **Low** | Consider merging these comparisons with 'in' by using 'task_type in ('img2img_lora', 'MODE_IMG2IMG_LORA')'. Use a set instead if elements are hashable. (consider-using-in) |
| 213 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 216 | 一般代码规范 | **High** | Class 'TaskRegistry' has no 'mark_task_status' member (no-member) |
| 221 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 222 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |


### 📄 `src/core/user_core.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 3 | 导入优化 | **Low** | standard import "datetime.datetime" should be placed before third party imports "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" (wrong-import-order) |
| 8 | 导入优化 | **Low** | standard import "typing.Tuple" should be placed before third party imports "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" and first party imports "src.database.core.AsyncSessionLocal", "src.database.models.User"  (wrong-import-order) |
| 19 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 28 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 32 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 37 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 70 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `src/handlers/callback_handler.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 12 | 死代码检测 | **Low** | unused import 'billing_callbacks' (90% confidence) |
| 12 | 死代码检测 | **Low** | unused import 'gallery_callbacks' (90% confidence) |
| 12 | 死代码检测 | **Low** | unused import 'misc_callbacks' (90% confidence) |


### 📄 `src/handlers/callbacks/billing_callbacks.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 134 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `buy_rmb_plan_callback`): Cyclomatic Complexity = 12 |


### 📄 `src/handlers/callbacks/gallery_callbacks.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 28 | 代码坏味道 | **High** | 高复杂度代码块 (function `public_share_callback`): Cyclomatic Complexity = 38 |
| 251 | 代码坏味道 | **High** | 高复杂度代码块 (function `submit_gallery_callback`): Cyclomatic Complexity = 22 |
| 376 | 代码坏味道 | **High** | 高复杂度代码块 (function `gallery_sort_page_callback`): Cyclomatic Complexity = 53 |
| 554 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `gallery_like_dislike_callback`): Cyclomatic Complexity = 15 |


### 📄 `src/handlers/command_handler.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 43 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `start`): Cyclomatic Complexity = 12 |


### 📄 `src/handlers/fsm/custom_video_fsm.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 111 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `process_settings`): Cyclomatic Complexity = 12 |


### 📄 `src/handlers/fsm/gallery_apply_fsm.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 45 | 代码坏味道 | **High** | 高复杂度代码块 (function `start_gallery_apply`): Cyclomatic Complexity = 31 |
| 225 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `receive_reference_image`): Cyclomatic Complexity = 15 |


### 📄 `src/handlers/fsm/quick_image_fsm.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 90 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `receive_image`): Cyclomatic Complexity = 16 |


### 📄 `src/handlers/fsm/quick_video_fsm.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 137 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `process_settings`): Cyclomatic Complexity = 13 |


### 📄 `src/handlers/fsm/video_lora_fsm.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 151 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `process_settings`): Cyclomatic Complexity = 12 |


### 📄 `src/handlers/message_handler.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 87 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `_handle_template_contribution`): Cyclomatic Complexity = 13 |
| 142 | 代码坏味道 | **High** | 高复杂度代码块 (function `handle_prompt`): Cyclomatic Complexity = 46 |


### 📄 `src/handlers/payment_handler.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 23 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `successful_payment_callback`): Cyclomatic Complexity = 19 |


### 📄 `src/logger.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 6 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 20 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 23 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 24 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 24 | 一般代码规范 | **Low** | Too few public methods (1/2) (too-few-public-methods) |
| 35 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 39 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 44 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 51 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 65 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 69 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 72 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 73 | 一般代码规范 | **Low** | Unnecessary "else" after "return", remove the "else" and de-indent the code inside it (no-else-return) |
| 74 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 77 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 88 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 91 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 95 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 96 | 一般代码规范 | **Low** | Unnecessary "else" after "return", remove the "else" and de-indent the code inside it (no-else-return) |
| 97 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 100 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 103 | 一般代码规范 | **Medium** | Redefining built-in 'type' (redefined-builtin) |
| 105 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 107 | 一般代码规范 | **Low** | Line too long (180/120) (line-too-long) |
| 107 | 代码坏味道 | **Low** | Too many arguments (8/5) (too-many-arguments) |
| 107 | 一般代码规范 | **Low** | Too many positional arguments (8/5) (too-many-positional-arguments) |
| 107 | 一般代码规范 | **Medium** | Redefining built-in 'type' (redefined-builtin) |
| 113 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 114 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 115 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 121 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 128 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 141 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 145 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `src/payment_api_server.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 5 | 导入优化 | **Low** | standard import "os" should be placed before third party imports "fastapi.FastAPI", "fastapi.responses.HTMLResponse", "uvicorn" (wrong-import-order) |
| 20 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 26 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 29 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 31 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 35 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 39 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 43 | 一般代码规范 | **Low** | Unnecessary "else" after "return", remove the "else" and de-indent the code inside it (no-else-return) |
| 44 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 47 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 49 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 50 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 54 | 一般代码规范 | **Medium** | Unused argument 'request' (unused-argument) |
| 83 | 一般代码规范 | **Medium** | os.getenv default type is builtins.int. Expected str or None. (invalid-envvar-default) |


### 📄 `src/quota.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 8 | 导入优化 | **Low** | third party import "sqlalchemy.exc.IntegrityError" should be placed before local imports "database.core.AsyncSessionLocal", "database.models.User", "services.log_service.LogService", "constants.GENERATION_TASK_TYPES" (wrong-import-order) |
| 10 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 17 | 一般代码规范 | **Low** | Import outside toplevel (datetime.timezone, datetime.timedelta) (import-outside-toplevel) |
| 23 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 24 | 一般代码规范 | **High** | func.count is not callable (not-callable) |
| 34 | 一般代码规范 | **Low** | Import outside toplevel (sqlalchemy.or_) (import-outside-toplevel) |
| 77 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 80 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 87 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 92 | 一般代码规范 | **Low** | "cost != 0" can be simplified to "cost", if it is strictly an int, as 0 is falsey (use-implicit-booleaness-not-comparison-to-zero) |
| 112 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 122 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 123 | 一般代码规范 | **Low** | Import outside toplevel (datetime.timezone, datetime.timedelta) (import-outside-toplevel) |
| 129 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 141 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 159 | 作用域分析 | **Medium** | Redefining name 'func' from outer scope (line 2) (redefined-outer-name) |
| 159 | 导入优化 | **Medium** | Reimport 'func' (imported line 2) (reimported) |
| 159 | 一般代码规范 | **Low** | Import outside toplevel (sqlalchemy.func) (import-outside-toplevel) |
| 160 | 一般代码规范 | **High** | func.count is not callable (not-callable) |
| 164 | 一般代码规范 | **Low** | Line too long (133/120) (line-too-long) |
| 164 | 代码坏味道 | **Low** | Too many return statements (7/6) (too-many-return-statements) |
| 164 | 一般代码规范 | **Medium** | Unused argument 'new_full_name' (unused-argument) |
| 164 | 死代码检测 | **Low** | unused variable 'new_full_name' (100% confidence) |
| 178 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 190 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 192 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 199 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 202 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 206 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 224 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 256 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 259 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 262 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 267 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 283 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 299 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 307 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 309 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 326 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `src/services/log_service.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 13 | 代码坏味道 | **Medium** | 高复杂度代码块 (class `LogService`): Cyclomatic Complexity = 11 |
| 72 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `get_logs`): Cyclomatic Complexity = 13 |


### 📄 `src/services/payment_fulfillment_service.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 14 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `fulfill_order`): Cyclomatic Complexity = 19 |


### 📄 `src/services/payment_validator.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 61 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `_check_new_transactions`): Cyclomatic Complexity = 12 |
| 124 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `_process_order`): Cyclomatic Complexity = 20 |


### 📄 `src/services/permission_service.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 207 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `refresh_user_group`): Cyclomatic Complexity = 13 |
| 379 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `perform_checkin`): Cyclomatic Complexity = 11 |


### 📄 `src/services/storage.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 23 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `_init_client`): Cyclomatic Complexity = 11 |


### 📄 `src/services/task_service.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 49 | 代码坏味道 | **Medium** | 高复杂度代码块 (class `TaskService`): Cyclomatic Complexity = 12 |
| 51 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `process_ltx_video_task`): Cyclomatic Complexity = 18 |
| 174 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `process_face_video_task`): Cyclomatic Complexity = 12 |
| 275 | 代码坏味道 | **High** | 高复杂度代码块 (method `process_generation_task`): Cyclomatic Complexity = 33 |
| 456 | 代码坏味道 | **High** | 高复杂度代码块 (method `_process_video_task_template`): Cyclomatic Complexity = 21 |
| 718 | 代码坏味道 | **High** | 高复杂度代码块 (method `process_custom_video_task`): Cyclomatic Complexity = 23 |
| 852 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `process_i2i_pro_task`): Cyclomatic Complexity = 11 |
| 977 | 代码坏味道 | **High** | 高复杂度代码块 (method `_monitor_task_progress`): Cyclomatic Complexity = 24 |
| 1055 | 代码坏味道 | **High** | 高复杂度代码块 (method `_handle_task_completion`): Cyclomatic Complexity = 37 |


### 📄 `src/services/zombie_cleaner_service.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 11 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `clean_zombies`): Cyclomatic Complexity = 14 |


### 📄 `src/utils.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 40 | 性能问题 | **Medium** | Unnecessary pass statement (unnecessary-pass) |
| 51 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 56 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 57 | 一般代码规范 | **Low** | Line too long (130/120) (line-too-long) |
| 64 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 82 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 87 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 88 | 一般代码规范 | **Low** | Line too long (131/120) (line-too-long) |
| 128 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 133 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 148 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 150 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 151 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 160 | 作用域分析 | **Medium** | Redefining name 'asyncio' from outer scope (line 1) (redefined-outer-name) |
| 160 | 导入优化 | **Medium** | Reimport 'asyncio' (imported line 1) (reimported) |
| 160 | 一般代码规范 | **Low** | Import outside toplevel (asyncio) (import-outside-toplevel) |
| 170 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 175 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 180 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 189 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 196 | 一般代码规范 | **Low** | Import outside toplevel (time) (import-outside-toplevel) |
| 198 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 200 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 205 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 218 | 一般代码规范 | **Low** | Line too long (135/120) (line-too-long) |
| 218 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |


### 📄 `src/web_api/core/config.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 6 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 6 | 一般代码规范 | **Low** | Too few public methods (0/2) (too-few-public-methods) |
| 9 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `src/web_api/core/security.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 7 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 20 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |


### 📄 `src/web_api/dependencies.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 12 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 16 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 19 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 23 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 30 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 30 | 代码坏味道 | **Low** | Too many local variables (17/15) (too-many-locals) |
| 39 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 43 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 47 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 51 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'except ValueError as exc' and 'raise credentials_exception from exc' (raise-missing-from) |
| 56 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 59 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 61 | 一般代码规范 | **Low** | Import outside toplevel (src.services.permission_service.permission_service) (import-outside-toplevel) |
| 65 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 71 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 77 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `src/web_api/main.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 4 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 5 | 导入优化 | **Low** | standard import "contextlib.asynccontextmanager" should be placed before third party imports "fastapi.FastAPI", "fastapi.middleware.cors.CORSMiddleware", "asgi_correlation_id.CorrelationIdMiddleware" (wrong-import-order) |
| 15 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 15 | 作用域分析 | **Medium** | Redefining name 'app' from outer scope (line 23) (redefined-outer-name) |
| 15 | 一般代码规范 | **Medium** | Unused argument 'app' (unused-argument) |
| 34 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 51 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |


### 📄 `src/web_api/routers/auth.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 8 | 导入优化 | **Medium** | Unused JSONResponse imported from fastapi.responses (unused-import) |
| 8 | 死代码检测 | **Low** | unused import 'JSONResponse' (90% confidence) |
| 13 | 导入优化 | **Medium** | Unused Token imported from src.web_api.schemas.auth_schema (unused-import) |
| 13 | 死代码检测 | **Low** | unused import 'Token' (90% confidence) |
| 25 | 一般代码规范 | **Low** | Import outside toplevel (time) (import-outside-toplevel) |
| 33 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 42 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 45 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 46 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 49 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 52 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 55 | 代码坏味道 | **Low** | Too many return statements (7/6) (too-many-return-statements) |
| 55 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `verify_telegram_webapp_initdata`): Cyclomatic Complexity = 13 |
| 67 | 一般代码规范 | **Low** | Import outside toplevel (time) (import-outside-toplevel) |
| 75 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 85 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 88 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 89 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 92 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 96 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 99 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 103 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 106 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 107 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 111 | 代码坏味道 | **Low** | Too many local variables (21/15) (too-many-locals) |
| 111 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `login_telegram`): Cyclomatic Complexity = 17 |
| 127 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 132 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 140 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 142 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 149 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 154 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 162 | 一般代码规范 | **Medium** | Unused variable 'is_new' (unused-variable) |
| 163 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 167 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 168 | 一般代码规范 | **Low** | Import outside toplevel (src.services.permission_service.permission_service) (import-outside-toplevel) |
| 172 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 175 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 178 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 184 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 187 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 202 | 一般代码规范 | **Low** | Line too long (141/120) (line-too-long) |
| 204 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 210 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 214 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 215 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Internal Server Error during authentication.') from e' (raise-missing-from) |


### 📄 `src/web_api/routers/gallery.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 1 | 导入优化 | **Medium** | Unused BackgroundTasks imported from fastapi (unused-import) |
| 4 | 导入优化 | **Low** | standard import "typing.List" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" (wrong-import-order) |
| 14 | 导入优化 | **Low** | Import "from src.constants import MODE_NAME_MAP, MODE_I2I_PRO, MODE_EDIT, MODE_CUSTOM_VIDEO, MODE_VIDEO_LORA, MODE_LTX_VIDEO" should be placed at the top of the module (wrong-import-position) |
| 15 | 导入优化 | **Low** | Import "from src.services.redis_client import redis_client" should be placed at the top of the module (wrong-import-position) |
| 16 | 导入优化 | **Low** | Import "import json" should be placed at the top of the module (wrong-import-position) |
| 16 | 导入优化 | **Low** | standard import "json" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" and first party imports "src.database.core.AsyncSessionLocal", "src.database.models.GalleryPost", "src.web_api.dependencies.get_current_user" (...) "src.handlers.fsm.edit_image_fsm.LORA_MODELS", "src.constants.MODE_NAME_MAP", "src.services.redis_client.redis_client"  (wrong-import-order) |
| 17 | 导入优化 | **Low** | Import "import logging" should be placed at the top of the module (wrong-import-position) |
| 17 | 导入优化 | **Low** | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" and first party imports "src.database.core.AsyncSessionLocal", "src.database.models.GalleryPost", "src.web_api.dependencies.get_current_user" (...) "src.handlers.fsm.edit_image_fsm.LORA_MODELS", "src.constants.MODE_NAME_MAP", "src.services.redis_client.redis_client"  (wrong-import-order) |
| 18 | 导入优化 | **Low** | Import "import os" should be placed at the top of the module (wrong-import-position) |
| 18 | 导入优化 | **Low** | standard import "os" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" and first party imports "src.database.core.AsyncSessionLocal", "src.database.models.GalleryPost", "src.web_api.dependencies.get_current_user" (...) "src.handlers.fsm.edit_image_fsm.LORA_MODELS", "src.constants.MODE_NAME_MAP", "src.services.redis_client.redis_client"  (wrong-import-order) |
| 18 | 导入优化 | **Medium** | Unused import os (unused-import) |
| 19 | 导入优化 | **Low** | Import "import re" should be placed at the top of the module (wrong-import-position) |
| 19 | 导入优化 | **Low** | standard import "re" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" and first party imports "src.database.core.AsyncSessionLocal", "src.database.models.GalleryPost", "src.web_api.dependencies.get_current_user" (...) "src.handlers.fsm.edit_image_fsm.LORA_MODELS", "src.constants.MODE_NAME_MAP", "src.services.redis_client.redis_client"  (wrong-import-order) |
| 20 | 导入优化 | **Low** | Import "from src.services.storage import storage" should be placed at the top of the module (wrong-import-position) |
| 28 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 38 | 导入优化 | **Low** | Import "from config import R2_PUBLIC_DOMAIN" should be placed at the top of the module (wrong-import-position) |
| 48 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 60 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 60 | 一般代码规范 | **Medium** | Unused argument 'media_type' (unused-argument) |
| 66 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 81 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 81 | 代码坏味道 | **Low** | Too many arguments (8/5) (too-many-arguments) |
| 81 | 一般代码规范 | **Low** | Too many positional arguments (8/5) (too-many-positional-arguments) |
| 81 | 代码坏味道 | **Low** | Too many local variables (37/15) (too-many-locals) |
| 81 | 代码坏味道 | **Low** | Too many branches (16/12) (too-many-branches) |
| 81 | 代码坏味道 | **Low** | Too many statements (60/50) (too-many-statements) |
| 81 | 代码坏味道 | **High** | 高复杂度代码块 (function `get_gallery_posts`): Cyclomatic Complexity = 24 |
| 92 | 一般代码规范 | **Low** | Comparison 'GalleryPost.is_active == True' should be 'GalleryPost.is_active is True' if checking for the singleton value True, or 'bool(GalleryPost.is_active)' if testing for truthiness (singleton-comparison) |
| 93 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 98 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 101 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 107 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 109 | 一般代码规范 | **Low** | Import outside toplevel (datetime.datetime, datetime.timedelta) (import-outside-toplevel) |
| 120 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 127 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 129 | 一般代码规范 | **Low** | Import outside toplevel (sqlalchemy.func) (import-outside-toplevel) |
| 130 | 一般代码规范 | **High** | func.count is not callable (not-callable) |
| 132 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 139 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 157 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 162 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 165 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 172 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 175 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 207 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 207 | 代码坏味道 | **Low** | Too many local variables (28/15) (too-many-locals) |
| 207 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `get_my_gallery_posts`): Cyclomatic Complexity = 12 |
| 214 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 216 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 218 | 一般代码规范 | **Low** | Import outside toplevel (sqlalchemy.func) (import-outside-toplevel) |
| 219 | 一般代码规范 | **High** | func.count is not callable (not-callable) |
| 221 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 225 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 228 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 245 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 250 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 253 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 259 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 262 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 283 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 294 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 294 | 代码坏味道 | **Low** | Too many local variables (30/15) (too-many-locals) |
| 294 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `get_my_favorite_posts`): Cyclomatic Complexity = 14 |
| 312 | 一般代码规范 | **Low** | Comparison 'GalleryPost.is_active == True' should be 'GalleryPost.is_active is True' if checking for the singleton value True, or 'bool(GalleryPost.is_active)' if testing for truthiness (singleton-comparison) |
| 314 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 316 | 一般代码规范 | **Low** | Import outside toplevel (sqlalchemy.func) (import-outside-toplevel) |
| 317 | 一般代码规范 | **High** | func.count is not callable (not-callable) |
| 319 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 323 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 326 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 343 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 348 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 351 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 357 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 360 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 381 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 392 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 403 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 409 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 413 | 一般代码规范 | **Low** | Import outside toplevel (sqlalchemy.delete) (import-outside-toplevel) |
| 420 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 423 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 425 | 一般代码规范 | **Low** | Line too long (138/120) (line-too-long) |
| 426 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 429 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 435 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 440 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 449 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 457 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 463 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 466 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 468 | 一般代码规范 | **Low** | Line too long (135/120) (line-too-long) |
| 470 | 一般代码规范 | **Low** | Line too long (141/120) (line-too-long) |
| 471 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 476 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'except IntegrityError as exc' and 'raise HTTPException(status_code=400, detail='重复操作：您已经给过评价了！') from exc' (raise-missing-from) |
| 480 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 488 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 491 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 494 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 498 | 一般代码规范 | **Low** | Line too long (135/120) (line-too-long) |
| 504 | 性能问题 | **Medium** | Unnecessary pass statement (unnecessary-pass) |
| 505 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 509 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 516 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 525 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 530 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 546 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 546 | 代码坏味道 | **Low** | Too many local variables (28/15) (too-many-locals) |
| 546 | 代码坏味道 | **Low** | Too many branches (14/12) (too-many-branches) |
| 546 | 代码坏味道 | **Low** | Too many statements (57/50) (too-many-statements) |
| 546 | 代码坏味道 | **High** | 高复杂度代码块 (function `submit_to_gallery`): Cyclomatic Complexity = 21 |
| 562 | 一般代码规范 | **Low** | Line too long (133/120) (line-too-long) |
| 608 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 614 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 634 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 635 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |


### 📄 `src/web_api/routers/storage.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 3 | 导入优化 | **Medium** | Unused status imported from fastapi (unused-import) |
| 4 | 导入优化 | **Low** | standard import "typing.Optional" should be placed before third party import "fastapi.APIRouter" (wrong-import-order) |
| 4 | 导入优化 | **Medium** | Unused Optional imported from typing (unused-import) |
| 5 | 导入优化 | **Low** | standard import "datetime.datetime" should be placed before third party import "fastapi.APIRouter" (wrong-import-order) |
| 27 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 32 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 34 | 一般代码规范 | **Low** | Line too long (146/120) (line-too-long) |
| 35 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 38 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 39 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 43 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 46 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 53 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 54 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise HTTPException(status_code=500, detail='Internal server error generating URL') from e' (raise-missing-from) |


### 📄 `src/web_api/routers/tasks.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 4 | 导入优化 | **Medium** | Unused import httpx (unused-import) |
| 5 | 导入优化 | **Low** | standard import "typing.AsyncGenerator" should be placed before third party import "httpx" (wrong-import-order) |
| 5 | 导入优化 | **Medium** | Unused AsyncGenerator imported from typing (unused-import) |
| 6 | 导入优化 | **Medium** | Unused status imported from fastapi (unused-import) |
| 6 | 导入优化 | **Medium** | Unused Request imported from fastapi (unused-import) |
| 13 | 一般代码规范 | **Low** | Line too long (156/120) (line-too-long) |
| 24 | 导入优化 | **Low** | Import "from src.utils import load_prompts" should be placed at the top of the module (wrong-import-position) |
| 25 | 导入优化 | **Low** | Import "from src.constants import TASK_COSTS, RESOLUTION_COST, DURATION_MULTIPLIER, MODE_I2I_PRO, MODE_FACESWAP_STEP1" should be placed at the top of the module (wrong-import-position) |
| 27 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `calculate_task_cost`): Cyclomatic Complexity = 11 |
| 35 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 36 | 一般代码规范 | **Low** | Line too long (162/120) (line-too-long) |
| 38 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 39 | 一般代码规范 | **Low** | Unnecessary "else" after "return", remove the "else" and de-indent the code inside it (no-else-return) |
| 42 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 44 | 一般代码规范 | **Low** | Import outside toplevel (src.constants.LTX_RESOLUTION_COST, src.constants.LTX_DURATION_MULTIPLIER) (import-outside-toplevel) |
| 52 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 59 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 66 | 导入优化 | **Low** | Import "from src.logger import UserLogger" should be placed at the top of the module (wrong-import-position) |
| 68 | 代码坏味道 | **Low** | Too many arguments (9/5) (too-many-arguments) |
| 68 | 一般代码规范 | **Low** | Too many positional arguments (9/5) (too-many-positional-arguments) |
| 68 | 代码坏味道 | **Low** | Too many local variables (18/15) (too-many-locals) |
| 68 | 代码坏味道 | **Medium** | 高复杂度代码块 (function `monitor_task_and_release_lock`): Cyclomatic Complexity = 12 |
| 69 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 70 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 72 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 84 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 93 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 94 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 100 | 一般代码规范 | **Low** | Line too long (138/120) (line-too-long) |
| 103 | 一般代码规范 | **Low** | Line too long (122/120) (line-too-long) |
| 104 | 一般代码规范 | **Low** | Line too long (170/120) (line-too-long) |
| 106 | 一般代码规范 | **Low** | Line too long (163/120) (line-too-long) |
| 107 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 108 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 109 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 115 | 代码坏味道 | **Low** | Too many local variables (37/15) (too-many-locals) |
| 115 | 代码坏味道 | **Low** | Too many branches (21/12) (too-many-branches) |
| 115 | 代码坏味道 | **Low** | Too many statements (81/50) (too-many-statements) |
| 115 | 代码坏味道 | **High** | 高复杂度代码块 (function `create_generation_task`): Cyclomatic Complexity = 28 |
| 123 | 一般代码规范 | **Low** | Line too long (162/120) (line-too-long) |
| 125 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 130 | 一般代码规范 | **Low** | Line too long (149/120) (line-too-long) |
| 131 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 134 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 139 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 142 | 一般代码规范 | **Low** | Line too long (122/120) (line-too-long) |
| 146 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 150 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 151 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 153 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 156 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 160 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 169 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 175 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 198 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 217 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 218 | 一般代码规范 | **Low** | Import outside toplevel (src.handlers.fsm.edit_image_fsm.get_lora_default_strength) (import-outside-toplevel) |
| 221 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 225 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 228 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 245 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 250 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 257 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 258 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 259 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 261 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 268 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 277 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 283 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 284 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise HTTPException(status_code=400, detail=str(ve)) from ve' (raise-missing-from) |
| 287 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 290 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise HTTPException(status_code=500, detail='Internal server error') from e' (raise-missing-from) |
| 293 | 代码坏味道 | **Low** | Too many statements (119/50) (too-many-statements) |
| 299 | 作用域分析 | **Medium** | Redefining name 'httpx' from outer scope (line 4) (redefined-outer-name) |
| 299 | 导入优化 | **Medium** | Reimport 'httpx' (imported line 4) (reimported) |
| 299 | 一般代码规范 | **Low** | Import outside toplevel (httpx) (import-outside-toplevel) |
| 300 | 一般代码规范 | **Low** | Import outside toplevel (config.API_BASE) (import-outside-toplevel) |
| 308 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 309 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 312 | 代码坏味道 | **Low** | Too many local variables (23/15) (too-many-locals) |
| 312 | 代码坏味道 | **Low** | Too many branches (29/12) (too-many-branches) |
| 312 | 代码坏味道 | **Low** | Too many statements (111/50) (too-many-statements) |
| 313 | 一般代码规范 | **High** | Instance of 'RedisClient' has no 'redis' member (no-member) |
| 316 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 323 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 327 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 337 | 一般代码规范 | **Low** | Line too long (205/120) (line-too-long) |
| 339 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 340 | 一般代码规范 | **Low** | Import outside toplevel (src.database.core.AsyncSessionLocal) (import-outside-toplevel) |
| 341 | 一般代码规范 | **Low** | Import outside toplevel (src.database.models.History) (import-outside-toplevel) |
| 342 | 一般代码规范 | **Low** | Import outside toplevel (sqlalchemy.select) (import-outside-toplevel) |
| 343 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 347 | 一般代码规范 | **Low** | Line too long (129/120) (line-too-long) |
| 352 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 353 | 一般代码规范 | **Low** | Line too long (121/120) (line-too-long) |
| 358 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 364 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 366 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 373 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 377 | 作用域分析 | **Medium** | Redefining name 'status' from outer scope (line 6) (redefined-outer-name) |
| 378 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 383 | 一般代码规范 | **Low** | Line too long (209/120) (line-too-long) |
| 385 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 387 | 一般代码规范 | **Low** | Import outside toplevel (src.database.core.AsyncSessionLocal) (import-outside-toplevel) |
| 388 | 一般代码规范 | **Low** | Import outside toplevel (src.database.models.History) (import-outside-toplevel) |
| 389 | 一般代码规范 | **Low** | Import outside toplevel (sqlalchemy.select) (import-outside-toplevel) |
| 390 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 394 | 一般代码规范 | **Low** | Line too long (133/120) (line-too-long) |
| 399 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 400 | 一般代码规范 | **Low** | Line too long (125/120) (line-too-long) |
| 405 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 411 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 422 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 424 | 代码坏味道 | **Low** | Too many nested blocks (6/5) (too-many-nested-blocks) |
| 437 | 一般代码规范 | **Low** | Line too long (217/120) (line-too-long) |
| 439 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 440 | 一般代码规范 | **Low** | Import outside toplevel (src.database.core.AsyncSessionLocal) (import-outside-toplevel) |
| 441 | 一般代码规范 | **Low** | Import outside toplevel (src.database.models.History) (import-outside-toplevel) |
| 442 | 一般代码规范 | **Low** | Import outside toplevel (sqlalchemy.select) (import-outside-toplevel) |
| 443 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 447 | 一般代码规范 | **Low** | Line too long (141/120) (line-too-long) |
| 448 | 一般代码规范 | **Low** | Line too long (127/120) (line-too-long) |
| 452 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 453 | 一般代码规范 | **Low** | Line too long (133/120) (line-too-long) |
| 463 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 474 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 477 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 479 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |


### 📄 `src/web_api/routers/users.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Medium** | Unused Query imported from fastapi (unused-import) |
| 2 | 导入优化 | **Medium** | Unused HTTPException imported from fastapi (unused-import) |
| 3 | 导入优化 | **Medium** | Unused func imported from sqlalchemy (unused-import) |
| 15 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 25 | 一般代码规范 | **Low** | Import outside toplevel (src.services.permission_service.permission_service) (import-outside-toplevel) |
| 27 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 32 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 59 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 69 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `src/web_api/routers/utils.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 4 | 一般代码规范 | **Low** | Trailing newlines (trailing-newlines) |


### 📄 `src/web_api/schemas/auth_schema.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 1 | 导入优化 | **Medium** | Unused Field imported from pydantic (unused-import) |
| 2 | 导入优化 | **Low** | standard import "typing.Optional" should be placed before third party import "pydantic.BaseModel" (wrong-import-order) |
| 3 | 导入优化 | **Low** | standard import "datetime.datetime" should be placed before third party import "pydantic.BaseModel" (wrong-import-order) |
| 5 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 13 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 17 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 21 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 28 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 42 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 43 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 43 | 一般代码规范 | **Low** | Too few public methods (0/2) (too-few-public-methods) |


### 📄 `src/web_api/schemas/gallery_schema.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "typing.List" should be placed before third party import "pydantic.BaseModel" (wrong-import-order) |
| 3 | 导入优化 | **Low** | standard import "datetime.datetime" should be placed before third party import "pydantic.BaseModel" (wrong-import-order) |
| 5 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 22 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 27 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 34 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |


### 📄 `src/web_api/schemas/task_schema.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "typing.Optional" should be placed before third party import "pydantic.BaseModel" (wrong-import-order) |
| 2 | 导入优化 | **Medium** | Unused List imported from typing (unused-import) |
| 4 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 11 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 12 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 12 | 一般代码规范 | **Low** | Too few public methods (0/2) (too-few-public-methods) |
| 23 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |


### 📄 `src/web_api/schemas/user_schema.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "typing.Optional" should be placed before third party import "pydantic.BaseModel" (wrong-import-order) |
| 3 | 导入优化 | **Low** | standard import "datetime.datetime" should be placed before third party import "pydantic.BaseModel" (wrong-import-order) |
| 5 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 15 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 16 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 16 | 一般代码规范 | **Low** | Too few public methods (0/2) (too-few-public-methods) |
| 19 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |


### 📄 `workers/comfy_agent1/agent_main.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 6 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 8 | 一般代码规范 | **High** | Unable to import 'websockets' (import-error) |
| 11 | 导入优化 | **Low** | standard import "typing.Dict" should be placed before third party imports "asgi_correlation_id.correlation_id", "httpx", "websockets", "minio.Minio", "dotenv.load_dotenv" (wrong-import-order) |
| 13 | 一般代码规范 | **High** | Unable to import 'comfy_client' (import-error) |
| 14 | 一般代码规范 | **High** | Unable to import 'workflow_patcher' (import-error) |
| 25 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 25 | 一般代码规范 | **Low** | Too few public methods (1/2) (too-few-public-methods) |
| 31 | 一般代码规范 | **Low** | Constant name "log_format" doesn't conform to UPPER_CASE naming style (invalid-name) |
| 59 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 59 | 架构问题 | **Low** | Too many instance attributes (11/7) (too-many-instance-attributes) |
| 64 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 78 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 79 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 89 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 102 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 103 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 105 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 106 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 111 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 120 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 121 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 123 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 130 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 131 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 133 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 133 | 代码坏味道 | **Low** | Too many local variables (23/15) (too-many-locals) |
| 133 | 代码坏味道 | **Low** | Too many branches (21/12) (too-many-branches) |
| 133 | 代码坏味道 | **Low** | Too many statements (70/50) (too-many-statements) |
| 133 | 代码坏味道 | **High** | 高复杂度代码块 (method `ws_listener_loop`): Cyclomatic Complexity = 24 |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 140 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 151 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 152 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 155 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 158 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 162 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 169 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 172 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 179 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 183 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 187 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 189 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 191 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 207 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 214 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 217 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 218 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 219 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 222 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 224 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 225 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 228 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 232 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 233 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 236 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 238 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 239 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 247 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 248 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 251 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 258 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 259 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 262 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 262 | 代码坏味道 | **Low** | Too many local variables (39/15) (too-many-locals) |
| 262 | 代码坏味道 | **Low** | Too many branches (38/12) (too-many-branches) |
| 262 | 代码坏味道 | **Low** | Too many statements (138/50) (too-many-statements) |
| 262 | 代码坏味道 | **High** | 高复杂度代码块 (method `process_task`): Cyclomatic Complexity = 43 |
| 266 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 271 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 274 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 279 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 280 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 285 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 290 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 299 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 304 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 305 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 306 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 310 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 311 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 350 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 351 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 359 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 362 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 365 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 370 | 一般代码规范 | **Medium** | Unused variable 'node_id' (unused-variable) |
| 374 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 375 | 一般代码规范 | **Low** | Unnecessary "elif" after "break", remove the leading "el" from "elif" (no-else-break) |
| 387 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 388 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 391 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 394 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 409 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 410 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 414 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 415 | 一般代码规范 | **Low** | Line too long (123/120) (line-too-long) |
| 415 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 416 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 419 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 421 | 一般代码规范 | **Low** | Import outside toplevel (io) (import-outside-toplevel) |
| 429 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 430 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 439 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 441 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 442 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise Exception(f'Result processing failed: {e}') from e' (raise-missing-from) |
| 442 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 446 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 448 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 449 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 458 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 459 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 460 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 462 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 463 | 一般代码规范 | **Low** | Line too long (127/120) (line-too-long) |
| 463 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 470 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 479 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 480 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 482 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 483 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 484 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 485 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 489 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 493 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 496 | 一般代码规范 | **Medium** | Attribute 'tasks' defined outside __init__ (attribute-defined-outside-init) |
| 503 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 506 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 509 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 512 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 516 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 517 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 518 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 522 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 530 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 533 | 导入优化 | **Medium** | Reimport 'sys' (imported line 5) (reimported) |
| 533 | 一般代码规范 | **Low** | Imports from package sys are not grouped (ungrouped-imports) |
| 535 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 542 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `workers/comfy_agent1/comfy_client.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "logging" should be placed before third party import "httpx" (wrong-import-order) |
| 3 | 导入优化 | **Low** | standard import "typing.Dict" should be placed before third party import "httpx" (wrong-import-order) |
| 7 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 12 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 16 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 17 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 31 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 37 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 41 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 52 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 66 | 一般代码规范 | **Medium** | Redefining built-in 'type' (redefined-builtin) |
| 71 | 一般代码规范 | **Low** | Import outside toplevel (asyncio) (import-outside-toplevel) |
| 73 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 80 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 82 | 一般代码规范 | **Low** | Line too long (140/120) (line-too-long) |
| 82 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 85 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 87 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 89 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |


### 📄 `workers/comfy_agent1/workflow_patcher.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 8 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 8 | 代码坏味道 | **Medium** | 高复杂度代码块 (class `WorkflowPatcher`): Cyclomatic Complexity = 18 |
| 13 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 20 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 26 | 一般代码规范 | **Low** | Consider using enumerate instead of iterating with range and len (consider-using-enumerate) |
| 30 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 30 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `load_workflow`): Cyclomatic Complexity = 14 |
| 51 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 54 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 56 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 60 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 62 | 一般代码规范 | **Low** | Line too long (133/120) (line-too-long) |
| 62 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 65 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 65 | 代码坏味道 | **Low** | Too many local variables (16/15) (too-many-locals) |
| 65 | 代码坏味道 | **Low** | Too many branches (30/12) (too-many-branches) |
| 65 | 代码坏味道 | **Low** | Too many statements (60/50) (too-many-statements) |
| 65 | 代码坏味道 | **High** | 高复杂度代码块 (method `patch_workflow`): Cyclomatic Complexity = 39 |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 71 | 一般代码规范 | **Low** | Import outside toplevel (random) (import-outside-toplevel) |
| 75 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 78 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 81 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 94 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 97 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 102 | 一般代码规范 | **Low** | "str(lora_name).strip() != ''" can be simplified to "str(lora_name).strip()", if it is strictly a string, as an empty string is falsey (use-implicit-booleaness-not-comparison-to-string) |
| 116 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 126 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 148 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 156 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 159 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 159 | 代码坏味道 | **Low** | Too many branches (23/12) (too-many-branches) |
| 159 | 代码坏味道 | **High** | 高复杂度代码块 (method `heuristic_patch`): Cyclomatic Complexity = 40 |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 167 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 168 | 一般代码规范 | **Low** | Line too long (124/120) (line-too-long) |
| 176 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 178 | 一般代码规范 | **Low** | Line too long (153/120) (line-too-long) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 189 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 193 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 199 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 202 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 205 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `workers/comfy_agent1/workflows/LTX 2.3 I2V.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 50 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "lora": "ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors", |


### 📄 `workers/comfy_agent1/workflows/Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 551 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "text": "<lora:Mystic-XXX-ZIT-V5:0.10>", |
| 555 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "name": "Mystic-XXX-ZIT-V5", |


### 📄 `workers/comfy_agent2/agent_main.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 6 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 8 | 一般代码规范 | **High** | Unable to import 'websockets' (import-error) |
| 11 | 导入优化 | **Low** | standard import "typing.Dict" should be placed before third party imports "asgi_correlation_id.correlation_id", "httpx", "websockets", "minio.Minio", "dotenv.load_dotenv" (wrong-import-order) |
| 13 | 一般代码规范 | **High** | Unable to import 'comfy_client' (import-error) |
| 14 | 一般代码规范 | **High** | Unable to import 'workflow_patcher' (import-error) |
| 25 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 25 | 一般代码规范 | **Low** | Too few public methods (1/2) (too-few-public-methods) |
| 31 | 一般代码规范 | **Low** | Constant name "log_format" doesn't conform to UPPER_CASE naming style (invalid-name) |
| 59 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 59 | 架构问题 | **Low** | Too many instance attributes (11/7) (too-many-instance-attributes) |
| 64 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 78 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 79 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 89 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 102 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 103 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 105 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 106 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 111 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 120 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 121 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 123 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 130 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 131 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 133 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 133 | 代码坏味道 | **Low** | Too many local variables (23/15) (too-many-locals) |
| 133 | 代码坏味道 | **Low** | Too many branches (21/12) (too-many-branches) |
| 133 | 代码坏味道 | **Low** | Too many statements (70/50) (too-many-statements) |
| 133 | 代码坏味道 | **High** | 高复杂度代码块 (method `ws_listener_loop`): Cyclomatic Complexity = 24 |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 140 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 151 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 152 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 155 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 158 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 162 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 169 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 172 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 179 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 183 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 187 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 189 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 191 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 207 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 214 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 217 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 218 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 219 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 222 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 224 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 225 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 228 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 232 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 233 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 236 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 238 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 239 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 247 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 248 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 251 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 258 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 259 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 262 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 262 | 代码坏味道 | **Low** | Too many local variables (39/15) (too-many-locals) |
| 262 | 代码坏味道 | **Low** | Too many branches (38/12) (too-many-branches) |
| 262 | 代码坏味道 | **Low** | Too many statements (138/50) (too-many-statements) |
| 262 | 代码坏味道 | **High** | 高复杂度代码块 (method `process_task`): Cyclomatic Complexity = 43 |
| 266 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 271 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 274 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 279 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 280 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 285 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 290 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 299 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 304 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 305 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 306 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 310 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 311 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 350 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 351 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 359 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 362 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 365 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 370 | 一般代码规范 | **Medium** | Unused variable 'node_id' (unused-variable) |
| 374 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 375 | 一般代码规范 | **Low** | Unnecessary "elif" after "break", remove the leading "el" from "elif" (no-else-break) |
| 387 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 388 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 391 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 394 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 409 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 410 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 414 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 415 | 一般代码规范 | **Low** | Line too long (123/120) (line-too-long) |
| 415 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 416 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 419 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 421 | 一般代码规范 | **Low** | Import outside toplevel (io) (import-outside-toplevel) |
| 429 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 430 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 439 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 441 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 442 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise Exception(f'Result processing failed: {e}') from e' (raise-missing-from) |
| 442 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 446 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 448 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 449 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 458 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 459 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 460 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 462 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 463 | 一般代码规范 | **Low** | Line too long (127/120) (line-too-long) |
| 463 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 470 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 479 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 480 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 482 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 483 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 484 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 485 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 489 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 493 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 496 | 一般代码规范 | **Medium** | Attribute 'tasks' defined outside __init__ (attribute-defined-outside-init) |
| 503 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 506 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 509 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 512 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 516 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 517 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 518 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 522 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 530 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 533 | 导入优化 | **Medium** | Reimport 'sys' (imported line 5) (reimported) |
| 533 | 一般代码规范 | **Low** | Imports from package sys are not grouped (ungrouped-imports) |
| 535 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 542 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `workers/comfy_agent2/comfy_client.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "logging" should be placed before third party import "httpx" (wrong-import-order) |
| 3 | 导入优化 | **Low** | standard import "typing.Dict" should be placed before third party import "httpx" (wrong-import-order) |
| 7 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 12 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 16 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 17 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 29 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 33 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 44 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 58 | 一般代码规范 | **Medium** | Redefining built-in 'type' (redefined-builtin) |
| 63 | 一般代码规范 | **Low** | Import outside toplevel (asyncio) (import-outside-toplevel) |
| 65 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 72 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 74 | 一般代码规范 | **Low** | Line too long (140/120) (line-too-long) |
| 74 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 77 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 79 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 81 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |


### 📄 `workers/comfy_agent2/workflow_patcher.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 8 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 8 | 代码坏味道 | **Medium** | 高复杂度代码块 (class `WorkflowPatcher`): Cyclomatic Complexity = 18 |
| 13 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 20 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 26 | 一般代码规范 | **Low** | Consider using enumerate instead of iterating with range and len (consider-using-enumerate) |
| 30 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 30 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `load_workflow`): Cyclomatic Complexity = 14 |
| 51 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 54 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 56 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 60 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 62 | 一般代码规范 | **Low** | Line too long (133/120) (line-too-long) |
| 62 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 65 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 65 | 代码坏味道 | **Low** | Too many local variables (16/15) (too-many-locals) |
| 65 | 代码坏味道 | **Low** | Too many branches (30/12) (too-many-branches) |
| 65 | 代码坏味道 | **Low** | Too many statements (60/50) (too-many-statements) |
| 65 | 代码坏味道 | **High** | 高复杂度代码块 (method `patch_workflow`): Cyclomatic Complexity = 39 |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 71 | 一般代码规范 | **Low** | Import outside toplevel (random) (import-outside-toplevel) |
| 75 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 78 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 81 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 94 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 97 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 102 | 一般代码规范 | **Low** | "str(lora_name).strip() != ''" can be simplified to "str(lora_name).strip()", if it is strictly a string, as an empty string is falsey (use-implicit-booleaness-not-comparison-to-string) |
| 116 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 126 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 148 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 156 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 159 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 159 | 代码坏味道 | **Low** | Too many branches (23/12) (too-many-branches) |
| 159 | 代码坏味道 | **High** | 高复杂度代码块 (method `heuristic_patch`): Cyclomatic Complexity = 40 |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 167 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 168 | 一般代码规范 | **Low** | Line too long (124/120) (line-too-long) |
| 176 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 178 | 一般代码规范 | **Low** | Line too long (153/120) (line-too-long) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 189 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 193 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 199 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 202 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 205 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `workers/comfy_agent2/workflows/LTX 2.3 I2V.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 50 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "lora": "ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors", |


### 📄 `workers/comfy_agent2/workflows/Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 551 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "text": "<lora:Mystic-XXX-ZIT-V5:0.10>", |
| 555 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "name": "Mystic-XXX-ZIT-V5", |


### 📄 `workers/comfy_agent3/agent_main.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 6 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 8 | 一般代码规范 | **High** | Unable to import 'websockets' (import-error) |
| 11 | 导入优化 | **Low** | standard import "typing.Dict" should be placed before third party imports "asgi_correlation_id.correlation_id", "httpx", "websockets", "minio.Minio", "dotenv.load_dotenv" (wrong-import-order) |
| 13 | 一般代码规范 | **High** | Unable to import 'comfy_client' (import-error) |
| 14 | 一般代码规范 | **High** | Unable to import 'workflow_patcher' (import-error) |
| 25 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 25 | 一般代码规范 | **Low** | Too few public methods (1/2) (too-few-public-methods) |
| 31 | 一般代码规范 | **Low** | Constant name "log_format" doesn't conform to UPPER_CASE naming style (invalid-name) |
| 59 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 59 | 架构问题 | **Low** | Too many instance attributes (11/7) (too-many-instance-attributes) |
| 64 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 78 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 79 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 89 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 102 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 103 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 105 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 106 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 111 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 120 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 121 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 123 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 130 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 131 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 133 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 133 | 代码坏味道 | **Low** | Too many local variables (23/15) (too-many-locals) |
| 133 | 代码坏味道 | **Low** | Too many branches (21/12) (too-many-branches) |
| 133 | 代码坏味道 | **Low** | Too many statements (70/50) (too-many-statements) |
| 133 | 代码坏味道 | **High** | 高复杂度代码块 (method `ws_listener_loop`): Cyclomatic Complexity = 24 |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 140 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 151 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 152 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 155 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 158 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 162 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 169 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 172 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 179 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 183 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 187 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 189 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 191 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 207 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 214 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 217 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 218 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 219 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 222 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 224 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 225 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 228 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 232 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 233 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 236 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 238 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 239 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 247 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 248 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 251 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 258 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 259 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 262 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 262 | 代码坏味道 | **Low** | Too many local variables (39/15) (too-many-locals) |
| 262 | 代码坏味道 | **Low** | Too many branches (38/12) (too-many-branches) |
| 262 | 代码坏味道 | **Low** | Too many statements (138/50) (too-many-statements) |
| 262 | 代码坏味道 | **High** | 高复杂度代码块 (method `process_task`): Cyclomatic Complexity = 43 |
| 266 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 271 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 274 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 279 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 280 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 285 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 290 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 299 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 304 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 305 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 306 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 310 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 311 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 350 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 351 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 359 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 362 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 365 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 370 | 一般代码规范 | **Medium** | Unused variable 'node_id' (unused-variable) |
| 374 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 375 | 一般代码规范 | **Low** | Unnecessary "elif" after "break", remove the leading "el" from "elif" (no-else-break) |
| 387 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 388 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 391 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 394 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 409 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 410 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 414 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 415 | 一般代码规范 | **Low** | Line too long (123/120) (line-too-long) |
| 415 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 416 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 419 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 421 | 一般代码规范 | **Low** | Import outside toplevel (io) (import-outside-toplevel) |
| 429 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 430 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 439 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 441 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 442 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise Exception(f'Result processing failed: {e}') from e' (raise-missing-from) |
| 442 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 446 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 448 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 449 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 458 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 459 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 460 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 462 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 463 | 一般代码规范 | **Low** | Line too long (127/120) (line-too-long) |
| 463 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 470 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 479 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 480 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 482 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 483 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 484 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 485 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 489 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 493 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 496 | 一般代码规范 | **Medium** | Attribute 'tasks' defined outside __init__ (attribute-defined-outside-init) |
| 503 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 506 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 509 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 512 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 516 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 517 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 518 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 522 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 530 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 533 | 导入优化 | **Medium** | Reimport 'sys' (imported line 5) (reimported) |
| 533 | 一般代码规范 | **Low** | Imports from package sys are not grouped (ungrouped-imports) |
| 535 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 542 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `workers/comfy_agent3/comfy_client.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "logging" should be placed before third party import "httpx" (wrong-import-order) |
| 3 | 导入优化 | **Low** | standard import "typing.Dict" should be placed before third party import "httpx" (wrong-import-order) |
| 7 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 12 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 16 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 17 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 29 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 33 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 44 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 58 | 一般代码规范 | **Medium** | Redefining built-in 'type' (redefined-builtin) |
| 63 | 一般代码规范 | **Low** | Import outside toplevel (asyncio) (import-outside-toplevel) |
| 65 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 72 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 74 | 一般代码规范 | **Low** | Line too long (140/120) (line-too-long) |
| 74 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 77 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 79 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 81 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |


### 📄 `workers/comfy_agent3/workflow_patcher.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 8 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 8 | 代码坏味道 | **Medium** | 高复杂度代码块 (class `WorkflowPatcher`): Cyclomatic Complexity = 18 |
| 13 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 20 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 26 | 一般代码规范 | **Low** | Consider using enumerate instead of iterating with range and len (consider-using-enumerate) |
| 30 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 30 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `load_workflow`): Cyclomatic Complexity = 14 |
| 51 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 54 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 56 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 60 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 62 | 一般代码规范 | **Low** | Line too long (133/120) (line-too-long) |
| 62 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 65 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 65 | 代码坏味道 | **Low** | Too many local variables (16/15) (too-many-locals) |
| 65 | 代码坏味道 | **Low** | Too many branches (30/12) (too-many-branches) |
| 65 | 代码坏味道 | **Low** | Too many statements (60/50) (too-many-statements) |
| 65 | 代码坏味道 | **High** | 高复杂度代码块 (method `patch_workflow`): Cyclomatic Complexity = 39 |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 71 | 一般代码规范 | **Low** | Import outside toplevel (random) (import-outside-toplevel) |
| 75 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 78 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 81 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 94 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 97 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 102 | 一般代码规范 | **Low** | "str(lora_name).strip() != ''" can be simplified to "str(lora_name).strip()", if it is strictly a string, as an empty string is falsey (use-implicit-booleaness-not-comparison-to-string) |
| 116 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 126 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 148 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 156 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 159 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 159 | 代码坏味道 | **Low** | Too many branches (23/12) (too-many-branches) |
| 159 | 代码坏味道 | **High** | 高复杂度代码块 (method `heuristic_patch`): Cyclomatic Complexity = 40 |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 167 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 168 | 一般代码规范 | **Low** | Line too long (124/120) (line-too-long) |
| 176 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 178 | 一般代码规范 | **Low** | Line too long (153/120) (line-too-long) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 189 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 193 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 199 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 202 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 205 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `workers/comfy_agent3/workflows/LTX 2.3 I2V.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 50 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "lora": "ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors", |


### 📄 `workers/comfy_agent3/workflows/Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 551 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "text": "<lora:Mystic-XXX-ZIT-V5:0.10>", |
| 555 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "name": "Mystic-XXX-ZIT-V5", |


### 📄 `workers/comfy_agent4/agent_main.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 6 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 8 | 一般代码规范 | **High** | Unable to import 'websockets' (import-error) |
| 11 | 导入优化 | **Low** | standard import "typing.Dict" should be placed before third party imports "asgi_correlation_id.correlation_id", "httpx", "websockets", "minio.Minio", "dotenv.load_dotenv" (wrong-import-order) |
| 13 | 一般代码规范 | **High** | Unable to import 'comfy_client' (import-error) |
| 14 | 一般代码规范 | **High** | Unable to import 'workflow_patcher' (import-error) |
| 25 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 25 | 一般代码规范 | **Low** | Too few public methods (1/2) (too-few-public-methods) |
| 31 | 一般代码规范 | **Low** | Constant name "log_format" doesn't conform to UPPER_CASE naming style (invalid-name) |
| 59 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 59 | 架构问题 | **Low** | Too many instance attributes (11/7) (too-many-instance-attributes) |
| 64 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 78 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 79 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 89 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 102 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 103 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 105 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 106 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 111 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 120 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 121 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 123 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 130 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 131 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 133 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 133 | 代码坏味道 | **Low** | Too many local variables (23/15) (too-many-locals) |
| 133 | 代码坏味道 | **Low** | Too many branches (21/12) (too-many-branches) |
| 133 | 代码坏味道 | **Low** | Too many statements (70/50) (too-many-statements) |
| 133 | 代码坏味道 | **High** | 高复杂度代码块 (method `ws_listener_loop`): Cyclomatic Complexity = 24 |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 140 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 151 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 152 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 155 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 158 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 162 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 169 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 172 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 179 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 183 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 187 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 189 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 191 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 207 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 214 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 217 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 218 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 219 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 222 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 224 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 225 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 228 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 232 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 233 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 236 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 238 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 239 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 247 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 248 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 251 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 258 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 259 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 262 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 262 | 代码坏味道 | **Low** | Too many local variables (39/15) (too-many-locals) |
| 262 | 代码坏味道 | **Low** | Too many branches (38/12) (too-many-branches) |
| 262 | 代码坏味道 | **Low** | Too many statements (138/50) (too-many-statements) |
| 262 | 代码坏味道 | **High** | 高复杂度代码块 (method `process_task`): Cyclomatic Complexity = 43 |
| 266 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 271 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 274 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 279 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 280 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 285 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 290 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 299 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 304 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 305 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 306 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 310 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 311 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 350 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 351 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 359 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 362 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 365 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 370 | 一般代码规范 | **Medium** | Unused variable 'node_id' (unused-variable) |
| 374 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 375 | 一般代码规范 | **Low** | Unnecessary "elif" after "break", remove the leading "el" from "elif" (no-else-break) |
| 387 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 388 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 391 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 394 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 409 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 410 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 414 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 415 | 一般代码规范 | **Low** | Line too long (123/120) (line-too-long) |
| 415 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 416 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 419 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 421 | 一般代码规范 | **Low** | Import outside toplevel (io) (import-outside-toplevel) |
| 429 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 430 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 439 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 441 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 442 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise Exception(f'Result processing failed: {e}') from e' (raise-missing-from) |
| 442 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 446 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 448 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 449 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 458 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 459 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 460 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 462 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 463 | 一般代码规范 | **Low** | Line too long (127/120) (line-too-long) |
| 463 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 470 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 479 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 480 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 482 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 483 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 484 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 485 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 489 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 493 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 496 | 一般代码规范 | **Medium** | Attribute 'tasks' defined outside __init__ (attribute-defined-outside-init) |
| 503 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 506 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 509 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 512 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 516 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 517 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 518 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 522 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 530 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 533 | 导入优化 | **Medium** | Reimport 'sys' (imported line 5) (reimported) |
| 533 | 一般代码规范 | **Low** | Imports from package sys are not grouped (ungrouped-imports) |
| 535 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 542 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `workers/comfy_agent4/comfy_client.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "logging" should be placed before third party import "httpx" (wrong-import-order) |
| 3 | 导入优化 | **Low** | standard import "typing.Dict" should be placed before third party import "httpx" (wrong-import-order) |
| 7 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 12 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 16 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 17 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 29 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 33 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 44 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 58 | 一般代码规范 | **Medium** | Redefining built-in 'type' (redefined-builtin) |
| 63 | 一般代码规范 | **Low** | Import outside toplevel (asyncio) (import-outside-toplevel) |
| 65 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 72 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 74 | 一般代码规范 | **Low** | Line too long (140/120) (line-too-long) |
| 74 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 77 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 79 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 81 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |


### 📄 `workers/comfy_agent4/workflow_patcher.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 8 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 8 | 代码坏味道 | **Medium** | 高复杂度代码块 (class `WorkflowPatcher`): Cyclomatic Complexity = 18 |
| 13 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 20 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 26 | 一般代码规范 | **Low** | Consider using enumerate instead of iterating with range and len (consider-using-enumerate) |
| 30 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 30 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `load_workflow`): Cyclomatic Complexity = 14 |
| 51 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 54 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 56 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 60 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 62 | 一般代码规范 | **Low** | Line too long (133/120) (line-too-long) |
| 62 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 65 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 65 | 代码坏味道 | **Low** | Too many local variables (16/15) (too-many-locals) |
| 65 | 代码坏味道 | **Low** | Too many branches (30/12) (too-many-branches) |
| 65 | 代码坏味道 | **Low** | Too many statements (60/50) (too-many-statements) |
| 65 | 代码坏味道 | **High** | 高复杂度代码块 (method `patch_workflow`): Cyclomatic Complexity = 39 |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 71 | 一般代码规范 | **Low** | Import outside toplevel (random) (import-outside-toplevel) |
| 75 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 78 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 81 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 94 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 97 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 102 | 一般代码规范 | **Low** | "str(lora_name).strip() != ''" can be simplified to "str(lora_name).strip()", if it is strictly a string, as an empty string is falsey (use-implicit-booleaness-not-comparison-to-string) |
| 116 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 126 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 148 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 156 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 159 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 159 | 代码坏味道 | **Low** | Too many branches (23/12) (too-many-branches) |
| 159 | 代码坏味道 | **High** | 高复杂度代码块 (method `heuristic_patch`): Cyclomatic Complexity = 40 |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 167 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 168 | 一般代码规范 | **Low** | Line too long (124/120) (line-too-long) |
| 176 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 178 | 一般代码规范 | **Low** | Line too long (153/120) (line-too-long) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 189 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 193 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 199 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 202 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 205 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `workers/comfy_agent4/workflows/LTX 2.3 I2V.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 50 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "lora": "ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors", |


### 📄 `workers/comfy_agent4/workflows/Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 551 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "text": "<lora:Mystic-XXX-ZIT-V5:0.10>", |
| 555 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "name": "Mystic-XXX-ZIT-V5", |


### 📄 `workers/comfy_agent5/actual_prompt.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 32 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "lora": "ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors", |


### 📄 `workers/comfy_agent5/agent_main.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 6 | 一般代码规范 | **High** | Unable to import 'asgi_correlation_id' (import-error) |
| 8 | 一般代码规范 | **High** | Unable to import 'websockets' (import-error) |
| 11 | 导入优化 | **Low** | standard import "typing.Dict" should be placed before third party imports "asgi_correlation_id.correlation_id", "httpx", "websockets", "minio.Minio", "dotenv.load_dotenv" (wrong-import-order) |
| 13 | 一般代码规范 | **High** | Unable to import 'comfy_client' (import-error) |
| 14 | 一般代码规范 | **High** | Unable to import 'workflow_patcher' (import-error) |
| 25 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 25 | 一般代码规范 | **Low** | Too few public methods (1/2) (too-few-public-methods) |
| 31 | 一般代码规范 | **Low** | Constant name "log_format" doesn't conform to UPPER_CASE naming style (invalid-name) |
| 59 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 59 | 架构问题 | **Low** | Too many instance attributes (11/7) (too-many-instance-attributes) |
| 64 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 78 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 79 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 89 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 102 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 103 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 105 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 106 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 111 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 120 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 121 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 123 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 130 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 131 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 133 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 133 | 代码坏味道 | **Low** | Too many local variables (23/15) (too-many-locals) |
| 133 | 代码坏味道 | **Low** | Too many branches (21/12) (too-many-branches) |
| 133 | 代码坏味道 | **Low** | Too many statements (70/50) (too-many-statements) |
| 133 | 代码坏味道 | **High** | 高复杂度代码块 (method `ws_listener_loop`): Cyclomatic Complexity = 24 |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 140 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 151 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 152 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 155 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 158 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 162 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 169 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 172 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 179 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 183 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 187 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 189 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 191 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 207 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 214 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 217 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 218 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 219 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 222 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 224 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 225 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 228 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 232 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 233 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 236 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 238 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 239 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 247 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 248 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 251 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 258 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 259 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 262 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 262 | 代码坏味道 | **Low** | Too many local variables (39/15) (too-many-locals) |
| 262 | 代码坏味道 | **Low** | Too many branches (38/12) (too-many-branches) |
| 262 | 代码坏味道 | **Low** | Too many statements (138/50) (too-many-statements) |
| 262 | 代码坏味道 | **High** | 高复杂度代码块 (method `process_task`): Cyclomatic Complexity = 43 |
| 266 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 271 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 274 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 279 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 280 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 285 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 290 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 299 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 304 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 305 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 306 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 310 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 311 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 350 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 351 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 359 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 362 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 365 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 370 | 一般代码规范 | **Medium** | Unused variable 'node_id' (unused-variable) |
| 374 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 375 | 一般代码规范 | **Low** | Unnecessary "elif" after "break", remove the leading "el" from "elif" (no-else-break) |
| 387 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 388 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 391 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 394 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 409 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 410 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 414 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 415 | 一般代码规范 | **Low** | Line too long (123/120) (line-too-long) |
| 415 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 416 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 419 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 421 | 一般代码规范 | **Low** | Import outside toplevel (io) (import-outside-toplevel) |
| 429 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 430 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 439 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 441 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 442 | 一般代码规范 | **Medium** | Consider explicitly re-raising using 'raise Exception(f'Result processing failed: {e}') from e' (raise-missing-from) |
| 442 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 446 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 448 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 449 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 458 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 459 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 460 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 462 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 463 | 一般代码规范 | **Low** | Line too long (127/120) (line-too-long) |
| 463 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 470 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 479 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 480 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 482 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 483 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 484 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 485 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 489 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 493 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 496 | 一般代码规范 | **Medium** | Attribute 'tasks' defined outside __init__ (attribute-defined-outside-init) |
| 503 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 506 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 509 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 512 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 516 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 517 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 518 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 522 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 530 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 533 | 导入优化 | **Medium** | Reimport 'sys' (imported line 5) (reimported) |
| 533 | 一般代码规范 | **Low** | Imports from package sys are not grouped (ungrouped-imports) |
| 535 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 542 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `workers/comfy_agent5/comfy_client.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 2 | 导入优化 | **Low** | standard import "logging" should be placed before third party import "httpx" (wrong-import-order) |
| 3 | 导入优化 | **Low** | standard import "typing.Dict" should be placed before third party import "httpx" (wrong-import-order) |
| 7 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 12 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 16 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 17 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 29 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 33 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 44 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 58 | 一般代码规范 | **Medium** | Redefining built-in 'type' (redefined-builtin) |
| 63 | 一般代码规范 | **Low** | Import outside toplevel (asyncio) (import-outside-toplevel) |
| 65 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 72 | 一般代码规范 | **Medium** | Catching too general exception Exception (broad-exception-caught) |
| 74 | 一般代码规范 | **Low** | Line too long (140/120) (line-too-long) |
| 74 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 77 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 79 | 一般代码规范 | **Medium** | Raising too general exception: Exception (broad-exception-raised) |
| 81 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |


### 📄 `workers/comfy_agent5/workflow_patcher.py`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 一般代码规范 | **Low** | Missing module docstring (missing-module-docstring) |
| 8 | 一般代码规范 | **Low** | Missing class docstring (missing-class-docstring) |
| 8 | 代码坏味道 | **Medium** | 高复杂度代码块 (class `WorkflowPatcher`): Cyclomatic Complexity = 18 |
| 13 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 20 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 26 | 一般代码规范 | **Low** | Consider using enumerate instead of iterating with range and len (consider-using-enumerate) |
| 30 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 30 | 代码坏味道 | **Medium** | 高复杂度代码块 (method `load_workflow`): Cyclomatic Complexity = 14 |
| 51 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 54 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 56 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 60 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 62 | 一般代码规范 | **Low** | Line too long (133/120) (line-too-long) |
| 62 | 一般代码规范 | **Medium** | Use lazy % formatting in logging functions (logging-fstring-interpolation) |
| 65 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 65 | 代码坏味道 | **Low** | Too many local variables (16/15) (too-many-locals) |
| 65 | 代码坏味道 | **Low** | Too many branches (30/12) (too-many-branches) |
| 65 | 代码坏味道 | **Low** | Too many statements (60/50) (too-many-statements) |
| 65 | 代码坏味道 | **High** | 高复杂度代码块 (method `patch_workflow`): Cyclomatic Complexity = 39 |
| 68 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 71 | 一般代码规范 | **Low** | Import outside toplevel (random) (import-outside-toplevel) |
| 75 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 78 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 81 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 94 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 97 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 102 | 一般代码规范 | **Low** | "str(lora_name).strip() != ''" can be simplified to "str(lora_name).strip()", if it is strictly a string, as an empty string is falsey (use-implicit-booleaness-not-comparison-to-string) |
| 116 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 126 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 136 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 148 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 156 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 159 | 一般代码规范 | **Low** | Missing function or method docstring (missing-function-docstring) |
| 159 | 代码坏味道 | **Low** | Too many branches (23/12) (too-many-branches) |
| 159 | 代码坏味道 | **High** | 高复杂度代码块 (method `heuristic_patch`): Cyclomatic Complexity = 40 |
| 164 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 167 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 168 | 一般代码规范 | **Low** | Line too long (124/120) (line-too-long) |
| 176 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 178 | 一般代码规范 | **Low** | Line too long (153/120) (line-too-long) |
| 185 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 189 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 193 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 196 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 199 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 202 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 205 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |
| 211 | 一般代码规范 | **Low** | Trailing whitespace (trailing-whitespace) |


### 📄 `workers/comfy_agent5/workflows/LTX 2.3 I2V.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 50 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "lora": "ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors", |


### 📄 `workers/comfy_agent5/workflows/Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json`
| 行号 | 问题类型 | 严重程度 | 具体描述 |
| --- | --- | --- | --- |
| 551 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "text": "<lora:Mystic-XXX-ZIT-V5:0.10>", |
| 555 | 注释清理 | **Low** | 遗留注释 (TODO/FIXME/XXX): "name": "Mystic-XXX-ZIT-V5", |

