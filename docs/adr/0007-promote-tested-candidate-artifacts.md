# ADR 0007：测试候选产物按原 digest 晋级 main

- 状态：Accepted
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
- test/prod 继续共用同一镜像；`/etc/allbot/test.env` 与 `/etc/allbot/prod.env` 是环境私密配置的唯一事实源。发布器按 `deploy/service-env-contract.yml` 生成 `600` 权限的 `/var/lib/allbot/config/<env>/<revision>/<service>.env`，容器只获得自己的投影；`release.env` 只记录 digest、SHA、配置 revision 与投影路径。
- `ALLBOT_ENV` 必填，`BOT_TYPE` 只能由它派生；运行代码禁止自动加载 `.env`、读取 `_TEST` 别名或使用秘密/环境身份默认值。Public Web 继续晋级同一 tar，并在部署时生成环境独立的 `allbot-runtime-config.js`。
- 代码发布先从目标主机只读计算 env 与逐服务 revision。发现漂移必须先执行 `config-plan`/`config-apply`；配置契约变化或未知键影响全部服务并强制完整维护。首次投影切换备份数据库和原 env，失败恢复旧投影与旧 digest；恢复不完整时保留维护。
- CI 检查构建上下文、运行源码、Dockerfile/Image Config.Env、镜像应用文件系统和 Web dist，并用同一 digest 分别解析 test/prod 哨兵身份。
- 秘密轮换分两阶段完成。`credential-isolation-complete` 之前，每次正式快捷发布必须显式提交 `--accept-pending-secret-rotation --reason --approved-by`，风险接受写入发布状态；轮换完成后该豁免失效。
- `scripts/verify_remote_secret_isolation.py` 用同一随机 challenge 在 test/prod 目标机本地计算 HMAC，只传回键名与摘要比较结果；禁止复制或输出秘密原文。Agent Token 的实际轮换仍按测试 Worker→正式控制面→正式 Worker 顺序交给既有 GPU operator。
- 轮换完成状态只能通过 `release.py credential-isolation-complete` 写入。命令要求一小时内生成的无值证据、全部目标健康、旧凭据已撤销、批准人、`--confirm-prod` 与 `--execute`，并在 test/prod 配置根保存不可变审计；不得手工创建状态 marker。
- 首期只覆盖 control-plane 和 Public Web。LAN AIO/RunPod 继续使用单卡 operator/canary 流程。

## 后果

正式发布不再重复测试环境流水线，生产运行的 digest/checksum 与批准候选完全相同。main merge 只承担受保护代码事实源和晋级索引身份；任何 tree 变化、证据缺失或 digest 不一致都会要求产生新 candidate。每次真实生产 mutation 仍需 `--confirm-prod` 和用户当次明确授权。

## 参考

- `scripts/test_train_release.py`
- `scripts/release_promotion_v2.py`
- `scripts/release.py`
- `.github/workflows/promote-tested-candidate.yml`
- `docs/子模块_Git不可变发布_git_immutable_release.md`
