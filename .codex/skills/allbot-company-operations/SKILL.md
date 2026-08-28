---
name: allbot-company-operations
description: "管理 AllBot 公司主体、证照、税务申报、支付宝/微信商户、银行与对账、会计账簿、成本报销、网站/AI 合规备案和本机私密凭据。用户询问公司运营、报税、发票、流水、账本、对公付款、商户平台、ICP备案或企业证件时必须使用。"
---

# AllBot 公司运营

本 Skill 管理法律主体与现实资金，不替代产品灵石/订单账本。只读命中文档：

| 任务 | 文档 |
| --- | --- |
| 总览、资料入口、月结 | `docs/company_operations/00_INDEX.md` |
| 营业执照、主体、账号/门户、备案 | `docs/company_operations/01_主体账户与备案.md` |
| 个税、增值税、企业所得税、征期 | `docs/company_operations/02_税务申报与合规日历.md` |
| 中国银行、支付宝/微信、收退款、对账 | `docs/company_operations/03_资金银行与支付对账.md` |
| 会计账、发票、境内外成本、住宅费用 | `docs/company_operations/04_会计账簿与成本凭证.md` |
| 密码、支付密钥、证件与保险库 | `docs/company_operations/05_本机私密资料与证据库.md` |
| ICP、隐私、AI/算法备案与内容标识 | `docs/company_operations/06_网站与AI服务合规.md` |

产品支付代码/RSA2/履约叠加 `allbot-billing-auth`；部署或正式 secret mutation
叠加 `allbot-ops-deployment`。税率、优惠、期限和备案要求办理前查主管机关最新页面。

## 工作流与红线

1. 先运行 `python3 scripts/company_operations_vault.py check --json`；不要打印文件
   内容验证。当前资料位于
   `${XDG_CONFIG_HOME:-~/.config}/allbot/company-operations/`，只按任务读取单文件。
2. 银行/支付平台导出是资金事实源；本地订单、合同、发票和报销单用于勾稽。税种、
   征期和备案状态以主管机关当次页面为准，更新状态时附观察时间和证据。
3. 真实密码、支付密码、E 盾 PIN、私钥和证书不得进入 Git、docs、聊天、命令行、
   日志或第三方服务。正常回答只报告类别、尾号、是否配置和待办，永不回显值。
4. 银行转账、报税、开票、退款、商户/备案提交和凭据轮换是外部 mutation；执行前
   必须确认具体对象、金额/期间和动作。经办与复核分离，E 盾交易由人核对。
5. 流水和凭证只追加/冲销，不静默覆盖。每月完成产品订单、渠道交易/退款、结算、
   银行入账、发票和会计分录的关联；申报保存草稿、回执、缴款和经办/复核证据。
