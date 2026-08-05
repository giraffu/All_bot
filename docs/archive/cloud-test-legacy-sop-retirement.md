# 云测试旧发布流程退役说明

云测试曾使用源码同步、目标机 Compose build、维护式整栈脚本和专用重建脚本。
这些入口在发布模型收敛为“完整 main SHA 构建明确模块、精确 digest 单模块部署”
后退出活跃 SOP。

已退役入口包括：

- `scripts/safe_deploy_cloud_test.sh`：文件已删除。
- `scripts/update_cloud_test_with_maintenance.sh`：仅保留 fail-fast 退役壳。
- `scripts/migrate_local_test_to_cloud_containers.sh`：仅保留 fail-fast 退役壳。
- rsync 源码、目标机 build、旧 cloud-test Compose 的自由 service 重建。
- 临时 PornMaster Flux2 test AIO helper：文件与对应 execution profile 已退役。

上述历史入口不得执行，也不得从 Git 历史恢复到当前 SOP。当前入口为
`scripts/release.py build/deploy/status/rollback`；GPU/LAN 使用各自受控 operator。
旧流程的完整文本仍可通过删除前 Git 历史追溯，退役发布重构的关键提交为
`88318c1bedf3cd036ff0169314aef3af7b8c0645`。
