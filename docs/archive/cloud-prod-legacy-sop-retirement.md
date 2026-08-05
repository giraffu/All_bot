# 云正式旧发布流程退役说明

云正式曾使用 rsync、目标机 Compose build、源码 bind mount、维护式组合脚本、
release bundle/test evidence 和按服务手工替换。当前发布模型已经收敛为：

1. 从受保护 main 的完整 SHA 构建明确 catalog 模块。
2. 一次向明确环境部署一个精确 digest。
3. prod mutation 显式携带 `--confirm-prod`。
4. 失败只恢复目标模块；migration 失败保留现场。

旧流程不得从 Git 历史恢复为当前 SOP。重写前的现场、拓扑快照与迁移说明可从
Git revision `90c921b7acff6650ca5bf15e305e5a56bc759143` 追溯。后续部署结果、
资源快照、canary 和事故证据进入 `docs/release_evidence/`、`logs/` 或专项
archive，不追加回活跃控制面文档。

活跃仓库不再保留旧 `deploy/docker-compose-cloud-prod.yml`。历史
`scripts/safe_deploy_cloud_prod.sh` 与 `scripts/cleanup_cloud_test_for_prod.sh`
只保留 fail-fast 退役壳，不能用于构建、启动或删除环境。
