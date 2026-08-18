---
name: allbot-codebase-design
description: "AllBot 代码库架构设计词汇与 seam 选择指南。设计/重构模块接口、移动职责、改善可测试性、评估浅封装、审查 core/service/router/worker 分层，或其它技能需要 module/interface/seam/adapter/depth/leverage/locality 词汇时使用。"
---

# AllBot 代码库设计词汇

本技能提供统一架构语言，用来评价模块是否值得存在、接口是否过宽、seam 是否放对，以及测试是否穿过了正确接口。

## 1. 固定术语
- **Module**：有 interface 和 implementation 的东西，可大可小，可以是函数、类、包、服务或跨层能力切片。
- **Interface**：调用方必须知道的一切，包括参数、返回、错误、顺序约束、配置、性能特征和副作用。
- **Implementation**：module 内部实现细节。
- **Seam**：可以替换行为而不改调用点的位置；AllBot 常见 seam 是 provider/capability、dependencies 参数、router/service 边界、worker phase helper。
- **Adapter**：填入 seam 的具体实现，例如 R2 storage adapter、billing provider、Central API client、测试 fake。
- **Depth**：小 interface 后面承载的行为量。深模块让调用方学得少、得到多。
- **Leverage**：深模块给调用方带来的复用收益。
- **Locality**：深模块给维护者带来的定位收益，修一次影响所有调用点。

## 2. AllBot 架构映射
- `src/core/` 只能依赖内部协议、domain config、provider/capability 或显式 dependencies；不得导入 Telegram `Update`、Web `Request` 或基础设施实现。AST 门禁禁止 core 直接 import `config`、`httpx`、`PIL`、SQLAlchemy、`src.database`、`src.services`、FastAPI 和 Telegram；媒体路径/处理 adapter 位于 `src/media_paths.py`、`src/media_processor.py`。
- 审查现状时必须区分两层证据：没有 Telegram/FastAPI 平台对象只证明入口对象隔离；若仍直接依赖 `config`、SQLAlchemy、HTTP client、PIL/subprocess 或默认 provider，必须继续记录为基础设施隔离债务，不能把规范当现状。
- Task core facade 应保持小 interface；复杂输入准备、billing、submission、side effect、runtime cleanup 放到实现层或 builder。
- Billing core、task core、Gallery feed、worker patcher 都应让测试和调用方穿过同一个 seam。
- Worker 大函数应按健康/控制面、Central 上报、预取、输入准备、workflow 执行、结果物化、上传/回报等阶段聚合；`ComfyAgent` 应保持 wiring/lifecycle shell，不要把每个 helper 做成只转发一行的浅模块。
- Web API router 应薄，展示转换放 presenter/service；数据库事务和对象存储探测不要混在长事务里。

## 3. 设计检查
- 删除测试：假想删除该 module。如果复杂度只是回到很多调用方，它有价值；如果什么也没丢，它可能只是浅封装。
- 接口检查：能否减少方法、参数、隐式顺序、全局状态和 caller 必须知道的异常。
- Seam 检查：只有一个 adapter 时不要急着抽象；至少有测试 fake、环境差异或可替换实现时 seam 才更有价值。
- 测试检查：如果测试必须 mock 私有函数或查内部表才能验证行为，module interface 可能放错了。
- AI 可导航性检查：未来 Codex 是否能从技能/文档/入口函数快速找到真实事实源。

## 4. 与其它技能配合
- `allbot-tdd` 使用本技能选择测试 seam。
- `allbot-diagnosing-bugs` 在“没有正确回归 seam”时使用本技能判断架构改造方向。
- `backend-code-review` 和 `allbot-code-analyzer` 在架构审查时使用本技能术语输出问题。
- 触发核心边界、入口职责或领域词汇变化时，继续调用 `allbot-kb-auto-updater`。
