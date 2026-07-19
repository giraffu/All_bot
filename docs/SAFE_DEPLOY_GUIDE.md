# AllBot 发布入口

截至 2026-07-13，代码发布的唯一受支持入口是 Git SHA + 不可变镜像发布器：

```bash
scripts/release.py plan --env test --sha <full-sha>
scripts/release.py deploy --env test --sha <full-sha> --execute
scripts/release.py deploy --env prod --sha <full-sha> --execute --confirm-prod
scripts/release.py rollback --env test|prod --to <full-sha> --execute
```

完整契约、配置变更、测试验收、生产晋级与回滚流程见
`docs/子模块_Git不可变发布_git_immutable_release.md`。

旧 `update_cloud_*` 同步脚本已经 fail closed；`safe_deploy_cloud_test.sh` 与 `migrate_local_test_to_cloud_containers.sh` 也已退役并固定退出，旧 cloud-test compose 仅作历史取证，不能作为回滚或新代码发布入口。正式与测试控制面都只能消费不可变候选/晋级 bundle；真实环境变量只保存在 `/etc/allbot/test.env` 与 `/etc/allbot/prod.env`，代码发布不得修改或同步它们。

本地主服务器的旧 `safe_deploy.sh` 仅保留给云正式整体故障时的临时灾备，必须按 `docs/子模块_本地正式灾备切换_local_prod_fallback.md` 单独授权执行。
