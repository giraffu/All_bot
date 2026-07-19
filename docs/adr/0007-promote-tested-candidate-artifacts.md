# ADR 0007：测试候选产物按原 digest 晋级 main

- 状态：Superseded by ADR 0008
- 日期：2026-07-19
- 取代：ADR 0005 中“candidate 不可晋级、main 必须重新构建复测”的结论
- 修订：ADR 0003/0004 中“生产与测试必须同一 Git SHA”的表述；新契约是同一 artifact digest/checksum，artifact source SHA 保持候选 SHA，main bundle 另记 main SHA

## 背景

测试列车已经对最终组合候选的容器和 Public Web 字节做了真实部署、门禁、回滚演练和人工验收。合入 main 后再构建、再部署测试会产生第二份未经原验收的二进制，还把正式发布变成长链路，并允许“main 状态写成功但实际容器未替换”的假更新。

## 决策

- `codex/test-train` 的最终 candidate 先 `freeze`。冻结保存候选 bundle descriptor digest 和完整 artifact digest/checksum 集，阻止后续候选混入该批次。
- `approve-release` 重新读取测试站真实运行态；测试过的 artifact 记 `verified`，按 direct 策略免测试的管理 artifact 记 `approved-direct`。批准记录作为不可覆盖 OCI artifact 发布。
- 合入 main 后，promotion CI 只验证候选是 main 祖先、整棵 Git tree 完全一致、bundle/批准记录/字节相互匹配。它复制原 manifest 引用和 Public Web tar，禁止 build、测试站部署和 Web 重打包。
- main bundle 以 main SHA 为键，记录候选 SHA、候选 bundle digest 和批准记录 digest。artifact 的 `source_sha`/OCI revision 不改写，生产只消费 main-channel bundle 中批准过的精确 digest。
- `release.py deploy-module` 默认一次锁定最新受保护 `origin/main` 完整 SHA，机器扩张依赖集合，执行完整生产 preflight 和事务。只有实际容器 RepoDigest、健康状态与配置 revision 都一致时才返回 `no-change`。
- 生成入口 artifact 触发整次事务进入生成维护；Dashboard、QQCC 配置后台、Payment、Paid Group Bot 和 Public Web 单独发布保持 rolling。migration、部署契约和未知影响仍强制完整维护、备份与单 Alembic head。
- test/prod 继续共用同一镜像；秘密和环境身份只存在于 `/etc/allbot/test.env`、`/etc/allbot/prod.env`、Compose overlay 或 Web runtime config。CI 检查构建上下文、Dockerfile/Image Config.Env 和 Web dist。
- 首期只覆盖 control-plane 和 Public Web。LAN AIO/RunPod 继续使用单卡 operator/canary 流程。

## 后果

正式发布不再重复测试环境流水线，生产运行的 digest/checksum 与批准候选完全相同。main merge 只承担受保护代码事实源和晋级索引身份；任何 tree 变化、证据缺失或 digest 不一致都会要求产生新 candidate。每次真实生产 mutation 仍需 `--confirm-prod` 和用户当次明确授权。

## 参考

- `scripts/test_train_release.py`
- `scripts/release_promotion_v2.py`
- `scripts/release.py`
- `.github/workflows/promote-tested-candidate.yml`
- `docs/子模块_Git不可变发布_git_immutable_release.md`
