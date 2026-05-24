# Compat / Seam 退出表

本表用于跟踪当前仓库内仍保留的兼容层、测试 seam 与过渡导出，避免“知道是历史层但没人敢删”。

## 已在本轮删除

| 对象 | 旧用途 | 依赖方 | 删除前置条件 | 实际动作 |
| --- | --- | --- | --- | --- |
| `src/handlers/fsm/video_lora_fsm.py` | 旧 `video_lora_fsm` 模块的 compat re-export | 仅剩兼容测试 | 调用方与测试退出旧模块路径 | 已删除，统一改走 `image_to_video_fsm.py` |
| `conversation_states.VideoLoraState` | 旧图生视频状态别名 | 仅剩兼容测试 | 所有调用方改用 `ImageToVideoState` | 已删除 |
| `image_to_video_fsm.start_video_lora` / `get_video_lora_fsm_handler` | 旧命名入口别名 | 仅剩兼容测试 | 统一入口改用 `start_image_to_video` / `get_image_to_video_fsm_handler` | 已删除 |

## 仍保留的 compat / seam

| 对象 | 当前用途 | 依赖它的调用方或测试 | 删除前置条件 | 预计删除阶段 |
| --- | --- | --- | --- | --- |
| `src/handlers/fsm/image_to_video_fsm.py:start_custom_video_compat` | 承接 `custom_video_fsm` 的 legacy 命名入口 | `src/handlers/fsm/custom_video_fsm.py` | `custom_video_fsm` 入口统一改为新的 flow 命名，不再导出 compat 名 | `D2` 后续轮次 |
| `src/handlers/fsm/custom_video_fsm.py:start_custom_video` | `/custom_video` 旧入口别名，对外保持稳定命令名 | Telegram 菜单与 callback `fsm_start_custom_video` | 明确 `/custom_video` 是否长期保留为独立产品入口；若仅是图生视频变体，可与统一入口继续收口 | `D2` 后续轮次 |
| `src/web_api/routers/users.py:invalidate_affiliate_redeem_cache_after_commit` | 仅为旧 patch 路径保留的 re-export | 旧集成测试 / service patch 习惯 | 相邻测试统一 patch `user_affiliate_redeem_api_service.py` 或 `affiliate_redeem_service.py` | `A3` + `D2` |
| `src/services/payment_fulfillment_service.py:LogService` 导入注释 | backward-compatible test patch target，便于旧支付/affiliate 测试稳定 patch | 相邻支付履约测试 | 测试改贴 `log_service` 或更稳定的 service/helper 边界 | `A3` + `D2` |
| `src/constants.py:MODE_IMAGE_TO_VIDEO = MODE_VIDEO_LORA` | 兼容历史任务类型值，避免旧记录/旧 payload 失配 | 历史任务类型、旧 apply-context、统计与计费链路 | 核对任务历史、gallery apply-context、计费与展示层对旧 `video_lora` 值的容忍度后，再做数据兼容迁移 | `B4` 之后单独评估 |

## 删除原则

1. 先迁调用方与测试，再删 compat 导出。
2. 优先让测试 patch helper/service 边界，不再绑定 router 或 façade 私有符号。
3. 删除 compat 后必须补 focused tests，防止回滚式复活。
