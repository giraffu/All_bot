# ADR 0003: Git SHA 与不可变镜像同版本晋级

日期：2026-07-13

## Status

Accepted，晋级身份语义由 ADR 0007 修订：main SHA 标识发布索引，artifact source SHA/OCI revision 保持已测试候选 SHA。

## Context

历史发布通过 rsync 选择文件并在云端 build。一次发布可以混入多个提交的 `src`、Redis 锁实现、locale、workflow 或配置文件，无法证明运行依赖闭包来自同一版本，也无法原子回滚。Git checkout 本身仍不足以解决现场 build 漂移、Node/Python 工具链漂移和测试/生产产物不一致。

## Decision

- 唯一发布身份是受保护 `origin/main` 可达的完整 40 位 Git SHA。
- GitHub Actions 对该 SHA 测试一次，构建五类自有镜像和一份 Web 静态产物；自有镜像写 OCI revision/source label。
- `release.json` 固定自有及第三方镜像 digest、Web SHA256 与 CI run。运行主机只拉 digest，不 build，也不挂载应用源码。
- 测试和生产共用公共 Compose/配置 schema；真实 env 分离为 `/etc/allbot/test.env` 和 `/etc/allbot/prod.env`，非敏感 digest 写入独立 `release.env`。
- `deploy/release-policy.yml` 由 Git diff计算依赖闭包。显式 service 只能扩大范围；未知路径整栈维护；migration 要求显式升级；GPU runtime 变化阻断普通发布。
- 生产只能晋级测试环境已批准的同一 artifact digest 与 Web checksum；tree-identical main bundle 记录独立 main SHA 和候选 SHA。回滚使用旧 manifest，不重建；数据库只做 expand/contract，不自动 downgrade。

## Alternatives Considered

- 继续 rsync，但维护更完整的文件清单：清单仍会漏掉新增消费者，且非原子。
- 云端 `git pull` 后现场 build：代码版本统一，但构建工具链、依赖源和产物仍可能不同。
- 每个环境各自构建：不能证明生产运行的是测试过的二进制产物。

## Consequences

- 单模块发布仍存在，但范围由机器计算；共享核心、锁、locale 与 Worker 不可能合法地混用版本。
- 首次切换需要归档 legacy 运行态、迁移 env、配置只读 deploy key 与 GHCR read token，并演练回滚。
- GHCR、Git 和 CI 成为发布依赖；仓库不可用时只能回滚已缓存/保留的 manifest 与 digest，不能现场热改源码。
- RunPod/LAN AIO 保留专用产物门禁；其契约变化会阻断普通控制面晋级。

## References

- `docs/子模块_Git不可变发布_git_immutable_release.md`
- `scripts/release.py`
- `deploy/release-policy.yml`
- `.github/workflows/control-plane-release.yml`
