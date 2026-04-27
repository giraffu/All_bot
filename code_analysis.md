# 代码全面静态分析与质量评估报告

## 1. 核心指标统计

- **代码重复率 (估计)**: 26.48%
- **死代码比例 (估计)**: 0.24%
- **平均圈复杂度 (Cyclomatic Complexity)**: 4.61
- **发现问题总数**: 3764

## 2. 架构问题与重构建议

### 严重架构违规

- **\[Critical]** `src/core/auth_core.py:8` - 核心层绝对禁止引入任何与 Telegram Update 相关的特定平台对象

**重构建议**：

1. **核心层隔离**：`src/core` 下的代码应使用内部统一的 `internal_user_id` 流转，将请求解析逻辑上移到 API 路由或 Bot Handler 层。
2. **依赖倒置**：如果核心层需要通知外部，请定义接口，由外部层实现并注入到核心层。

## 3. 按优先级对问题进行分类统计

| 优先级      | 问题数量 | 占比    |
| -------- | ---- | ----- |
| Critical | 1    | 0.0%  |
| High     | 80   | 2.1%  |
| Medium   | 876  | 23.3% |
| Low      | 2807 | 74.6% |

## 4. 按文件结构的问题详情

### 文件: `src/core/auth_core.py`

| 行号  | 问题分类                       | 严重程度     | 问题描述                                                                                |
| --- | -------------------------- | -------- | ----------------------------------------------------------------------------------- |
| 8   | 架构问题 - 违反分层原则              | Critical | 核心层绝对禁止引入任何与 Telegram Update 相关的特定平台对象                                              |
| 20  | 死代码检测 - Vulture死代码         | Medium   | unused class 'InsufficientPermissionError'                                          |
| 29  | 代码坏味道 - Pylint警告 (PLC0415) | Medium   | `import` should be at the top-level of a file                                       |
| 55  | 代码坏味道 - 函数返回点过多            | Medium   | Too many return statements (7 > 6)                                                  |
| 65  | 代码坏味道 - Pylint警告 (PLC0415) | Medium   | `import` should be at the top-level of a file                                       |
| 1   | 导入优化 - 未排序的导入              | Low      | Import block is un-sorted or un-formatted                                           |
| 31  | 代码坏味道 - 魔法值使用              | Low      | Magic value used in comparison, consider replacing `86400` with a constant variable |
| 36  | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 45  | 代码坏味道 - 警告 (W291)          | Low      | Trailing whitespace                                                                 |
| 46  | 代码坏味道 - 警告 (W291)          | Low      | Trailing whitespace                                                                 |
| 49  | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 52  | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 67  | 代码坏味道 - 魔法值使用              | Low      | Magic value used in comparison, consider replacing `86400` with a constant variable |
| 72  | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 82  | 代码坏味道 - 警告 (W291)          | Low      | Trailing whitespace                                                                 |
| 83  | 代码坏味道 - 警告 (W291)          | Low      | Trailing whitespace                                                                 |
| 86  | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 90  | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 93  | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 97  | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 116 | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 121 | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 129 | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 132 | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 137 | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 145 | 代码坏味道 - Ruff特有规则 (RUF059)  | Low      | Unpacked variable `is_new` is never used                                            |
| 146 | 代码坏味道 - 警告 (W291)          | Low      | Trailing whitespace                                                                 |
| 147 | 代码坏味道 - 警告 (W291)          | Low      | Trailing whitespace                                                                 |
| 150 | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |
| 152 | 代码坏味道 - 警告 (W293)          | Low      | Blank line contains whitespace                                                      |

### 文件: `backend/app/main.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                                                                                                   |
| --- | -------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 226 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 274 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 386 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 420 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 38  | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 53  | 死代码检测 - Vulture死代码         | Medium | unused function 'startup\_event'                                                                                                                                       |
| 56  | 作用域分析 - 使用global语句         | Medium | Using the global statement to update `minio_client` is discouraged                                                                                                     |
| 70  | 死代码检测 - Vulture死代码         | Medium | unused function 'shutdown\_event'                                                                                                                                      |
| 74  | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 79  | 死代码检测 - Vulture死代码         | Medium | unused function 'create\_img2img\_task'                                                                                                                                |
| 82  | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 91  | 死代码检测 - Vulture死代码         | Medium | unused function 'create\_img2img\_lora\_task'                                                                                                                          |
| 94  | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 103 | 死代码检测 - Vulture死代码         | Medium | unused function 'create\_face\_swap\_task'                                                                                                                             |
| 106 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 115 | 死代码检测 - Vulture死代码         | Medium | unused function 'create\_video\_insert\_task'                                                                                                                          |
| 118 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 127 | 死代码检测 - Vulture死代码         | Medium | unused function 'create\_video\_edit\_task'                                                                                                                            |
| 130 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 139 | 死代码检测 - Vulture死代码         | Medium | unused function 'create\_video\_lora\_task'                                                                                                                            |
| 142 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 153 | 死代码检测 - Vulture死代码         | Medium | unused function 'create\_face\_video\_task'                                                                                                                            |
| 156 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 165 | 死代码检测 - Vulture死代码         | Medium | unused function 'create\_i2i\_pro\_task'                                                                                                                               |
| 168 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 177 | 死代码检测 - Vulture死代码         | Medium | unused function 'create\_ltx\_video\_task'                                                                                                                             |
| 180 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 189 | 死代码检测 - Vulture死代码         | Medium | unused function 'create\_t2i\_pornmaster\_turbo\_task'                                                                                                                 |
| 190 | 代码坏味道 - 函数过于复杂             | Medium | `create_t2i_pornmaster_turbo_task` is too complex (17 > 10)                                                                                                            |
| 190 | 代码坏味道 - 语句过多               | Medium | Too many statements (64 > 50)                                                                                                                                          |
| 191 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Body` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable    |
| 194 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 253 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 284 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 292 | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_task\_status\_v1'                                                                                                                                |
| 295 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 328 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 352 | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_task\_image'                                                                                                                                     |
| 355 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 367 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 388 | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_task\_video'                                                                                                                                     |
| 391 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 401 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 422 | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_system\_workers'                                                                                                                                 |
| 424 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 434 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 55  | 代码坏味道 - Ruff特有规则 (RUF006)  | Low    | Store a reference to the return value of `asyncio.create_task`                                                                                                         |
| 57  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 83  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `token`                                                                                                                                      |
| ... | ...                        | ...    | *还有 46 个同文件问题未展示*                                                                                                                                                      |

### 文件: `cs_bot/skill_manager.py`

| 行号 | 问题分类                         | 严重程度   | 问题描述                                                                          |
| -- | ---------------------------- | ------ | ----------------------------------------------------------------------------- |
| 38 | 代码坏味道 - Python语法/逻辑错误 (F811) | High   | Redefinition of unused `inspect` from line 4: `inspect` redefined here        |
| 3  | 死代码检测 - 未使用的导入               | Medium | `importlib.util` imported but unused                                          |
| 4  | 死代码检测 - Vulture死代码           | Medium | unused import 'inspect'                                                       |
| 4  | 死代码检测 - 未使用的导入               | Medium | `inspect` imported but unused                                                 |
| 6  | 死代码检测 - 未使用的导入               | Medium | `langchain_core.tools.tool` imported but unused                               |
| 37 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                 |
| 38 | 死代码检测 - Vulture死代码           | Medium | unused import 'inspect'                                                       |
| 38 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                 |
| 38 | 死代码检测 - 未使用的导入               | Medium | `inspect` imported but unused                                                 |
| 1  | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                     |
| 17 | 代码坏味道 - Ruff特有规则 (RUF002)    | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 18 | 代码坏味道 - Ruff特有规则 (RUF002)    | Low    | Docstring contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)? |
| 18 | 代码坏味道 - Ruff特有规则 (RUF002)    | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 33 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                |
| 35 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 35 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 36 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 39 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                |
| 44 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                |
| 50 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                |
| 51 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 69 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |

### 文件: `src/api_client.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                                                                                 |
| --- | -------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 282 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 283 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 293 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 294 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 317 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 371 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 68  | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (7 > 5)                                                                                                    |
| 88  | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (7 > 5)                                                                                                    |
| 107 | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (8 > 5)                                                                                                    |
| 156 | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (7 > 5)                                                                                                    |
| 206 | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (6 > 5)                                                                                                    |
| 245 | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (7 > 5)                                                                                                    |
| 296 | 代码坏味道 - 函数过于复杂             | Medium | `listen_for_progress` is too complex (22 > 10)                                                                                                       |
| 296 | 代码坏味道 - 分支过多               | Medium | Too many branches (23 > 12)                                                                                                                          |
| 296 | 代码坏味道 - 语句过多               | Medium | Too many statements (82 > 50)                                                                                                                        |
| 315 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 321 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 322 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 323 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 2   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                            |
| 9   | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                  |
| 10  | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                  |
| 23  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                               |
| 23  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                            |
| 29  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 146 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 147 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                                                          |
| 177 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 281 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `404` with a constant variable                                                                    |
| 282 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?                                                     |
| 282 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?                                                   |
| 282 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                                                           |
| 292 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `404` with a constant variable                                                                    |
| 296 | 死代码检测 - 未使用的方法参数           | Low    | Unused method argument: `is_video`                                                                                                                   |
| 301 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 308 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 316 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `404` with a constant variable                                                                    |
| 321 | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                            |
| 324 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 333 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 341 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 344 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 355 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 366 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 380 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 386 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |

### 文件: `src/bot_test.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                              |
| --- | ---------------------------- | ------ | --------------------------------------------------------------------------------- |
| 28  | 代码坏味道 - Python语法/逻辑错误 (F811) | High   | Redefinition of unused `os` from line 15: `os` redefined here                     |
| 29  | 代码坏味道 - Python语法/逻辑错误 (F811) | High   | Redefinition of unused `logging` from line 14: `logging` redefined here           |
| 22  | 死代码检测 - Vulture死代码           | Medium | unused import 'socket'                                                            |
| 22  | 死代码检测 - 未使用的导入               | Medium | `socket` imported but unused                                                      |
| 23  | 死代码检测 - 未使用的导入               | Medium | `urllib.parse.urlparse` imported but unused                                       |
| 34  | 代码坏味道 - 参数过多                 | Medium | Too many arguments in function definition (6 > 5)                                 |
| 40  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 67  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 86  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 117 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 120 | 代码坏味道 - 语句过多                 | Medium | Too many statements (51 > 50)                                                     |
| 128 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 191 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 192 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 193 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 194 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 195 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 196 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 197 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 198 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 199 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 200 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                         |
| 37  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 53  | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `else` after `return` statement                                       |
| 59  | 代码坏味道 - 代码风格问题 (E402)        | Low    | Module level import not at top of file                                            |
| 59  | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                         |
| 60  | 代码坏味道 - 代码风格问题 (E402)        | Low    | Module level import not at top of file                                            |
| 61  | 代码坏味道 - 代码风格问题 (E402)        | Low    | Module level import not at top of file                                            |
| 62  | 代码坏味道 - 代码风格问题 (E402)        | Low    | Module level import not at top of file                                            |
| 76  | 死代码检测 - 未使用的函数参数             | Low    | Unused function argument: `context`                                               |
| 88  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 91  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 96  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 102 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 107 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 123 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 126 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 130 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 132 | 代码坏味道 - 代码不够简化 (SIM112)      | Low    | Use capitalized environment variable `BOT_TOKEN_TEST` instead of `BOT_TOKEN_test` |
| 133 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 135 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 143 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?       |
| 144 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?        |
| 145 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 153 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 168 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?        |
| 190 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 191 | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                         |
| 202 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |

### 文件: `src/core/task_core.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                                                                                 |
| --- | -------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 234 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 261 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 1   | 死代码检测 - 未使用的导入             | Medium | `typing.Tuple` imported but unused                                                                                                                   |
| 1   | 死代码检测 - 未使用的导入             | Medium | `typing.Optional` imported but unused                                                                                                                |
| 1   | 死代码检测 - 未使用的导入             | Medium | `typing.List` imported but unused                                                                                                                    |
| 20  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 30  | 死代码检测 - 未使用的导入             | Medium | `src.constants.TASK_COSTS` imported but unused                                                                                                       |
| 30  | 死代码检测 - 未使用的导入             | Medium | `src.constants.RESOLUTION_COST` imported but unused                                                                                                  |
| 30  | 死代码检测 - 未使用的导入             | Medium | `src.constants.DURATION_MULTIPLIER` imported but unused                                                                                              |
| 30  | 死代码检测 - 未使用的导入             | Medium | `src.constants.MODE_I2I_PRO` imported but unused                                                                                                     |
| 30  | 死代码检测 - 未使用的导入             | Medium | `src.constants.MODE_FACESWAP_STEP1` imported but unused                                                                                              |
| 30  | 死代码检测 - 未使用的导入             | Medium | `src.constants.LTX_RESOLUTION_COST` imported but unused                                                                                              |
| 30  | 死代码检测 - 未使用的导入             | Medium | `src.constants.LTX_DURATION_MULTIPLIER` imported but unused                                                                                          |
| 43  | 代码坏味道 - 函数过于复杂             | Medium | `monitor_task_and_release_lock` is too complex (12 > 10)                                                                                             |
| 43  | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (9 > 5)                                                                                                    |
| 43  | 代码坏味道 - 分支过多               | Medium | Too many branches (13 > 12)                                                                                                                          |
| 57  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 58  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 58  | 死代码检测 - 未使用的导入             | Medium | `src.database.core.AsyncSessionLocal` imported but unused                                                                                            |
| 59  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 59  | 死代码检测 - 未使用的导入             | Medium | `src.database.models.History` imported but unused                                                                                                    |
| 103 | 代码坏味道 - 函数过于复杂             | Medium | `process_and_submit_task` is too complex (24 > 10)                                                                                                   |
| 103 | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (9 > 5)                                                                                                    |
| 103 | 代码坏味道 - 分支过多               | Medium | Too many branches (25 > 12)                                                                                                                          |
| 103 | 代码坏味道 - 语句过多               | Medium | Too many statements (95 > 50)                                                                                                                        |
| 114 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 115 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 165 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 253 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                        |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                            |
| 18  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 24  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 29  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                               |
| 29  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                            |
| 30  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                               |
| 31  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                               |
| 32  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                               |
| 36  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 39  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 44  | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                  |
| 45  | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                  |
| 47  | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                  |
| 51  | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`                                                                                                                |
| 57  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                            |
| 60  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 63  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 90  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 96  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                       |
| 104 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                  |
| 106 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                  |
| ... | ...                        | ...    | *还有 40 个同文件问题未展示*                                                                                                                                    |

### 文件: `src/handlers/fsm/edit_image_fsm.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                                                  |
| --- | ---------------------------- | ------ | ----------------------------------------------------------------------------------------------------- |
| 96  | 代码坏味道 - Python语法/逻辑错误 (F541) | High   | f-string without any placeholders                                                                     |
| 161 | 代码坏味道 - Python语法/逻辑错误 (F541) | High   | f-string without any placeholders                                                                     |
| 164 | 代码坏味道 - Python语法/逻辑错误 (F541) | High   | f-string without any placeholders                                                                     |
| 4   | 死代码检测 - 未使用的导入               | Medium | `asyncio` imported but unused                                                                         |
| 6   | 死代码检测 - 未使用的导入               | Medium | `re` imported but unused                                                                              |
| 62  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                         |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                             |
| 34  | 代码坏味道 - 代码不够简化 (SIM116)      | Low    | Use a dictionary instead of consecutive `if` statements                                               |
| 36  | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `elif` after `return` statement                                                           |
| 45  | 死代码检测 - 未使用的函数参数             | Low    | Unused function argument: `user_id`                                                                   |
| 58  | 死代码检测 - 未使用的局部变量             | Low    | Local variable `user_id` is assigned to but never used                                                |
| 61  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                        |
| 64  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 64  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 64  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 64  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?      |
| 72  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 90  | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `else` after `return` statement                                                           |
| 96  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                            |
| 104 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                        |
| 107 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                        |
| 110 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                        |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 115 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                        |
| 123 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                        |
| 124 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                            |
| 135 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?      |
| 141 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?      |
| 151 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                        |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 157 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                            |
| 157 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 161 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?      |
| 161 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 161 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 161 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?    |
| 164 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?      |
| 164 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 164 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?    |
| 167 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                        |
| 168 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?     |
| 168 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?   |
| 168 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 172 | 代码坏味道 - Ruff特有规则 (RUF002)    | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 172 | 代码坏味道 - Ruff特有规则 (RUF002)    | Low    | Docstring contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 172 | 代码坏味道 - Ruff特有规则 (RUF002)    | Low    | Docstring contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 175 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                        |
| 177 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 180 | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `2` with a constant variable                       |
| 181 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| ... | ...                          | ...    | *还有 16 个同文件问题未展示*                                                                                     |

### 文件: `src/handlers/fsm/ltx_video_fsm.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                                             |
| --- | ---------------------------- | ------ | ------------------------------------------------------------------------------------------------ |
| 51  | 代码坏味道 - Python语法/逻辑错误 (F811) | High   | Redefinition of unused `is_maintenance_mode` from line 26: `is_maintenance_mode` redefined here  |
| 4   | 死代码检测 - 未使用的导入               | Medium | `asyncio` imported but unused                                                                    |
| 6   | 死代码检测 - 未使用的导入               | Medium | `re` imported but unused                                                                         |
| 19  | 死代码检测 - 未使用的导入               | Medium | `src.constants.TMP_DIR` imported but unused                                                      |
| 22  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MAIN_MENU_KEYBOARD` imported but unused                                           |
| 24  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_LTX_VIDEO` imported but unused                                               |
| 26  | 死代码检测 - 未使用的导入               | Medium | `src.utils.is_maintenance_mode` imported but unused                                              |
| 51  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 105 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 163 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                        |
| 31  | 死代码检测 - 未使用的函数参数             | Low    | Unused function argument: `user_id`                                                              |
| 45  | 代码坏味道 - 代码不够简化 (SIM105)      | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                            |
| 49  | 死代码检测 - 未使用的局部变量             | Low    | Local variable `user_id` is assigned to but never used                                           |
| 50  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 53  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 53  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 53  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 53  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 61  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 72  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 72  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 83  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 89  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 99  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 101 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 108 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 111 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 115 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 119 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 120 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 120 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 120 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 122 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 123 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 123 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 126 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 127 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 128 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 130 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 131 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 132 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 133 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 134 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 135 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 136 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 137 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 146 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| ... | ...                          | ...    | *还有 46 个同文件问题未展示*                                                                                |

### 文件: `src/handlers/payment_handler.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                            |
| --- | ---------------------------- | ------ | ------------------------------------------------------------------------------- |
| 198 | 代码坏味道 - Python语法/逻辑错误 (F541) | High   | f-string without any placeholders                                               |
| 23  | 代码坏味道 - 函数过于复杂               | Medium | `successful_payment_callback` is too complex (18 > 10)                          |
| 23  | 代码坏味道 - 函数返回点过多              | Medium | Too many return statements (7 > 6)                                              |
| 23  | 代码坏味道 - 分支过多                 | Medium | Too many branches (20 > 12)                                                     |
| 23  | 代码坏味道 - 语句过多                 | Medium | Too many statements (98 > 50)                                                   |
| 25  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                   |
| 26  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                   |
| 67  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                   |
| 75  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                   |
| 141 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                   |
| 165 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                   |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                       |
| 13  | 死代码检测 - 未使用的函数参数             | Low    | Unused function argument: `context`                                             |
| 20  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?      |
| 23  | 死代码检测 - 未使用的函数参数             | Low    | Unused function argument: `context`                                             |
| 25  | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                       |
| 27  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 31  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 33  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 36  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 38  | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `3` with a constant variable |
| 40  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 47  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 53  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 57  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 61  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?      |
| 65  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 70  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 74  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 77  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 84  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 98  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 101 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 103 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?     |
| 111 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?     |
| 115 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 116 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?     |
| 120 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?     |
| 120 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?     |
| 123 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 126 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 127 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?     |
| 134 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 139 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 143 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 146 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 152 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 163 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| 164 | 死代码检测 - 注释掉的代码               | Low    | Found commented-out code                                                        |
| 176 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                  |
| ... | ...                          | ...    | *还有 15 个同文件问题未展示*                                                               |

### 文件: `src/services/payment_fulfillment_service.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                                                |
| --- | ---------------------------- | ------ | --------------------------------------------------------------------------------------------------- |
| 152 | 代码坏味道 - Python语法/逻辑错误 (F541) | High   | f-string without any placeholders                                                                   |
| 3   | 死代码检测 - 未使用的导入               | Medium | `json` imported but unused                                                                          |
| 7   | 死代码检测 - 未使用的导入               | Medium | `sqlalchemy.update` imported but unused                                                             |
| 14  | 代码坏味道 - 函数过于复杂               | Medium | `fulfill_order` is too complex (16 > 10)                                                            |
| 14  | 代码坏味道 - 函数返回点过多              | Medium | Too many return statements (7 > 6)                                                                  |
| 14  | 代码坏味道 - 分支过多                 | Medium | Too many branches (18 > 12)                                                                         |
| 14  | 代码坏味道 - 语句过多                 | Medium | Too many statements (80 > 50)                                                                       |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                           |
| 16  | 代码坏味道 - Ruff特有规则 (RUF002)    | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 26  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 30  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 42  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 49  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 57  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 70  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 73  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 82  | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 82  | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 88  | 死代码检测 - 注释掉的代码               | Low    | Found commented-out code                                                                            |
| 103 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 107 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 111 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 113 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 114 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 114 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 114 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 130 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 132 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 137 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?    |
| 138 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                          |
| 139 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                          |
| 142 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                          |
| 144 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                          |
| 146 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                          |
| 148 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                          |
| 149 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 151 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                          |
| 152 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                          |
| 152 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?    |
| 153 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 162 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |
| 164 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                      |

### 文件: `src/services/redis_client.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                          |
| --- | -------------------------- | ------ | ----------------------------------------------------------------------------- |
| 134 | 代码坏味道 - 常见Bug风险 (B905)     | High   | `zip()` without an explicit `strict=` parameter                               |
| 74  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                 |
| 90  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                 |
| 106 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                 |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                     |
| 11  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                |
| 48  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 51  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 73  | 代码坏味道 - Ruff特有规则 (RUF002)  | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 80  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 87  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                |
| 111 | 代码坏味道 - 代码不够简化 (SIM103)    | Low    | Return the condition `not (val and int(val) >= limit)` directly               |
| 116 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?   |
| 116 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 126 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                |
| 132 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                |
| 138 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                |

### 文件: `src/services/task_service.py`

| 行号   | 问题分类                         | 严重程度   | 问题描述                                                         |
| ---- | ---------------------------- | ------ | ------------------------------------------------------------ |
| 1055 | 代码坏味道 - Python语法/逻辑错误 (F541) | High   | f-string without any placeholders                            |
| 31   | 死代码检测 - 未使用的导入               | Medium | `src.constants.MAX_CONCURRENT_TASKS` imported but unused     |
| 52   | 死代码检测 - 未使用的导入               | Medium | `src.services.redis_client.redis_client` imported but unused |
| 58   | 代码坏味道 - 函数过于复杂               | Medium | `process_ltx_video_task` is too complex (11 > 10)            |
| 58   | 代码坏味道 - 参数过多                 | Medium | Too many arguments in function definition (6 > 5)            |
| 58   | 代码坏味道 - 分支过多                 | Medium | Too many branches (13 > 12)                                  |
| 58   | 代码坏味道 - 语句过多                 | Medium | Too many statements (66 > 50)                                |
| 66   | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 67   | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 84   | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 123  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 197  | 代码坏味道 - 函数过于复杂               | Medium | `process_face_video_task` is too complex (11 > 10)           |
| 197  | 代码坏味道 - 参数过多                 | Medium | Too many arguments in function definition (11 > 5)           |
| 197  | 代码坏味道 - 分支过多                 | Medium | Too many branches (13 > 12)                                  |
| 197  | 代码坏味道 - 语句过多                 | Medium | Too many statements (51 > 50)                                |
| 210  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 211  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 212  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 323  | 代码坏味道 - 函数过于复杂               | Medium | `process_generation_task` is too complex (26 > 10)           |
| 323  | 代码坏味道 - 参数过多                 | Medium | Too many arguments in function definition (17 > 5)           |
| 323  | 代码坏味道 - 分支过多                 | Medium | Too many branches (31 > 12)                                  |
| 323  | 代码坏味道 - 语句过多                 | Medium | Too many statements (103 > 50)                               |
| 343  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 344  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 345  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 346  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 346  | 死代码检测 - 未使用的导入               | Medium | `src.constants.DURATION_FRAMES` imported but unused          |
| 361  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 534  | 代码坏味道 - 函数过于复杂               | Medium | `_process_video_task_template` is too complex (17 > 10)      |
| 534  | 代码坏味道 - 参数过多                 | Medium | Too many arguments in function definition (8 > 5)            |
| 534  | 代码坏味道 - 分支过多                 | Medium | Too many branches (22 > 12)                                  |
| 534  | 代码坏味道 - 语句过多                 | Medium | Too many statements (90 > 50)                                |
| 547  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 548  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 565  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 633  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 812  | 代码坏味道 - 函数过于复杂               | Medium | `process_custom_video_task` is too complex (15 > 10)         |
| 812  | 代码坏味道 - 分支过多                 | Medium | Too many branches (18 > 12)                                  |
| 812  | 代码坏味道 - 语句过多                 | Medium | Too many statements (72 > 50)                                |
| 819  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 820  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 840  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 882  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 963  | 代码坏味道 - 参数过多                 | Medium | Too many arguments in function definition (7 > 5)            |
| 963  | 代码坏味道 - 语句过多                 | Medium | Too many statements (60 > 50)                                |
| 973  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 974  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 975  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 1000 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| 1001 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                |
| ...  | ...                          | ...    | *还有 128 个同文件问题未展示*                                           |

### 文件: `src/web_api/dependencies.py`

| 行号 | 问题分类                       | 严重程度   | 问题描述                                                                                                                                                                   |
| -- | -------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 51 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 31 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 61 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 1  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 19 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 23 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 39 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 43 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 47 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 56 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 59 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 65 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 68 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 71 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 75 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                                                                                             |
| 77 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |

### 文件: `src/web_api/routers/auth.py`

| 行号 | 问题分类                      | 严重程度   | 问题描述                                                                                                                                                 |
| -- | ------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 59 | 代码坏味道 - 常见Bug风险 (B904)    | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 64 | 代码坏味道 - 常见Bug风险 (B904)    | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 2  | 死代码检测 - 未使用的导入            | Medium | `typing.Optional` imported but unused                                                                                                                |
| 4  | 死代码检测 - 未使用的导入            | Medium | `fastapi.responses.JSONResponse` imported but unused                                                                                                 |
| 7  | 死代码检测 - 未使用的导入            | Medium | `src.web_api.schemas.auth_schema.Token` imported but unused                                                                                          |
| 14 | 死代码检测 - Vulture死代码        | Medium | unused function 'login\_telegram'                                                                                                                    |
| 69 | 死代码检测 - Vulture死代码        | Medium | unused function 'default\_login\_form'                                                                                                               |
| 1  | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                                                                                            |
| 22 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                                                                       |
| 24 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                                                                       |
| 29 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                                                                           |
| 29 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                                                           |
| 31 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                                                                       |
| 35 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                                                                       |
| 52 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                                                                       |

### 文件: `src/web_api/routers/gallery.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                                                                                                   |
| --- | -------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 476 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 557 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 562 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 15  | 死代码检测 - 未使用的导入             | Medium | `src.services.redis_client.redis_client` imported but unused                                                                                                           |
| 18  | 死代码检测 - 未使用的导入             | Medium | `os` imported but unused                                                                                                                                               |
| 20  | 死代码检测 - 未使用的导入             | Medium | `src.services.storage.storage` imported but unused                                                                                                                     |
| 52  | 代码坏味道 - Pylint警告 (PLC0207) | Medium | String is split more times than necessary                                                                                                                              |
| 60  | 死代码检测 - Vulture死代码         | Medium | unused function 'generate\_thumbnail\_url'                                                                                                                             |
| 65  | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_gallery\_config'                                                                                                                                 |
| 80  | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_gallery\_posts'                                                                                                                                  |
| 81  | 代码坏味道 - 函数过于复杂             | Medium | `get_gallery_posts` is too complex (16 > 10)                                                                                                                           |
| 81  | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (8 > 5)                                                                                                                      |
| 81  | 代码坏味道 - 分支过多               | Medium | Too many branches (16 > 12)                                                                                                                                            |
| 81  | 代码坏味道 - 语句过多               | Medium | Too many statements (59 > 50)                                                                                                                                          |
| 89  | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 109 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 129 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 206 | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_my\_gallery\_posts'                                                                                                                              |
| 210 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 218 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 293 | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_my\_favorite\_posts'                                                                                                                             |
| 298 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 316 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 391 | 死代码检测 - Vulture死代码         | Medium | unused function 'update\_post\_status'                                                                                                                                 |
| 395 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 408 | 死代码检测 - Vulture死代码         | Medium | unused function 'delete\_post'                                                                                                                                         |
| 411 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 413 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 439 | 死代码检测 - Vulture死代码         | Medium | unused function 'interact\_with\_post'                                                                                                                                 |
| 443 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 479 | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_apply\_context'                                                                                                                                  |
| 482 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 547 | 死代码检测 - Vulture死代码         | Medium | unused function 'submit\_to\_gallery'                                                                                                                                  |
| 551 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 14  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                                                 |
| 14  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 15  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                                                 |
| 16  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                                                 |
| 17  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                                                 |
| 18  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                                                 |
| 19  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                                                 |
| 20  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                                                 |
| 38  | 代码坏味道 - 代码风格问题 (E402)      | Low    | Module level import not at top of file                                                                                                                                 |
| 38  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 48  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 60  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `media_type`                                                                                                                                 |
| 62  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                                                                            |
| 92  | 代码坏味道 - 代码风格问题 (E712)      | Low    | Avoid equality comparisons to `True`; use `GalleryPost.is_active:` for truth checks                                                                                    |
| 93  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| ... | ...                        | ...    | *还有 65 个同文件问题未展示*                                                                                                                                                      |

### 文件: `src/web_api/routers/storage.py`

| 行号 | 问题分类                       | 严重程度   | 问题描述                                                                                                                                                                   |
| -- | -------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 54 | 代码坏味道 - 常见Bug风险 (B904)     | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 3  | 死代码检测 - 未使用的导入             | Medium | `fastapi.status` imported but unused                                                                                                                                   |
| 4  | 死代码检测 - 未使用的导入             | Medium | `typing.Optional` imported but unused                                                                                                                                  |
| 15 | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_presigned\_upload\_url'                                                                                                                          |
| 19 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 29 | 代码坏味道 - Pylint警告 (PLC0207) | Medium | String is split more times than necessary                                                                                                                              |
| 1  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 27 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 32 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 33 | 死代码检测 - 注释掉的代码             | Low    | Found commented-out code                                                                                                                                               |
| 35 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 38 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                                    |
| 39 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                                    |
| 43 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 46 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |

### 文件: `src/web_api/routers/tasks.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                                                                                                                   |
| --- | ---------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 54  | 代码坏味道 - 常见Bug风险 (B904)       | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 56  | 代码坏味道 - 常见Bug风险 (B904)       | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 58  | 代码坏味道 - 常见Bug风险 (B904)       | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 61  | 代码坏味道 - 常见Bug风险 (B904)       | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling                   |
| 70  | 代码坏味道 - Python语法/逻辑错误 (F811) | High   | Redefinition of unused `httpx` from line 4: `httpx` redefined here                                                                                                     |
| 4   | 死代码检测 - 未使用的导入               | Medium | `httpx` imported but unused                                                                                                                                            |
| 5   | 死代码检测 - 未使用的导入               | Medium | `typing.AsyncGenerator` imported but unused                                                                                                                            |
| 6   | 死代码检测 - 未使用的导入               | Medium | `fastapi.status` imported but unused                                                                                                                                   |
| 6   | 死代码检测 - 未使用的导入               | Medium | `fastapi.Request` imported but unused                                                                                                                                  |
| 21  | 死代码检测 - Vulture死代码           | Medium | unused function 'create\_generation\_task'                                                                                                                             |
| 24  | 作用域分析 - 默认参数中调用函数            | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 63  | 死代码检测 - Vulture死代码           | Medium | unused function 'task\_status\_stream'                                                                                                                                 |
| 64  | 代码坏味道 - 函数过于复杂               | Medium | `task_status_stream` is too complex (33 > 10)                                                                                                                          |
| 64  | 代码坏味道 - 语句过多                 | Medium | Too many statements (123 > 50)                                                                                                                                         |
| 64  | 作用域分析 - 默认参数中调用函数            | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 70  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 71  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 83  | 代码坏味道 - 函数过于复杂               | Medium | `event_generator` is too complex (29 > 10)                                                                                                                             |
| 83  | 代码坏味道 - 分支过多                 | Medium | Too many branches (29 > 12)                                                                                                                                            |
| 83  | 代码坏味道 - 语句过多                 | Medium | Too many statements (112 > 50)                                                                                                                                         |
| 111 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 112 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 113 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 158 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 159 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 160 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 211 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 212 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 213 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 31  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 35  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 44  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 70  | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 77  | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `200` with a constant variable                                                                                      |
| 87  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 94  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 98  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 110 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 111 | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 114 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 123 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 129 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 135 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 137 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 144 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 149 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 156 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| 158 | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 161 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                                         |
| ... | ...                          | ...    | *还有 12 个同文件问题未展示*                                                                                                                                                      |

### 文件: `workers/comfy_agent/agent_main.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                                                                                                 |
| --- | ---------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 380 | 代码坏味道 - 常见Bug风险 (B007)       | High   | Loop control variable `node_id` not used within loop body                                                                                            |
| 424 | 代码坏味道 - 常见Bug风险 (B007)       | High   | Loop control variable `node_id` not used within loop body                                                                                            |
| 473 | 代码坏味道 - 常见Bug风险 (B904)       | High   | Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| 143 | 代码坏味道 - 函数过于复杂               | Medium | `ws_listener_loop` is too complex (22 > 10)                                                                                                          |
| 143 | 代码坏味道 - 分支过多                 | Medium | Too many branches (21 > 12)                                                                                                                          |
| 143 | 代码坏味道 - 语句过多                 | Medium | Too many statements (71 > 50)                                                                                                                        |
| 246 | 死代码检测 - Vulture死代码           | Medium | unused method 'upload\_result\_to\_minio'                                                                                                            |
| 272 | 代码坏味道 - 函数过于复杂               | Medium | `process_task` is too complex (44 > 10)                                                                                                              |
| 272 | 代码坏味道 - 分支过多                 | Medium | Too many branches (42 > 12)                                                                                                                          |
| 272 | 代码坏味道 - 语句过多                 | Medium | Too many statements (154 > 50)                                                                                                                       |
| 346 | 性能问题 - 使用列表推导代替for循环         | Medium | Use a list comprehension to create a transformed list                                                                                                |
| 380 | 性能问题 - 性能建议 (PERF102)        | Medium | When using only the values of a dict use the `values()` method                                                                                       |
| 424 | 性能问题 - 性能建议 (PERF102)        | Medium | When using only the values of a dict use the `values()` method                                                                                       |
| 452 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                                                                        |
| 490 | 性能问题 - 性能建议 (PERF203)        | Medium | `try`-`except` within a loop incurs performance overhead                                                                                             |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                                                                            |
| 74  | 代码坏味道 - 警告 (W291)            | Low    | Trailing whitespace                                                                                                                                  |
| 78  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 146 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 165 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 168 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 172 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 174 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 182 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 189 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 195 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 199 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 206 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 217 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 221 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 227 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 235 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 238 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 242 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 249 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 255 | 代码重复 - 冗余代码 (PIE810)         | Low    | Call `endswith` once with a `tuple`                                                                                                                  |
| 257 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 264 | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `200` with a constant variable                                                                    |
| 276 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 281 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 284 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 285 | 代码坏味道 - 代码不够简化 (SIM108)      | Low    | Use ternary operator `params = json.loads(params_str) if isinstance(params_str, str) else params_str` instead of `if`-`else`-block                   |
| 289 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 295 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 335 | 代码坏味道 - Ruff特有规则 (RUF019)    | Low    | Unnecessary key check before dictionary access                                                                                                       |
| 337 | 代码坏味道 - Ruff特有规则 (RUF019)    | Low    | Unnecessary key check before dictionary access                                                                                                       |
| 345 | 代码坏味道 - Ruff特有规则 (RUF019)    | Low    | Unnecessary key check before dictionary access                                                                                                       |
| 361 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 384 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                                                                       |
| 389 | 代码坏味道 - Return语句不规范 (RET508) | Low    | Unnecessary `elif` after `break` statement                                                                                                           |
| ... | ...                          | ...    | *还有 34 个同文件问题未展示*                                                                                                                                    |

### 文件: `backend/app/config.py`

| 行号 | 问题分类               | 严重程度   | 问题描述                                      |
| -- | ------------------ | ------ | ----------------------------------------- |
| 15 | 死代码检测 - Vulture死代码 | Medium | unused variable 'minio\_bucket'           |
| 17 | 死代码检测 - Vulture死代码 | Medium | unused variable 'minio\_template\_bucket' |
| 22 | 死代码检测 - Vulture死代码 | Medium | unused variable 'minio\_input\_bucket'    |
| 25 | 死代码检测 - Vulture死代码 | Medium | unused variable 'env\_file'               |
| 26 | 死代码检测 - Vulture死代码 | Medium | unused variable 'extra'                   |
| 1  | 导入优化 - 未排序的导入      | Low    | Import block is un-sorted or un-formatted |
| 6  | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |
| 7  | 代码坏味道 - 警告 (W291)  | Low    | Trailing whitespace                       |
| 10 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |
| 19 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |
| 23 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |

### 文件: `backend/app/models.py`

| 行号  | 问题分类               | 严重程度   | 问题描述                                         |
| --- | ------------------ | ------ | -------------------------------------------- |
| 43  | 死代码检测 - Vulture死代码 | Medium | unused variable 'last\_seen'                 |
| 45  | 死代码检测 - Vulture死代码 | Medium | unused variable 'current\_task\_type'        |
| 46  | 死代码检测 - Vulture死代码 | Medium | unused variable 'current\_task\_progress'    |
| 47  | 死代码检测 - Vulture死代码 | Medium | unused variable 'current\_task\_created\_at' |
| 61  | 死代码检测 - Vulture死代码 | Medium | unused variable 'image'                      |
| 62  | 死代码检测 - Vulture死代码 | Medium | unused variable 'image2'                     |
| 66  | 死代码检测 - Vulture死代码 | Medium | unused variable 'num\_inference\_steps'      |
| 67  | 死代码检测 - Vulture死代码 | Medium | unused variable 'guidance\_scale'            |
| 73  | 死代码检测 - Vulture死代码 | Medium | unused variable 'image'                      |
| 74  | 死代码检测 - Vulture死代码 | Medium | unused variable 'image2'                     |
| 78  | 死代码检测 - Vulture死代码 | Medium | unused variable 'num\_inference\_steps'      |
| 79  | 死代码检测 - Vulture死代码 | Medium | unused variable 'guidance\_scale'            |
| 87  | 死代码检测 - Vulture死代码 | Medium | unused variable 'face\_image'                |
| 88  | 死代码检测 - Vulture死代码 | Medium | unused variable 'body\_image'                |
| 93  | 死代码检测 - Vulture死代码 | Medium | unused variable 'image'                      |
| 102 | 死代码检测 - Vulture死代码 | Medium | unused variable 'image'                      |
| 111 | 死代码检测 - Vulture死代码 | Medium | unused variable 'image'                      |
| 121 | 死代码检测 - Vulture死代码 | Medium | unused variable 'face\_image'                |
| 129 | 死代码检测 - Vulture死代码 | Medium | unused variable 'image'                      |
| 136 | 死代码检测 - Vulture死代码 | Medium | unused variable 'image'                      |
| 1   | 导入优化 - 未排序的导入      | Low    | Import block is un-sorted or un-formatted    |
| 141 | 代码坏味道 - 警告 (W292)  | Low    | No newline at end of file                    |

### 文件: `backend/app/queue_manager.py`

| 行号  | 问题分类                      | 严重程度   | 问题描述                                                                        |
| --- | ------------------------- | ------ | --------------------------------------------------------------------------- |
| 3   | 死代码检测 - 未使用的导入            | Medium | `uuid` imported but unused                                                  |
| 114 | 死代码检测 - Vulture死代码        | Medium | unused method 'get\_task\_by\_prompt\_id'                                   |
| 252 | 死代码检测 - Vulture死代码        | Medium | unused method 'clear\_running\_tasks'                                       |
| 1   | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                   |
| 20  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 22  | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 24  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 38  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 42  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 48  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 55  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 79  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 83  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 88  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 96  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 141 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 146 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 158 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 184 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 193 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 212 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 226 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 229 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 232 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 239 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 241 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 249 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |

### 文件: `backend/app/routers/agent.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                                                                                                   |
| --- | -------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 25  | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 46  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 56  | 死代码检测 - Vulture死代码         | Medium | unused function 'pop\_task'                                                                                                                                            |
| 59  | 死代码检测 - Vulture死代码         | Medium | unused variable 'authorized'                                                                                                                                           |
| 60  | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 78  | 死代码检测 - Vulture死代码         | Medium | unused function 'check\_task'                                                                                                                                          |
| 81  | 死代码检测 - Vulture死代码         | Medium | unused variable 'authorized'                                                                                                                                           |
| 82  | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 89  | 死代码检测 - Vulture死代码         | Medium | unused function 'update\_status'                                                                                                                                       |
| 92  | 死代码检测 - Vulture死代码         | Medium | unused variable 'authorized'                                                                                                                                           |
| 93  | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 110 | 死代码检测 - Vulture死代码         | Medium | unused variable 'authorized'                                                                                                                                           |
| 111 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 121 | 死代码检测 - Vulture死代码         | Medium | unused function 'task\_heartbeat'                                                                                                                                      |
| 124 | 死代码检测 - Vulture死代码         | Medium | unused variable 'authorized'                                                                                                                                           |
| 125 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 133 | 死代码检测 - Vulture死代码         | Medium | unused function 'heartbeat'                                                                                                                                            |
| 136 | 死代码检测 - Vulture死代码         | Medium | unused variable 'authorized'                                                                                                                                           |
| 137 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 7   | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                                    |
| 59  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `authorized`                                                                                                                                 |
| 65  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 69  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 72  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 75  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 81  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `authorized`                                                                                                                                 |
| 91  | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                                    |
| 92  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `authorized`                                                                                                                                 |
| 98  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 104 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 109 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                                                                                    |
| 110 | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `authorized`                                                                                                                                 |
| 124 | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `authorized`                                                                                                                                 |
| 136 | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `authorized`                                                                                                                                 |

### 文件: `backend/tests/test_t2i_pornmaster.py`

| 行号  | 问题分类               | 严重程度   | 问题描述                            |
| --- | ------------------ | ------ | ------------------------------- |
| 25  | 死代码检测 - Vulture死代码 | Medium | unused attribute 'side\_effect' |
| 35  | 死代码检测 - Vulture死代码 | Medium | unused attribute 'side\_effect' |
| 87  | 死代码检测 - Vulture死代码 | Medium | unused attribute 'side\_effect' |
| 110 | 死代码检测 - Vulture死代码 | Medium | unused attribute 'side\_effect' |
| 153 | 死代码检测 - Vulture死代码 | Medium | unused attribute 'side\_effect' |
| 190 | 死代码检测 - Vulture死代码 | Medium | unused attribute 'side\_effect' |

### 文件: `config.py`

| 行号 | 问题分类                    | 严重程度   | 问题描述                                                                              |
| -- | ----------------------- | ------ | --------------------------------------------------------------------------------- |
| 10 | 死代码检测 - Vulture死代码      | Medium | unused variable 'FILE\_BOT\_TOKEN'                                                |
| 13 | 死代码检测 - Vulture死代码      | Medium | unused variable 'TELETHON\_API\_ID'                                               |
| 14 | 死代码检测 - Vulture死代码      | Medium | unused variable 'TELETHON\_API\_HASH'                                             |
| 15 | 死代码检测 - Vulture死代码      | Medium | unused variable 'PHONE'                                                           |
| 16 | 死代码检测 - Vulture死代码      | Medium | unused variable 'PASSWORD'                                                        |
| 17 | 死代码检测 - Vulture死代码      | Medium | unused variable 'GROUP\_ID'                                                       |
| 44 | 死代码检测 - Vulture死代码      | Medium | unused variable 'IMGPROXY\_URL'                                                   |
| 73 | 死代码检测 - Vulture死代码      | Medium | unused variable 'LLM\_API\_URL'                                                   |
| 74 | 死代码检测 - Vulture死代码      | Medium | unused variable 'LLM\_MODEL\_NAME'                                                |
| 78 | 死代码检测 - Vulture死代码      | Medium | unused variable 'POLL\_TIMEOUT'                                                   |
| 88 | 死代码检测 - Vulture死代码      | Medium | unused variable 'DAILY\_LIMIT'                                                    |
| 1  | 死代码检测 - 注释掉的代码          | Low    | Found commented-out code                                                          |
| 2  | 导入优化 - 未排序的导入           | Low    | Import block is un-sorted or un-formatted                                         |
| 9  | 代码坏味道 - 代码不够简化 (SIM112) | Low    | Use capitalized environment variable `BOT_TOKEN_TEST` instead of `BOT_TOKEN_test` |

### 文件: `cs_bot/bot.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                                  |
| --- | -------------------------- | ------ | ----------------------------------------------------------------------------------------------------- |
| 42  | 死代码检测 - Vulture死代码         | Medium | unused variable 'out'                                                                                 |
| 49  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                         |
| 98  | 代码坏味道 - 函数过于复杂             | Medium | `handle_group_message` is too complex (19 > 10)                                                       |
| 98  | 代码坏味道 - 分支过多               | Medium | Too many branches (18 > 12)                                                                           |
| 98  | 代码坏味道 - 语句过多               | Medium | Too many statements (57 > 50)                                                                         |
| 215 | 代码坏味道 - 函数过于复杂             | Medium | `silent_logger_handler` is too complex (13 > 10)                                                      |
| 215 | 代码坏味道 - 分支过多               | Medium | Too many branches (13 > 12)                                                                           |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                             |
| 17  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                           |
| 18  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                           |
| 18  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 31  | 代码坏味道 - 代码不够简化 (SIM102)    | Low    | Use a single `if` statement instead of nested `if` statements                                         |
| 42  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `out`                                                                       |
| 42  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `custom_path`                                                               |
| 42  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `args`                                                                      |
| 42  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `kwargs`                                                                    |
| 43  | 代码坏味道 - Ruff特有规则 (RUF002)  | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 48  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 52  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                        |
| 53  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                           |
| 58  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                        |
| 60  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                        |
| 61  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 66  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                        |
| 83  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 90  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `context`                                                                   |
| 94  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?      |
| 94  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?      |
| 94  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?    |
| 94  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 96  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 96  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 96  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?      |
| 100 | 代码坏味道 - Ruff特有规则 (RUF002)  | Low    | Docstring contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 103 | 代码坏味道 - Ruff特有规则 (RUF002)  | Low    | Docstring contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 103 | 代码坏味道 - Ruff特有规则 (RUF002)  | Low    | Docstring contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 108 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                        |
| 109 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                           |
| 109 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 112 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                        |
| 114 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                           |
| 116 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                        |
| 121 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 121 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 121 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?     |
| 121 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?   |
| 128 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 128 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 135 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                           |
| 137 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                        |
| ... | ...                        | ...    | *还有 53 个同文件问题未展示*                                                                                     |

### 文件: `cs_bot/db.py`

| 行号 | 问题分类                       | 严重程度   | 问题描述                                              |
| -- | -------------------------- | ------ | ------------------------------------------------- |
| 32 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file     |
| 37 | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (8 > 5) |
| 1  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted         |
| 53 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                               |

### 文件: `cs_bot/skills/system_status_skill.py`

| 行号 | 问题分类                       | 严重程度   | 问题描述                                          |
| -- | -------------------------- | ------ | --------------------------------------------- |
| 6  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file |
| 1  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted     |

### 文件: `src/constants.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                           |
| --- | -------------------------- | ------ | ---------------------------------------------- |
| 90  | 死代码检测 - Vulture死代码         | Medium | unused variable 'VIDEO\_RESOLUTIONS'           |
| 171 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file  |
| 219 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file  |
| 175 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 179 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 181 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 188 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 196 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 199 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 206 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 212 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 215 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 218 | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `user_group`         |
| 218 | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `user_identity`      |
| 218 | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `current_resolution` |
| 223 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 225 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 234 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |
| 239 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                 |

### 文件: `src/core/billing_core.py`

| 行号 | 问题分类                       | 严重程度   | 问题描述                                                                                             |
| -- | -------------------------- | ------ | ------------------------------------------------------------------------------------------------ |
| 4  | 死代码检测 - 未使用的导入             | Medium | `src.database.core.AsyncSessionLocal` imported but unused                                        |
| 5  | 死代码检测 - 未使用的导入             | Medium | `src.database.models.User` imported but unused                                                   |
| 18 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 19 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 71 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 1  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                        |
| 24 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                      |
| 24 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                      |
| 28 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `200` with a constant variable                |
| 29 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 29 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 29 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 29 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 29 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 35 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 35 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 42 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`                                                            |
| 60 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 62 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`                                                            |

### 文件: `src/core/gallery_core.py`

| 行号  | 问题分类                      | 严重程度   | 问题描述                                                                                             |
| --- | ------------------------- | ------ | ------------------------------------------------------------------------------------------------ |
| 4   | 死代码检测 - 未使用的导入            | Medium | `asyncio` imported but unused                                                                    |
| 43  | 代码坏味道 - 函数过于复杂            | Medium | `process_submit_to_gallery` is too complex (13 > 10)                                             |
| 43  | 代码坏味道 - 分支过多              | Medium | Too many branches (13 > 12)                                                                      |
| 43  | 代码坏味道 - 语句过多              | Medium | Too many statements (54 > 50)                                                                    |
| 1   | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                                        |
| 48  | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 54  | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 60  | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 63  | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 63  | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 67  | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 67  | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 70  | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 103 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                   |
| 109 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                   |
| 118 | 代码坏味道 - 代码风格问题 (E713)     | Low    | Test for membership should be `not in`                                                           |
| 133 | 代码坏味道 - 警告 (W291)         | Low    | Trailing whitespace                                                                              |
| 134 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 134 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |

### 文件: `src/core/task_dispatcher.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                             |
| --- | ---------------------------- | ------ | -------------------------------------------------------------------------------- |
| 12  | 死代码检测 - Vulture死代码           | Medium | unused method 'build\_payload'                                                   |
| 35  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                    |
| 40  | 死代码检测 - Vulture死代码           | Medium | unused method 'build\_payload'                                                   |
| 51  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                    |
| 83  | 死代码检测 - Vulture死代码           | Medium | unused method 'build\_payload'                                                   |
| 124 | 死代码检测 - Vulture死代码           | Medium | unused method 'build\_payload'                                                   |
| 189 | 死代码检测 - Vulture死代码           | Medium | unused method 'build\_payload'                                                   |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                        |
| 11  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 15  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 19  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 23  | 代码重复 - 冗余代码 (PIE790)         | Low    | Unnecessary `pass` statement                                                     |
| 24  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 28  | 代码重复 - 冗余代码 (PIE790)         | Low    | Unnecessary `pass` statement                                                     |
| 33  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 37  | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `2` with a constant variable  |
| 39  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 42  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 45  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 48  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 60  | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `elif` after `return` statement                                      |
| 80  | 死代码检测 - 未使用的方法参数             | Low    | Unused method argument: `inputs`                                                 |
| 82  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 85  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 89  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 91  | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?      |
| 91  | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?      |
| 92  | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `2` with a constant variable  |
| 95  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 112 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 119 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 123 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 126 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 129 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 132 | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `2` with a constant variable  |
| 135 | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `elif` after `return` statement                                      |
| 138 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 141 | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `10` with a constant variable |
| 143 | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `8` with a constant variable  |
| 147 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 152 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 157 | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `elif` after `return` statement                                      |
| 165 | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `10` with a constant variable |
| 180 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 188 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 191 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 194 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 197 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 204 | 代码坏味道 - 代码风格问题 (E722)        | Low    | Do not use bare `except`                                                         |
| 206 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| ... | ...                          | ...    | *还有 7 个同文件问题未展示*                                                                 |

### 文件: `src/core/user_core.py`

| 行号 | 问题分类                      | 严重程度   | 问题描述                                                                                                  |
| -- | ------------------------- | ------ | ----------------------------------------------------------------------------------------------------- |
| 64 | 死代码检测 - Vulture死代码        | Medium | unused function 'get\_or\_create\_user\_by\_google'                                                   |
| 1  | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                                             |
| 10 | 代码坏味道 - Ruff特有规则 (RUF013) | Low    | PEP 484 prohibits implicit `Optional`                                                                 |
| 10 | 代码坏味道 - Ruff特有规则 (RUF013) | Low    | PEP 484 prohibits implicit `Optional`                                                                 |
| 11 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 11 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 19 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                        |
| 28 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                        |
| 32 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                        |
| 33 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 33 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 37 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                        |
| 39 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 45 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 45 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 59 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 64 | 代码坏味道 - Ruff特有规则 (RUF013) | Low    | PEP 484 prohibits implicit `Optional`                                                                 |
| 70 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                        |

### 文件: `src/core/user_facade.py`

| 行号 | 问题分类                       | 严重程度   | 问题描述                                                                               |
| -- | -------------------------- | ------ | ---------------------------------------------------------------------------------- |
| 2  | 死代码检测 - 未使用的导入             | Medium | `typing.Optional` imported but unused                                              |
| 67 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                      |
| 1  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                          |
| 21 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                     |
| 26 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                     |
| 29 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?         |
| 34 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `3` with a constant variable    |
| 35 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `10` with a constant variable   |
| 37 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?         |
| 43 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `10` with a constant variable   |
| 44 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `30` with a constant variable   |
| 45 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `100` with a constant variable  |
| 47 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?         |
| 53 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `100` with a constant variable  |
| 54 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `300` with a constant variable  |
| 55 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `1000` with a constant variable |
| 57 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?         |
| 63 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?         |
| 63 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?         |
| 78 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?         |
| 80 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?         |

### 文件: `src/database/core.py`

| 行号 | 问题分类                       | 严重程度   | 问题描述                                                                                               |
| -- | -------------------------- | ------ | -------------------------------------------------------------------------------------------------- |
| 5  | 死代码检测 - 未使用的导入             | Medium | `.models.Base` imported but unused                                                                 |
| 28 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 29 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 30 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 31 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 1  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                          |
| 13 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                |
| 28 | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                          |
| 32 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 38 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 40 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 48 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 54 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 62 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 65 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 65 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |

### 文件: `src/database/logger.py`

| 行号 | 问题分类               | 严重程度   | 问题描述                                      |
| -- | ------------------ | ------ | ----------------------------------------- |
| 21 | 死代码检测 - Vulture死代码 | Medium | unused function 'before\_cursor\_execute' |
| 25 | 死代码检测 - Vulture死代码 | Medium | unused function 'after\_cursor\_execute'  |
| 58 | 死代码检测 - Vulture死代码 | Medium | unused function 'handle\_error'           |
| 1  | 导入优化 - 未排序的导入      | Low    | Import block is un-sorted or un-formatted |
| 15 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |
| 22 | 死代码检测 - 未使用的函数参数   | Low    | Unused function argument: `conn`          |
| 22 | 死代码检测 - 未使用的函数参数   | Low    | Unused function argument: `cursor`        |
| 22 | 死代码检测 - 未使用的函数参数   | Low    | Unused function argument: `statement`     |
| 22 | 死代码检测 - 未使用的函数参数   | Low    | Unused function argument: `parameters`    |
| 26 | 死代码检测 - 未使用的函数参数   | Low    | Unused function argument: `conn`          |
| 28 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |
| 31 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |
| 38 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |
| 46 | 代码坏味道 - 警告 (W291)  | Low    | Trailing whitespace                       |
| 50 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |
| 63 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |
| 78 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |

### 文件: `src/database/models.py`

| 行号  | 问题分类                      | 严重程度   | 问题描述                                                                                                |
| --- | ------------------------- | ------ | --------------------------------------------------------------------------------------------------- |
| 39  | 作用域分析 - 类属性遮蔽内置名称         | Medium | Python builtin is shadowed by class attribute `id` from line 10                                     |
| 40  | 死代码检测 - Vulture死代码        | Medium | unused variable 'referrals\_made'                                                                   |
| 41  | 死代码检测 - Vulture死代码        | Medium | unused variable 'referred\_by'                                                                      |
| 131 | 死代码检测 - Vulture死代码        | Medium | unused variable 'original\_price'                                                                   |
| 136 | 死代码检测 - Vulture死代码        | Medium | unused variable 'updated\_at'                                                                       |
| 1   | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                                           |
| 11  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 28  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 67  | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 160 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 166 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 168 | 代码坏味道 - 警告 (W291)         | Low    | Trailing whitespace                                                                                 |
| 169 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 174 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 175 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 175 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 177 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |

### 文件: `src/handlers/callback_handler.py`

| 行号 | 问题分类                         | 严重程度   | 问题描述                                                                             |
| -- | ---------------------------- | ------ | -------------------------------------------------------------------------------- |
| 12 | 死代码检测 - Vulture死代码           | Medium | unused import 'billing\_callbacks'                                               |
| 12 | 死代码检测 - Vulture死代码           | Medium | unused import 'gallery\_callbacks'                                               |
| 12 | 死代码检测 - Vulture死代码           | Medium | unused import 'misc\_callbacks'                                                  |
| 12 | 死代码检测 - 未使用的导入               | Medium | `src.handlers.callbacks.billing_callbacks` imported but unused                   |
| 12 | 死代码检测 - 未使用的导入               | Medium | `src.handlers.callbacks.gallery_callbacks` imported but unused                   |
| 12 | 死代码检测 - 未使用的导入               | Medium | `src.handlers.callbacks.misc_callbacks` imported but unused                      |
| 1  | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                        |
| 11 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?      |
| 16 | 代码坏味道 - Return语句不规范 (RET503) | Low    | Missing explicit `return` at the end of function able to return non-`None` value |
| 23 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 26 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 27 | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?      |
| 31 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                   |
| 32 | 死代码检测 - 注释掉的代码               | Low    | Found commented-out code                                                         |
| 35 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?       |

### 文件: `src/handlers/callback_router.py`

| 行号 | 问题分类                      | 严重程度   | 问题描述                                                                        |
| -- | ------------------------- | ------ | --------------------------------------------------------------------------- |
| 18 | 作用域分析 - 使用global语句        | Medium | Using the global statement to update `SORTED_ROUTES` is discouraged         |
| 16 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                              |
| 17 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 17 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |

### 文件: `src/handlers/callbacks/billing_callbacks.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                   |
| --- | -------------------------- | ------ | -------------------------------------------------------------------------------------- |
| 15  | 死代码检测 - Vulture死代码         | Medium | unused function 'recharge\_stars\_menu\_callback'                                      |
| 26  | 性能问题 - 使用列表推导代替for循环       | Medium | Use `list.extend` to create a transformed list                                         |
| 35  | 死代码检测 - Vulture死代码         | Medium | unused function 'recharge\_stars\_credit\_menu\_callback'                              |
| 46  | 性能问题 - 使用列表推导代替for循环       | Medium | Use `list.extend` to create a transformed list                                         |
| 55  | 死代码检测 - Vulture死代码         | Medium | unused function 'recharge\_back\_callback'                                             |
| 74  | 死代码检测 - Vulture死代码         | Medium | unused function 'recharge\_rmb\_menu\_callback'                                        |
| 85  | 性能问题 - 使用列表推导代替for循环       | Medium | Use `list.extend` to create a transformed list                                         |
| 94  | 死代码检测 - Vulture死代码         | Medium | unused function 'recharge\_rmb\_credit\_menu\_callback'                                |
| 105 | 性能问题 - 使用列表推导代替for循环       | Medium | Use `list.extend` to create a transformed list                                         |
| 114 | 死代码检测 - Vulture死代码         | Medium | unused function 'select\_rmb\_plan\_callback'                                          |
| 133 | 死代码检测 - Vulture死代码         | Medium | unused function 'buy\_rmb\_plan\_callback'                                             |
| 225 | 死代码检测 - Vulture死代码         | Medium | unused function 'buy\_star\_plan\_callback'                                            |
| 227 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                          |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                              |
| 16  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `context`                                                    |
| 19  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 22  | 代码坏味道 - 代码风格问题 (E712)      | Low    | Avoid equality comparisons to `True`; use `MembershipPlan.is_active:` for truth checks |
| 27  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 30  | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                  |
| 36  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `context`                                                    |
| 39  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 42  | 代码坏味道 - 代码风格问题 (E712)      | Low    | Avoid equality comparisons to `True`; use `MembershipPlan.is_active:` for truth checks |
| 47  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 50  | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                  |
| 56  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `context`                                                    |
| 59  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 69  | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                  |
| 75  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `context`                                                    |
| 78  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 81  | 代码坏味道 - 代码风格问题 (E712)      | Low    | Avoid equality comparisons to `True`; use `MembershipPlan.is_active:` for truth checks |
| 86  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 89  | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                  |
| 95  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `context`                                                    |
| 98  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 101 | 代码坏味道 - 代码风格问题 (E712)      | Low    | Avoid equality comparisons to `True`; use `MembershipPlan.is_active:` for truth checks |
| 106 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 109 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                  |
| 115 | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `context`                                                    |
| 118 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 128 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                  |
| 134 | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `context`                                                    |
| 137 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 142 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 145 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 149 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 153 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 155 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                         |
| 156 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                  |
| 158 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?             |
| 158 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?             |
| ... | ...                        | ...    | *还有 25 个同文件问题未展示*                                                                      |

### 文件: `src/handlers/callbacks/gallery_callbacks.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                                             |
| --- | ---------------------------- | ------ | ------------------------------------------------------------------------------------------------ |
| 13  | 死代码检测 - 未使用的导入               | Medium | `src.database.models.User` imported but unused                                                   |
| 18  | 死代码检测 - 未使用的导入               | Medium | `src.utils.robust_edit_text` imported but unused                                                 |
| 22  | 死代码检测 - 未使用的导入               | Medium | `config.MINIO_TEMPLATE_BUCKET` imported but unused                                               |
| 28  | 死代码检测 - Vulture死代码           | Medium | unused function 'public\_share\_callback'                                                        |
| 29  | 代码坏味道 - 函数过于复杂               | Medium | `public_share_callback` is too complex (32 > 10)                                                 |
| 29  | 代码坏味道 - 函数返回点过多              | Medium | Too many return statements (11 > 6)                                                              |
| 29  | 代码坏味道 - 分支过多                 | Medium | Too many branches (32 > 12)                                                                      |
| 29  | 代码坏味道 - 语句过多                 | Medium | Too many statements (87 > 50)                                                                    |
| 204 | 死代码检测 - Vulture死代码           | Medium | unused function 'rate\_like\_callback'                                                           |
| 208 | 死代码检测 - Vulture死代码           | Medium | unused function 'rate\_dislike\_callback'                                                        |
| 251 | 死代码检测 - Vulture死代码           | Medium | unused function 'submit\_gallery\_callback'                                                      |
| 252 | 代码坏味道 - 函数过于复杂               | Medium | `submit_gallery_callback` is too complex (17 > 10)                                               |
| 252 | 代码坏味道 - 分支过多                 | Medium | Too many branches (18 > 12)                                                                      |
| 252 | 代码坏味道 - 语句过多                 | Medium | Too many statements (69 > 50)                                                                    |
| 258 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 356 | 死代码检测 - Vulture死代码           | Medium | unused function 'gallery\_catmenu\_callback'                                                     |
| 375 | 死代码检测 - Vulture死代码           | Medium | unused function 'gallery\_sort\_page\_callback'                                                  |
| 377 | 代码坏味道 - 函数过于复杂               | Medium | `gallery_sort_page_callback` is too complex (35 > 10)                                            |
| 377 | 代码坏味道 - 分支过多                 | Medium | Too many branches (42 > 12)                                                                      |
| 377 | 代码坏味道 - 语句过多                 | Medium | Too many statements (127 > 50)                                                                   |
| 446 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 447 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 466 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 557 | 死代码检测 - Vulture死代码           | Medium | unused function 'gallery\_like\_dislike\_callback'                                               |
| 559 | 代码坏味道 - 函数过于复杂               | Medium | `gallery_like_dislike_callback` is too complex (13 > 10)                                         |
| 559 | 代码坏味道 - 分支过多                 | Medium | Too many branches (15 > 12)                                                                      |
| 559 | 代码坏味道 - 语句过多                 | Medium | Too many statements (51 > 50)                                                                    |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                        |
| 18  | 代码坏味道 - 警告 (W291)            | Low    | Trailing whitespace                                                                              |
| 32  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 37  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 48  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 48  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 52  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 57  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 70  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 73  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `？` (FULLWIDTH QUESTION MARK). Did you mean `?` (QUESTION MARK)?       |
| 74  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 74  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 76  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 80  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 94  | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `elif` after `return` statement                                                      |
| 100 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 101 | 代码坏味道 - 代码不够简化 (SIM102)      | Low    | Use a single `if` statement instead of nested `if` statements                                    |
| 104 | 代码坏味道 - 代码不够简化 (SIM105)      | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                            |
| 134 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 139 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 145 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 149 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 154 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| ... | ...                          | ...    | *还有 108 个同文件问题未展示*                                                                               |

### 文件: `src/handlers/callbacks/misc_callbacks.py`

| 行号 | 问题分类                      | 严重程度   | 问题描述                                                                                               |
| -- | ------------------------- | ------ | -------------------------------------------------------------------------------------------------- |
| 20 | 死代码检测 - Vulture死代码        | Medium | unused function 'random\_faceswap\_again\_callback'                                                |
| 1  | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                                          |
| 23 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                     |
| 24 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                        |
| 26 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                     |
| 28 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 34 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 34 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 34 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 34 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 34 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 34 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 39 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 41 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                     |
| 54 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                     |
| 56 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 61 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                     |
| 63 | 代码坏味道 - 警告 (W291)         | Low    | Trailing whitespace                                                                                |
| 64 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                     |
| 74 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                     |
| 78 | 代码坏味道 - 警告 (W291)         | Low    | Trailing whitespace                                                                                |
| 85 | 代码坏味道 - Ruff特有规则 (RUF001) | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 85 | 代码坏味道 - Ruff特有规则 (RUF010) | Low    | Use explicit conversion flag                                                                       |

### 文件: `src/handlers/conversation_states.py`

| 行号 | 问题分类                      | 严重程度   | 问题描述                                                                          |
| -- | ------------------------- | ------ | ----------------------------------------------------------------------------- |
| 30 | 死代码检测 - Vulture死代码        | Medium | unused class 'Img2ImgLoraState'                                               |
| 50 | 死代码检测 - Vulture死代码        | Medium | unused class 'CommonState'                                                    |
| 1  | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                     |
| 51 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |

### 文件: `src/handlers/fsm/custom_video_fsm.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                               |
| --- | -------------------------- | ------ | -------------------------------------------------------------------------------------------------- |
| 4   | 死代码检测 - 未使用的导入             | Medium | `asyncio` imported but unused                                                                      |
| 6   | 死代码检测 - 未使用的导入             | Medium | `re` imported but unused                                                                           |
| 7   | 死代码检测 - 未使用的导入             | Medium | `telegram.InlineKeyboardMarkup` imported but unused                                                |
| 7   | 死代码检测 - 未使用的导入             | Medium | `telegram.InlineKeyboardButton` imported but unused                                                |
| 44  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 98  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 154 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                          |
| 24  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `user_id`                                                                |
| 38  | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 42  | 死代码检测 - 未使用的局部变量           | Low    | Local variable `user_id` is assigned to but never used                                             |
| 43  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 46  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 46  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 46  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 46  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 54  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 65  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 65  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 76  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 82  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 92  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 94  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 101 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 104 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 108 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 112 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 114 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 123 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 126 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 127 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 136 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 137 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 145 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 146 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 153 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 157 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 161 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 165 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 166 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 166 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| ... | ...                        | ...    | *还有 24 个同文件问题未展示*                                                                                  |

### 文件: `src/handlers/fsm/face_video_fsm.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                               |
| --- | -------------------------- | ------ | -------------------------------------------------------------------------------------------------- |
| 4   | 死代码检测 - 未使用的导入             | Medium | `asyncio` imported but unused                                                                      |
| 5   | 死代码检测 - 未使用的导入             | Medium | `re` imported but unused                                                                           |
| 56  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 199 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                          |
| 24  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `user_id`                                                                |
| 28  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 33  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 50  | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 54  | 死代码检测 - 未使用的局部变量           | Low    | Local variable `user_id` is assigned to but never used                                             |
| 55  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 58  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 58  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 58  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 58  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 67  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 79  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 79  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 79  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 96  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 96  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 102 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 112 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 116 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 118 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 123 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 136 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 142 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 150 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 153 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 155 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 155 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 172 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 203 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 203 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 203 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 203 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 203 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 209 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 210 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 222 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 222 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 245 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 250 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 260 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 262 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 262 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 263 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 272 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 272 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| ... | ...                        | ...    | *还有 3 个同文件问题未展示*                                                                                   |

### 文件: `src/handlers/fsm/faceswap_fsm.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                               |
| --- | -------------------------- | ------ | -------------------------------------------------------------------------------------------------- |
| 4   | 死代码检测 - 未使用的导入             | Medium | `asyncio` imported but unused                                                                      |
| 6   | 死代码检测 - 未使用的导入             | Medium | `re` imported but unused                                                                           |
| 7   | 死代码检测 - 未使用的导入             | Medium | `telegram.InlineKeyboardMarkup` imported but unused                                                |
| 7   | 死代码检测 - 未使用的导入             | Medium | `telegram.InlineKeyboardButton` imported but unused                                                |
| 46  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                          |
| 24  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `user_id`                                                                |
| 39  | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 45  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 48  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 48  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 48  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 48  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 56  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 66  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 66  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 66  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 80  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 86  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 96  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 98  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 103 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 103 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 103 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 114 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 120 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 134 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 136 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 145 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 145 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 176 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 176 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 185 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 185 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 185 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 185 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 188 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |

### 文件: `src/handlers/fsm/gallery_apply_fsm.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                             |
| --- | -------------------------- | ------ | ------------------------------------------------------------------------------------------------ |
| 7   | 死代码检测 - 未使用的导入             | Medium | `telegram.InlineKeyboardButton` imported but unused                                              |
| 7   | 死代码检测 - 未使用的导入             | Medium | `telegram.InlineKeyboardMarkup` imported but unused                                              |
| 21  | 死代码检测 - 未使用的导入             | Medium | `src.constants.MODE_FACE_VIDEO_STEP1` imported but unused                                        |
| 22  | 死代码检测 - 未使用的导入             | Medium | `src.constants.MODE_FACE_VIDEO_STEP2` imported but unused                                        |
| 23  | 死代码检测 - 未使用的导入             | Medium | `src.constants.MODE_FACESWAP_STEP1` imported but unused                                          |
| 46  | 代码坏味道 - 函数过于复杂             | Medium | `start_gallery_apply` is too complex (26 > 10)                                                   |
| 46  | 代码坏味道 - 分支过多               | Medium | Too many branches (33 > 12)                                                                      |
| 46  | 代码坏味道 - 语句过多               | Medium | Too many statements (123 > 50)                                                                   |
| 69  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 70  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 71  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 72  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 92  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 103 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 115 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 220 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 233 | 代码坏味道 - 语句过多               | Medium | Too many statements (55 > 50)                                                                    |
| 289 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 306 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 310 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 324 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 336 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                    |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                        |
| 50  | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                            |
| 56  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 56  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 61  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 69  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                        |
| 81  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 91  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 97  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                      |
| 98  | 代码重复 - 冗余代码 (PIE790)       | Low    | Unnecessary `pass` statement                                                                     |
| 101 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 111 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 115 | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                        |
| 116 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 122 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 133 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 136 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 140 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 144 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 146 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 153 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `720` with a constant variable                |
| 155 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `512` with a constant variable                |
| 159 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 162 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `9` with a constant variable                  |
| 164 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `6` with a constant variable                  |
| 168 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 172 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| 175 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                   |
| ... | ...                        | ...    | *还有 23 个同文件问题未展示*                                                                                |

### 文件: `src/handlers/fsm/quick_image_fsm.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                               |
| --- | -------------------------- | ------ | -------------------------------------------------------------------------------------------------- |
| 4   | 死代码检测 - 未使用的导入             | Medium | `asyncio` imported but unused                                                                      |
| 7   | 死代码检测 - 未使用的导入             | Medium | `re` imported but unused                                                                           |
| 14  | 死代码检测 - 未使用的导入             | Medium | `telegram.ext.CallbackQueryHandler` imported but unused                                            |
| 50  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 92  | 代码坏味道 - 函数过于复杂             | Medium | `receive_image` is too complex (12 > 10)                                                           |
| 92  | 代码坏味道 - 函数返回点过多            | Medium | Too many return statements (8 > 6)                                                                 |
| 92  | 代码坏味道 - 分支过多               | Medium | Too many branches (13 > 12)                                                                        |
| 92  | 代码坏味道 - 语句过多               | Medium | Too many statements (60 > 50)                                                                      |
| 111 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 144 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 145 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                          |
| 33  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `user_id`                                                                |
| 49  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 52  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 52  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 52  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 52  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 60  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 83  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 85  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 87  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 101 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 107 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 115 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 115 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 115 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 115 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 115 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 130 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 132 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 139 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 139 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 142 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 150 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 153 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 158 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 170 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 173 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 177 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                |
| 178 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                                                |
| 186 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 186 | 代码坏味道 - Ruff特有规则 (RUF010)  | Low    | Use explicit conversion flag                                                                       |
| 187 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 213 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 213 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 222 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 222 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 222 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 222 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| ... | ...                        | ...    | *还有 1 个同文件问题未展示*                                                                                   |

### 文件: `src/handlers/fsm/quick_video_fsm.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                               |
| --- | -------------------------- | ------ | -------------------------------------------------------------------------------------------------- |
| 4   | 死代码检测 - 未使用的导入             | Medium | `asyncio` imported but unused                                                                      |
| 6   | 死代码检测 - 未使用的导入             | Medium | `re` imported but unused                                                                           |
| 49  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 114 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 139 | 代码坏味道 - 函数过于复杂             | Medium | `process_settings` is too complex (11 > 10)                                                        |
| 178 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 204 | 代码坏味道 - 函数过于复杂             | Medium | `start_generation` is too complex (15 > 10)                                                        |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                          |
| 33  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `user_id`                                                                |
| 45  | 死代码检测 - 未使用的局部变量           | Low    | Local variable `user_id` is assigned to but never used                                             |
| 48  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 51  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 51  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 51  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 51  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 59  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 68  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 80  | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `2` with a constant variable                    |
| 81  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 92  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 98  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 108 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 110 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 117 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 120 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 124 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 128 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 129 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 130 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 143 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 146 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 147 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 160 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 161 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 169 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 170 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 177 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 181 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 185 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 189 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 190 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 190 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| ... | ...                        | ...    | *还有 31 个同文件问题未展示*                                                                                  |

### 文件: `src/handlers/fsm/video_lora_fsm.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                                               |
| --- | -------------------------- | ------ | -------------------------------------------------------------------------------------------------- |
| 4   | 死代码检测 - 未使用的导入             | Medium | `asyncio` imported but unused                                                                      |
| 6   | 死代码检测 - 未使用的导入             | Medium | `re` imported but unused                                                                           |
| 54  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 136 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 194 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                      |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                          |
| 34  | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `user_id`                                                                |
| 48  | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 52  | 死代码检测 - 未使用的局部变量           | Low    | Local variable `user_id` is assigned to but never used                                             |
| 53  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 56  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 56  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 56  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 56  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 64  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 79  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 82  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 90  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 93  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 96  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 99  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 101 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 103 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 104 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 104 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 104 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 115 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 121 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?   |
| 132 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 139 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 142 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 146 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 150 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 152 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 153 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                         |
| 154 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 163 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                     |
| 166 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 167 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 176 | 代码坏味道 - 代码不够简化 (SIM105)    | Low    | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                              |
| 177 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| ... | ...                        | ...    | *还有 34 个同文件问题未展示*                                                                                  |

### 文件: `src/handlers/message_handler.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                              |
| --- | ---------------------------- | ------ | --------------------------------------------------------------------------------- |
| 3   | 死代码检测 - 未使用的导入               | Medium | `random` imported but unused                                                      |
| 9   | 死代码检测 - 未使用的导入               | Medium | `config.ENABLE_PUBLIC_SHARE` imported but unused                                  |
| 14  | 死代码检测 - 未使用的导入               | Medium | `src.logger.UserLogger` imported but unused                                       |
| 15  | 死代码检测 - 未使用的导入               | Medium | `src.utils.load_prompts` imported but unused                                      |
| 18  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_EDIT` imported but unused                                     |
| 18  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_UNDRESS` imported but unused                                  |
| 18  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_MASTURBATION` imported but unused                             |
| 19  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_FACESWAP_STEP1` imported but unused                           |
| 19  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_FACESWAP_STEP2` imported but unused                           |
| 19  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_RANDOM_FACESWAP` imported but unused                          |
| 20  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_FACE_VIDEO_STEP1` imported but unused                         |
| 20  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_FACE_VIDEO_STEP2` imported but unused                         |
| 21  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_CUSTOM_VIDEO` imported but unused                             |
| 21  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_PERFECT_VIDEO_INSERT` imported but unused                     |
| 22  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_DOGGY_STYLE` imported but unused                              |
| 22  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_BLOWJOB` imported but unused                                  |
| 22  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_UNDRESS_TONGUE` imported but unused                           |
| 22  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_CLOSEUP_BLOWJOB` imported but unused                          |
| 22  | 死代码检测 - 未使用的导入               | Medium | `src.constants.MODE_I2I_PRO` imported but unused                                  |
| 142 | 死代码检测 - Vulture死代码           | Medium | unused function 'handle\_photo\_edit\_menu'                                       |
| 152 | 死代码检测 - Vulture死代码           | Medium | unused function 'handle\_video\_edit\_menu'                                       |
| 162 | 死代码检测 - Vulture死代码           | Medium | unused function 'handle\_gallery\_menu'                                           |
| 178 | 死代码检测 - Vulture死代码           | Medium | unused function 'handle\_back\_to\_main\_menu'                                    |
| 184 | 死代码检测 - Vulture死代码           | Medium | unused function 'handle\_recharge\_menu'                                          |
| 221 | 死代码检测 - Vulture死代码           | Medium | unused function 'handle\_personal\_center'                                        |
| 229 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 264 | 死代码检测 - Vulture死代码           | Medium | unused function 'handle\_checkin'                                                 |
| 285 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 303 | 死代码检测 - Vulture死代码           | Medium | unused function 'handle\_share'                                                   |
| 307 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 326 | 死代码检测 - Vulture死代码           | Medium | unused function 'handle\_queue\_status'                                           |
| 356 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                     |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                         |
| 41  | 代码坏味道 - 代码风格问题 (E701)        | Low    | Multiple statements on one line (colon)                                           |
| 41  | 代码坏味道 - Return语句不规范 (RET502) | Low    | Do not implicitly `return None` in function able to return non-`None` value       |
| 42  | 代码坏味道 - 代码风格问题 (E701)        | Low    | Multiple statements on one line (colon)                                           |
| 42  | 代码坏味道 - Return语句不规范 (RET502) | Low    | Do not implicitly `return None` in function able to return non-`None` value       |
| 47  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 50  | 代码坏味道 - Return语句不规范 (RET503) | Low    | Missing explicit `return` at the end of function able to return non-`None` value  |
| 52  | 代码坏味道 - 代码风格问题 (E701)        | Low    | Multiple statements on one line (colon)                                           |
| 52  | 代码坏味道 - Return语句不规范 (RET502) | Low    | Do not implicitly `return None` in function able to return non-`None` value       |
| 53  | 代码坏味道 - 代码风格问题 (E701)        | Low    | Multiple statements on one line (colon)                                           |
| 53  | 代码坏味道 - Return语句不规范 (RET502) | Low    | Do not implicitly `return None` in function able to return non-`None` value       |
| 58  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 63  | 代码坏味道 - 代码风格问题 (E701)        | Low    | Multiple statements on one line (colon)                                           |
| 63  | 代码坏味道 - Return语句不规范 (RET502) | Low    | Do not implicitly `return None` in function able to return non-`None` value       |
| 64  | 代码坏味道 - 代码风格问题 (E701)        | Low    | Multiple statements on one line (colon)                                           |
| 64  | 代码坏味道 - Return语句不规范 (RET502) | Low    | Do not implicitly `return None` in function able to return non-`None` value       |
| 69  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                    |
| 75  | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `3.0` with a constant variable |
| ... | ...                          | ...    | *还有 115 个同文件问题未展示*                                                                |

### 文件: `src/handlers/prompt_router.py`

| 行号 | 问题分类                      | 严重程度   | 问题描述                                                                                                |
| -- | ------------------------- | ------ | --------------------------------------------------------------------------------------------------- |
| 1  | 死代码检测 - Vulture死代码        | Medium | unused import 'Awaitable'                                                                           |
| 1  | 死代码检测 - 未使用的导入            | Medium | `typing.Callable` imported but unused                                                               |
| 1  | 死代码检测 - 未使用的导入            | Medium | `typing.Awaitable` imported but unused                                                              |
| 2  | 死代码检测 - 未使用的导入            | Medium | `telegram.Update` imported but unused                                                               |
| 17 | 作用域分析 - 使用global语句        | Medium | Using the global statement to update `GLOBAL_MENU_FILTER` is discouraged                            |
| 1  | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                                           |
| 16 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 20 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 21 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 21 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 26 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 28 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 31 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 33 | 代码坏味道 - Ruff特有规则 (RUF005) | Low    | Consider `[exact_pattern, *regex_patterns]` instead of concatenation                                |
| 35 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace                                                                      |
| 39 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 39 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |

### 文件: `src/logger.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                   |
| --- | ---------------------------- | ------ | ------------------------------------------------------ |
| 103 | 死代码检测 - Vulture死代码           | Medium | unused method 'log\_interaction'                       |
| 103 | 作用域分析 - 参数遮蔽内置名称             | Medium | Function argument `type` is shadowing a Python builtin |
| 107 | 代码坏味道 - 参数过多                 | Medium | Too many arguments in function definition (7 > 5)      |
| 107 | 作用域分析 - 参数遮蔽内置名称             | Medium | Function argument `type` is shadowing a Python builtin |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted              |
| 20  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 23  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 35  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 39  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 44  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 65  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 69  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 72  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 76  | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `else` after `return` statement            |
| 88  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 91  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 95  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 99  | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `else` after `return` statement            |
| 107 | 代码坏味道 - Ruff特有规则 (RUF013)    | Low    | PEP 484 prohibits implicit `Optional`                  |
| 113 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 115 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 121 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 128 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 141 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |
| 145 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                         |

### 文件: `src/payment_api_server.py`

| 行号 | 问题分类                         | 严重程度   | 问题描述                                                                       |
| -- | ---------------------------- | ------ | -------------------------------------------------------------------------- |
| 14 | 死代码检测 - Vulture死代码           | Medium | unused function 'huanyuy\_notify'                                          |
| 53 | 死代码检测 - Vulture死代码           | Medium | unused function 'payment\_result'                                          |
| 83 | 代码坏味道 - Pylint警告 (PLW1508)   | Medium | Invalid type for environment variable default; expected `str` or `None`    |
| 1  | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                  |
| 26 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                             |
| 31 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                             |
| 35 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                             |
| 39 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                             |
| 46 | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `else` after `return` statement                                |
| 54 | 死代码检测 - 未使用的函数参数             | Low    | Unused function argument: `request`                                        |
| 75 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 76 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |

### 文件: `src/quota.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                          |
| --- | -------------------------- | ------ | --------------------------------------------- |
| 17  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file |
| 34  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file |
| 123 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file |
| 159 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file |
| 164 | 死代码检测 - Vulture死代码         | Medium | unused variable 'new\_full\_name'             |
| 164 | 代码坏味道 - 函数返回点过多            | Medium | Too many return statements (7 > 6)            |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted     |
| 17  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted     |
| 23  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 40  | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 40  | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 58  | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 58  | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 68  | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 77  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 80  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 87  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 102 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 102 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 112 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 122 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 123 | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted     |
| 129 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 141 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 164 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 164 | 死代码检测 - 未使用的方法参数           | Low    | Unused method argument: `new_full_name`       |
| 164 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 178 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 185 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 190 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 192 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 199 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 202 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 206 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 224 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 256 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 259 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 262 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 267 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 283 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 299 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 307 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 309 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 326 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |

### 文件: `src/services/image_service.py`

| 行号 | 问题分类          | 严重程度   | 问题描述                                              |
| -- | ------------- | ------ | ------------------------------------------------- |
| 5  | 代码坏味道 - 参数过多  | Medium | Too many arguments in function definition (7 > 5) |
| 9  | 代码坏味道 - 参数过多  | Medium | Too many arguments in function definition (6 > 5) |
| 25 | 代码坏味道 - 参数过多  | Medium | Too many arguments in function definition (7 > 5) |
| 29 | 代码坏味道 - 参数过多  | Medium | Too many arguments in function definition (7 > 5) |
| 33 | 代码坏味道 - 参数过多  | Medium | Too many arguments in function definition (8 > 5) |
| 37 | 代码坏味道 - 参数过多  | Medium | Too many arguments in function definition (7 > 5) |
| 1  | 导入优化 - 未排序的导入 | Low    | Import block is un-sorted or un-formatted         |

### 文件: `src/services/log_service.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                     |
| --- | -------------------------- | ------ | -------------------------------------------------------- |
| 19  | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (7 > 5)        |
| 40  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file            |
| 72  | 代码坏味道 - 参数过多               | Medium | Too many arguments in function definition (6 > 5)        |
| 135 | 性能问题 - 性能建议 (PERF203)      | Medium | `try`-`except` within a loop incurs performance overhead |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                |
| 30  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                           |
| 43  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                           |
| 98  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                           |
| 114 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                           |

### 文件: `src/services/payment_validator.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                            |
| --- | -------------------------- | ------ | ------------------------------------------------------------------------------- |
| 17  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                   |
| 19  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                   |
| 31  | 作用域分析 - 变量遮蔽内置名称           | Medium | Variable `slice` is shadowing a Python builtin                                  |
| 124 | 代码坏味道 - 函数过于复杂             | Medium | `_process_order` is too complex (19 > 10)                                       |
| 124 | 代码坏味道 - 函数返回点过多            | Medium | Too many return statements (8 > 6)                                              |
| 124 | 代码坏味道 - 分支过多               | Medium | Too many branches (23 > 12)                                                     |
| 124 | 代码坏味道 - 语句过多               | Medium | Too many statements (102 > 50)                                                  |
| 145 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                   |
| 177 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                   |
| 179 | 代码坏味道 - Pylint警告 (PLR1730) | Medium | Replace `if` statement with `max` call                                          |
| 202 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                   |
| 203 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                   |
| 234 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                   |
| 247 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                   |
| 273 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                   |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                       |
| 21  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 30  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 45  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 51  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 57  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 60  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 73  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 76  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 80  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 82  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 87  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 90  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 95  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 100 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 104 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 112 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 118 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                             |
| 131 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 134 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `4` with a constant variable |
| 137 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 144 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 148 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 156 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 169 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 175 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 177 | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                       |
| 187 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 199 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 202 | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                       |
| 204 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 211 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 224 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 227 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                  |
| 233 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?     |
| ... | ...                        | ...    | *还有 21 个同文件问题未展示*                                                               |

### 文件: `src/services/permission_service.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                                             |
| --- | ---------------------------- | ------ | ------------------------------------------------------------------------------------------------ |
| 53  | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 86  | 作用域分析 - 变量遮蔽内置名称             | Medium | Variable `credits` is shadowing a Python builtin                                                 |
| 110 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 120 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 121 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 141 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 171 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 192 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 200 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 247 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 255 | 作用域分析 - 变量遮蔽内置名称             | Medium | Variable `credits` is shadowing a Python builtin                                                 |
| 283 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 284 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 285 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 319 | 代码坏味道 - Pylint警告 (PLR5501)   | Medium | Use `elif` instead of `else` then `if`, to reduce indentation                                    |
| 337 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 344 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 345 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 361 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 362 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 363 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 385 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 444 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 450 | 死代码检测 - Vulture死代码           | Medium | unused variable 'created'                                                                        |
| 470 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 478 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                                    |
| 1   | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                        |
| 19  | 代码坏味道 - Ruff特有规则 (RUF003)    | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                      |
| 21  | 代码坏味道 - 魔法值使用                | Low    | Magic value used in comparison, consider replacing `2` with a constant variable                  |
| 27  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 34  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 41  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 63  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 72  | 代码坏味道 - Return语句不规范 (RET505) | Low    | Unnecessary `else` after `return` statement                                                      |
| 78  | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 82  | 代码重复 - 冗余代码 (PIE790)         | Low    | Unnecessary `pass` statement                                                                     |
| 99  | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 105 | 代码坏味道 - Ruff特有规则 (RUF013)    | Low    | PEP 484 prohibits implicit `Optional`                                                            |
| 113 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 120 | 导入优化 - 未排序的导入                | Low    | Import block is un-sorted or un-formatted                                                        |
| 127 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 127 | 代码坏味道 - Ruff特有规则 (RUF001)    | Low    | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 144 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 150 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 153 | 代码坏味道 - Ruff特有规则 (RUF013)    | Low    | PEP 484 prohibits implicit `Optional`                                                            |
| 178 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 180 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 189 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| 207 | 代码坏味道 - Ruff特有规则 (RUF013)    | Low    | PEP 484 prohibits implicit `Optional`                                                            |
| 218 | 代码坏味道 - 警告 (W293)            | Low    | Blank line contains whitespace                                                                   |
| ... | ...                          | ...    | *还有 51 个同文件问题未展示*                                                                                |

### 文件: `src/services/recovery_service.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                                       |
| --- | -------------------------- | ------ | -------------------------------------------------------------------------- |
| 2   | 死代码检测 - 未使用的导入             | Medium | `asyncio` imported but unused                                              |
| 122 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                              |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                  |
| 47  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                             |
| 71  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 71  | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 100 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 105 | 代码坏味道 - Ruff特有规则 (RUF001)  | Low    | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 111 | 死代码检测 - 未使用的函数参数           | Low    | Unused function argument: `registry_task_id`                               |
| 116 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                             |
| 119 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                             |

### 文件: `src/services/rmb_payment_service.py`

| 行号 | 问题分类                       | 严重程度   | 问题描述                                                                          |
| -- | -------------------------- | ------ | ----------------------------------------------------------------------------- |
| 45 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                 |
| 1  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                     |
| 8  | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 9  | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                           |
| 10 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                                                           |
| 43 | 代码坏味道 - Ruff特有规则 (RUF002)  | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 46 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                |
| 57 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                |
| 58 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?   |
| 58 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 58 | 代码坏味道 - Ruff特有规则 (RUF003)  | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |
| 64 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                |
| 74 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                |
| 81 | 死代码检测 - 未使用的局部变量           | Low    | Local variable `json_e` is assigned to but never used                         |

### 文件: `src/services/storage.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                          |
| --- | -------------------------- | ------ | --------------------------------------------- |
| 4   | 死代码检测 - 未使用的导入             | Medium | `os` imported but unused                      |
| 10  | 死代码检测 - 未使用的导入             | Medium | `config.R2_PUBLIC_DOMAIN` imported but unused |
| 84  | 代码坏味道 - Pylint警告 (PLC0207) | Medium | String is split more times than necessary     |
| 187 | 代码坏味道 - Pylint警告 (PLC0207) | Medium | String is split more times than necessary     |
| 192 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file |
| 192 | 死代码检测 - 未使用的导入             | Medium | `config.MINIO_ENDPOINT` imported but unused   |
| 235 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file |
| 235 | 死代码检测 - 未使用的导入             | Medium | `config.MINIO_ENDPOINT` imported but unused   |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted     |
| 31  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 37  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 45  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 53  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 78  | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 83  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 85  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 91  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 107 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 113 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 119 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 127 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 136 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                           |
| 137 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                           |
| 138 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                           |
| 147 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 164 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 170 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 178 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 183 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 191 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 192 | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted     |
| 196 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 205 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 208 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 210 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                           |
| 211 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                           |
| 217 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                           |
| 218 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                           |
| 222 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 228 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 228 | 死代码检测 - 未使用的方法参数           | Low    | Unused method argument: `content_type`        |
| 228 | 代码坏味道 - Ruff特有规则 (RUF013)  | Low    | PEP 484 prohibits implicit `Optional`         |
| 233 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 235 | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted     |
| 236 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 241 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 245 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 254 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 261 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                |
| 263 | 代码坏味道 - 警告 (W291)          | Low    | Trailing whitespace                           |
| ... | ...                        | ...    | *还有 4 个同文件问题未展示*                              |

### 文件: `src/services/task_registry.py`

| 行号 | 问题分类                      | 严重程度   | 问题描述                                                                          |
| -- | ------------------------- | ------ | ----------------------------------------------------------------------------- |
| 2  | 死代码检测 - 未使用的导入            | Medium | `uuid` imported but unused                                                    |
| 11 | 代码坏味道 - 参数过多              | Medium | Too many arguments in function definition (7 > 5)                             |
| 1  | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                     |
| 7  | 代码坏味道 - 代码风格问题 (E402)     | Low    | Module level import not at top of file                                        |
| 7  | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                     |
| 11 | 代码坏味道 - Ruff特有规则 (RUF013) | Low    | PEP 484 prohibits implicit `Optional`                                         |
| 11 | 代码坏味道 - Ruff特有规则 (RUF013) | Low    | PEP 484 prohibits implicit `Optional`                                         |
| 43 | 死代码检测 - 未使用的类方法参数         | Low    | Unused class method argument: `bot`                                           |
| 45 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 45 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 45 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 47 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 48 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)? |
| 52 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?   |

### 文件: `src/services/zombie_cleaner_service.py`

| 行号 | 问题分类                      | 严重程度   | 问题描述                                                                                                  |
| -- | ------------------------- | ------ | ----------------------------------------------------------------------------------------------------- |
| 11 | 代码坏味道 - 函数过于复杂            | Medium | `clean_zombies` is too complex (13 > 10)                                                              |
| 1  | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted                                                             |
| 13 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 13 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 17 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 29 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 33 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 34 | 代码坏味道 - 魔法值使用             | Low    | Magic value used in comparison, consider replacing `7200` with a constant variable                    |
| 46 | 代码坏味道 - 警告 (W291)         | Low    | Trailing whitespace                                                                                   |
| 47 | 代码坏味道 - 警告 (W291)         | Low    | Trailing whitespace                                                                                   |
| 48 | 代码坏味道 - 警告 (W291)         | Low    | Trailing whitespace                                                                                   |
| 69 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?     |
| 69 | 代码坏味道 - Ruff特有规则 (RUF003) | Low    | Comment contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?   |
| 73 | 死代码检测 - 注释掉的代码            | Low    | Found commented-out code                                                                              |
| 89 | 代码坏味道 - Ruff特有规则 (RUF002) | Low    | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |

### 文件: `src/tests/test_points_system.py`

| 行号 | 问题分类               | 严重程度   | 问题描述                      |
| -- | ------------------ | ------ | ------------------------- |
| 44 | 死代码检测 - Vulture死代码 | Medium | unused variable 'created' |

### 文件: `src/tests/test_queue_logic.py`

| 行号 | 问题分类               | 严重程度   | 问题描述                            |
| -- | ------------------ | ------ | ------------------------------- |
| 36 | 死代码检测 - Vulture死代码 | Medium | unused attribute 'side\_effect' |

### 文件: `src/utils.py`

| 行号  | 问题分类                         | 严重程度   | 问题描述                                                                             |
| --- | ---------------------------- | ------ | -------------------------------------------------------------------------------- |
| 23  | 代码坏味道 - 函数过于复杂               | Medium | `async_retry` is too complex (11 > 10)                                           |
| 35  | 性能问题 - 性能建议 (PERF203)        | Medium | `try`-`except` within a loop incurs performance overhead                         |
| 160 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                    |
| 196 | 代码坏味道 - Pylint警告 (PLC0415)   | Medium | `import` should be at the top-level of a file                                    |
| 29  | 代码坏味道 - Return语句不规范 (RET503) | Low    | Missing explicit `return` at the end of function able to return non-`None` value |
| 40  | 代码重复 - 冗余代码 (PIE790)         | Low    | Unnecessary `pass` statement                                                     |
| 41  | 代码坏味道 - Return语句不规范 (RET502) | Low    | Do not implicitly `return None` in function able to return non-`None` value      |
| 67  | 代码坏味道 - Return语句不规范 (RET502) | Low    | Do not implicitly `return None` in function able to return non-`None` value      |
| 216 | 代码坏味道 - 警告 (W291)            | Low    | Trailing whitespace                                                              |
| 217 | 代码坏味道 - 警告 (W291)            | Low    | Trailing whitespace                                                              |

### 文件: `src/web_api/core/config.py`

| 行号 | 问题分类               | 严重程度   | 问题描述                                      |
| -- | ------------------ | ------ | ----------------------------------------- |
| 7  | 死代码检测 - Vulture死代码 | Medium | unused variable 'PROJECT\_NAME'           |
| 8  | 死代码检测 - Vulture死代码 | Medium | unused variable 'VERSION'                 |
| 1  | 导入优化 - 未排序的导入      | Low    | Import block is un-sorted or un-formatted |
| 9  | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |

### 文件: `src/web_api/main.py`

| 行号 | 问题分类               | 严重程度   | 问题描述                                      |
| -- | ------------------ | ------ | ----------------------------------------- |
| 50 | 死代码检测 - Vulture死代码 | Medium | unused function 'health\_check'           |
| 1  | 导入优化 - 未排序的导入      | Low    | Import block is un-sorted or un-formatted |
| 15 | 死代码检测 - 未使用的函数参数   | Low    | Unused function argument: `app`           |
| 34 | 代码坏味道 - 警告 (W291)  | Low    | Trailing whitespace                       |

### 文件: `src/web_api/routers/users.py`

| 行号 | 问题分类                       | 严重程度   | 问题描述                                                                                                                                                                   |
| -- | -------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2  | 死代码检测 - 未使用的导入             | Medium | `fastapi.Query` imported but unused                                                                                                                                    |
| 2  | 死代码检测 - 未使用的导入             | Medium | `fastapi.HTTPException` imported but unused                                                                                                                            |
| 3  | 死代码检测 - 未使用的导入             | Medium | `sqlalchemy.func` imported but unused                                                                                                                                  |
| 19 | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_user\_profile'                                                                                                                                   |
| 20 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 25 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                                                                                                          |
| 49 | 死代码检测 - Vulture死代码         | Medium | unused function 'get\_user\_history'                                                                                                                                   |
| 51 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 52 | 作用域分析 - 默认参数中调用函数          | Medium | Do not perform function call `Depends` in argument defaults; instead, perform the call within the function, or read the default from a module-level singleton variable |
| 1  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                                                                                                              |
| 27 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 32 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 59 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |
| 69 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                                                                                                         |

### 文件: `src/web_api/schemas/auth_schema.py`

| 行号 | 问题分类                  | 严重程度   | 问题描述                                                       |
| -- | --------------------- | ------ | ---------------------------------------------------------- |
| 1  | 死代码检测 - 未使用的导入        | Medium | `pydantic.Field` imported but unused                       |
| 10 | 死代码检测 - Vulture死代码    | Medium | unused variable 'photo\_url'                               |
| 19 | 死代码检测 - Vulture死代码    | Medium | unused variable 'token\_type'                              |
| 22 | 死代码检测 - Vulture死代码    | Medium | unused variable 'recharged\_invitees\_count'               |
| 23 | 死代码检测 - Vulture死代码    | Medium | unused variable 'total\_recharge\_count'                   |
| 40 | 死代码检测 - Vulture死代码    | Medium | unused variable 'invitation\_count'                        |
| 44 | 死代码检测 - Vulture死代码    | Medium | unused variable 'from\_attributes'                         |
| 1  | 导入优化 - 未排序的导入         | Low    | Import block is un-sorted or un-formatted                  |
| 13 | 代码坏味道 - 警告 (W293)     | Low    | Blank line contains whitespace                             |
| 15 | 代码坏味道 - 命名规范问题 (N815) | Low    | Variable `initData` in class scope should not be mixedCase |
| 42 | 代码坏味道 - 警告 (W293)     | Low    | Blank line contains whitespace                             |

### 文件: `src/web_api/schemas/gallery_schema.py`

| 行号 | 问题分类               | 严重程度   | 问题描述                                      |
| -- | ------------------ | ------ | ----------------------------------------- |
| 24 | 死代码检测 - Vulture死代码 | Medium | unused variable 'has\_liked'              |
| 25 | 死代码检测 - Vulture死代码 | Medium | unused variable 'has\_disliked'           |
| 1  | 导入优化 - 未排序的导入      | Low    | Import block is un-sorted or un-formatted |
| 22 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |

### 文件: `src/web_api/schemas/task_schema.py`

| 行号 | 问题分类                      | 严重程度   | 问题描述                                      |
| -- | ------------------------- | ------ | ----------------------------------------- |
| 2  | 死代码检测 - 未使用的导入            | Medium | `typing.List` imported but unused         |
| 13 | 死代码检测 - Vulture死代码        | Medium | unused variable 'json\_schema\_extra'     |
| 28 | 死代码检测 - Vulture死代码        | Medium | unused variable 'balance\_remaining'      |
| 1  | 导入优化 - 未排序的导入             | Low    | Import block is un-sorted or un-formatted |
| 11 | 代码坏味道 - 警告 (W293)         | Low    | Blank line contains whitespace            |
| 13 | 代码坏味道 - Ruff特有规则 (RUF012) | Low    | Mutable default value for class attribute |

### 文件: `src/web_api/schemas/user_schema.py`

| 行号 | 问题分类               | 严重程度   | 问题描述                                      |
| -- | ------------------ | ------ | ----------------------------------------- |
| 17 | 死代码检测 - Vulture死代码 | Medium | unused variable 'from\_attributes'        |
| 1  | 导入优化 - 未排序的导入      | Low    | Import block is un-sorted or un-formatted |
| 15 | 代码坏味道 - 警告 (W293)  | Low    | Blank line contains whitespace            |

### 文件: `workers/comfy_agent/comfy_client.py`

| 行号 | 问题分类                       | 严重程度   | 问题描述                                                                              |
| -- | -------------------------- | ------ | --------------------------------------------------------------------------------- |
| 66 | 作用域分析 - 参数遮蔽内置名称           | Medium | Function argument `type` is shadowing a Python builtin                            |
| 71 | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                                     |
| 80 | 性能问题 - 性能建议 (PERF203)      | Medium | `try`-`except` within a loop incurs performance overhead                          |
| 1  | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                                         |
| 15 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `200` with a constant variable |
| 31 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                    |
| 37 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                    |
| 40 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `200` with a constant variable |
| 51 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `200` with a constant variable |
| 62 | 代码坏味道 - 魔法值使用              | Low    | Magic value used in comparison, consider replacing `200` with a constant variable |
| 73 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                                    |

### 文件: `workers/comfy_agent/workflow_patcher.py`

| 行号  | 问题分类                       | 严重程度   | 问题描述                                                          |
| --- | -------------------------- | ------ | ------------------------------------------------------------- |
| 30  | 代码坏味道 - 函数过于复杂             | Medium | `load_workflow` is too complex (12 > 10)                      |
| 65  | 代码坏味道 - 函数过于复杂             | Medium | `patch_workflow` is too complex (29 > 10)                     |
| 65  | 代码坏味道 - 分支过多               | Medium | Too many branches (30 > 12)                                   |
| 65  | 代码坏味道 - 语句过多               | Medium | Too many statements (59 > 50)                                 |
| 71  | 代码坏味道 - Pylint警告 (PLC0415) | Medium | `import` should be at the top-level of a file                 |
| 159 | 代码坏味道 - 函数过于复杂             | Medium | `heuristic_patch` is too complex (24 > 10)                    |
| 159 | 代码坏味道 - 分支过多               | Medium | Too many branches (23 > 12)                                   |
| 1   | 导入优化 - 未排序的导入              | Low    | Import block is un-sorted or un-formatted                     |
| 51  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 56  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 60  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 68  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 75  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 78  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 81  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 94  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 97  | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 116 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 126 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 136 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 148 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 153 | 代码坏味道 - 代码不够简化 (SIM102)    | Low    | Use a single `if` statement instead of nested `if` statements |
| 156 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 164 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 167 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 176 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 179 | 代码坏味道 - 代码不够简化 (SIM102)    | Low    | Use a single `if` statement instead of nested `if` statements |
| 182 | 代码坏味道 - 代码不够简化 (SIM102)    | Low    | Use a single `if` statement instead of nested `if` statements |
| 185 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 189 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 193 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 196 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 199 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 202 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 205 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |
| 211 | 代码坏味道 - 警告 (W293)          | Low    | Blank line contains whitespace                                |

### 文件: `cs_bot/langgraph_client.py`

| 行号  | 问题分类                      | 严重程度 | 问题描述                                                                                                         |
| --- | ------------------------- | ---- | ------------------------------------------------------------------------------------------------------------ |
| 1   | 导入优化 - 未排序的导入             | Low  | Import block is un-sorted or un-formatted                                                                    |
| 22  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 23  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 41  | 代码坏味道 - 代码不够简化 (SIM108)   | Low  | Use ternary operator `llm_with_tools = llm.bind_tools(tools) if tools else llm` instead of `if`-`else`-block |
| 51  | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                                |
| 51  | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?          |
| 51  | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?        |
| 51  | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                |
| 51  | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                |
| 57  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                               |
| 58  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                                  |
| 58  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?            |
| 58  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?          |
| 60  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                               |
| 61  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                                  |
| 62  | 代码坏味道 - Ruff特有规则 (RUF005) | Low  | Consider `[system_prompt, *recent_messages]` instead of concatenation                                        |
| 63  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                               |
| 65  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                               |
| 66  | 死代码检测 - 注释掉的代码            | Low  | Found commented-out code                                                                                     |
| 68  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                               |
| 81  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 84  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                               |
| 85  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                                  |
| 85  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 87  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 90  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 96  | 死代码检测 - 注释掉的代码            | Low  | Found commented-out code                                                                                     |
| 97  | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 109 | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                |
| 110 | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                |
| 110 | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?          |
| 110 | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?        |
| 113 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                   |
| 114 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?             |
| 114 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                                   |
| 114 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?           |
| 114 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                   |
| 114 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                   |
| 116 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                                   |
| 118 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                   |
| 123 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 127 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 127 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                                  |
| 130 | 代码坏味道 - Ruff特有规则 (RUF013) | Low  | PEP 484 prohibits implicit `Optional`                                                                        |
| 132 | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                |
| 134 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?            |
| 134 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?          |
| 136 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 136 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                                  |
| 139 | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                               |
| ... | ...                       | ...  | *还有 14 个同文件问题未展示*                                                                                            |

### 文件: `scripts/clear_stuck_tasks.py`

| 行号 | 问题分类                      | 严重程度 | 问题描述                                                                                                  |
| -- | ------------------------- | ---- | ----------------------------------------------------------------------------------------------------- |
| 1  | 导入优化 - 未排序的导入             | Low  | Import block is un-sorted or un-formatted                                                             |
| 10 | 导入优化 - 未排序的导入             | Low  | Import block is un-sorted or un-formatted                                                             |
| 29 | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?   |
| 29 | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)? |
| 29 | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 29 | 代码坏味道 - Ruff特有规则 (RUF002) | Low  | Docstring contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                         |
| 57 | 代码坏味道 - 警告 (W291)         | Low  | Trailing whitespace                                                                                   |
| 58 | 代码坏味道 - 警告 (W291)         | Low  | Trailing whitespace                                                                                   |
| 59 | 代码坏味道 - 警告 (W291)         | Low  | Trailing whitespace                                                                                   |
| 82 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)?      |
| 82 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 90 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?     |
| 90 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?   |
| 90 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 91 | 代码坏味道 - Ruff特有规则 (RUF003) | Low  | Comment contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                           |
| 92 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `（` (FULLWIDTH LEFT PARENTHESIS). Did you mean `(` (LEFT PARENTHESIS)?      |
| 92 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 92 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                            |
| 92 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `）` (FULLWIDTH RIGHT PARENTHESIS). Did you mean `)` (RIGHT PARENTHESIS)?    |
| 92 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                            |
| 94 | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                        |

### 文件: `src/circuit_breaker.py`

| 行号 | 问题分类                  | 严重程度 | 问题描述                                                                              |
| -- | --------------------- | ---- | --------------------------------------------------------------------------------- |
| 1  | 导入优化 - 未排序的导入         | Low  | Import block is un-sorted or un-formatted                                         |
| 12 | 代码坏味道 - 命名规范问题 (N818) | Low  | Exception name `CircuitBreakerOpenException` should be named with an Error suffix |

### 文件: `src/handlers/command_handler.py`

| 行号  | 问题分类                      | 严重程度 | 问题描述                                                                                             |
| --- | ------------------------- | ---- | ------------------------------------------------------------------------------------------------ |
| 1   | 导入优化 - 未排序的导入             | Low  | Import block is un-sorted or un-formatted                                                        |
| 23  | 死代码检测 - 未使用的局部变量          | Low  | Local variable `user_id` is assigned to but never used                                           |
| 24  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                   |
| 27  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                   |
| 29  | 代码坏味道 - 代码不够简化 (SIM118)   | Low  | Use `key in dict` instead of `key in dict.keys()`                                                |
| 32  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                   |
| 35  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                   |
| 46  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                   |
| 48  | 代码坏味道 - 警告 (W291)         | Low  | Trailing whitespace                                                                              |
| 57  | 代码坏味道 - 代码不够简化 (SIM105)   | Low  | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                            |
| 61  | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 61  | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 61  | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 68  | 代码坏味道 - 代码不够简化 (SIM105)   | Low  | Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`                            |
| 72  | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 72  | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 85  | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                   |
| 100 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 101 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 102 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 102 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 103 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 103 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 103 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `！` (FULLWIDTH EXCLAMATION MARK). Did you mean `!` (EXCLAMATION MARK)? |
| 104 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 104 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 105 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 106 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 106 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 107 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 108 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `：` (FULLWIDTH COLON). Did you mean `:` (COLON)?                       |
| 108 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 108 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `；` (FULLWIDTH SEMICOLON). Did you mean `;` (SEMICOLON)?               |
| 127 | 代码坏味道 - 警告 (W293)         | Low  | Blank line contains whitespace                                                                   |
| 131 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |
| 135 | 代码坏味道 - Ruff特有规则 (RUF001) | Low  | String contains ambiguous `，` (FULLWIDTH COMMA). Did you mean `,` (COMMA)?                       |

### 文件: `src/handlers/utils.py`

| 行号 | 问题分类              | 严重程度 | 问题描述                                      |
| -- | ----------------- | ---- | ----------------------------------------- |
| 1  | 导入优化 - 未排序的导入     | Low  | Import block is un-sorted or un-formatted |
| 13 | 代码坏味道 - 警告 (W293) | Low  | Blank line contains whitespace            |
| 24 | 代码坏味道 - 警告 (W293) | Low  | Blank line contains whitespace            |
| 27 | 代码坏味道 - 警告 (W293) | Low  | Blank line contains whitespace            |
| 29 | 代码坏味道 - 警告 (W293) | Low  | Blank line contains whitespace            |
| 33 | 代码坏味道 - 警告 (W293) | Low  | Blank line contains whitespace            |
| 52 | 代码坏味道 - 警告 (W293) | Low  | Blank line contains whitespace            |
| 60 | 代码坏味道 - 警告 (W293) | Low  | Blank line contains whitespace            |
| 66 | 代码坏味道 - 警告 (W293) | Low  | Blank line contains whitespace            |

### 文件: `src/web_api/core/security.py`

| 行号 | 问题分类                         | 严重程度 | 问题描述                                                                |
| -- | ---------------------------- | ---- | ------------------------------------------------------------------- |
| 1  | 导入优化 - 未排序的导入                | Low  | Import block is un-sorted or un-formatted                           |
| 8  | 代码坏味道 - Ruff特有规则 (RUF013)    | Low  | PEP 484 prohibits implicit `Optional`                               |
| 18 | 代码坏味道 - Return语句不规范 (RET504) | Low  | Unnecessary assignment to `encoded_jwt` before `return` statement   |
| 23 | 代码坏味道 - Return语句不规范 (RET504) | Low  | Unnecessary assignment to `decoded_token` before `return` statement |

