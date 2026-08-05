# LAN GPU 运行态历史退役说明

旧版 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` 长期累积了
节点 IP、GPU UUID、容器名、某次 current mapping、故障卡处置、canary、磁盘清理
和逐日切换记录。随着 LAN AIO catalog v2 与 XDG current/history ledger 成为事实
源，这些快照继续放在活跃 SOP 会与 live 状态冲突。

本轮将活跃文档收敛为事实源、隔离、artifact/cache、只读核对、单槽 mutation 和
恢复边界。历史全文可从重写前 Git revision
`90c921b7acff6650ca5bf15e305e5a56bc759143` 读取。后续一次性节点探测、operation
结果和事故证据进入 XDG history、`logs/` 或专项 archive，不再追加回活跃文档。

已删除的临时 cloud-test PornMaster helper 与退役 FP8 execution profile不得从
历史命令恢复；新候选必须进入当前 fleet catalog，并走统一 disabled canary。
