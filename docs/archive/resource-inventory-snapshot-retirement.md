# 资源画像快照退役说明

旧版 `docs/子模块_系统资源与容量画像_resource_inventory.md` 混合保存了控制面
主机、数据库、Redis、LAN GPU、Telegram Local API、NAS 和某次容器状态。此类
数字会快速过期，也与 provider、XDG ledger、数据库和 live 主机的职责重叠。

本轮将活跃文档改为采集范围、证据等级、解释方法和报告格式。旧快照全文可从
重写前 Git revision `90c921b7acff6650ca5bf15e305e5a56bc759143` 追溯；后续
采集结果进入 `logs/` 或专项 archive，并记录明确时间和环境，不追加回活跃 SOP。
