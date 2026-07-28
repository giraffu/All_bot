# 热点文件门禁（已退役）

旧 changed-path classifier、四级 scope、`requires_full_ci` 和 hotspot GitHub
workflow 已由 ADR 0009 取代并删除。

业务模块可以维护自己的 focused tests，但测试是否运行由任务/操作者决定，
不是 main 合入、产物构建、test 部署或 prod 部署的资格状态。新增模块测试不应
重新引入全仓 change-scope、跨模块影响推导或 required status check。
