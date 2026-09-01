---
name: allbot-company-operations
description: "管理 AllBot 公司主体、税务、支付/银行对账、会计账套、成本、网站备案和私密资料。用户询问公司运营、报税、发票、流水、记账/月结、对公付款、商户平台或企业证件时必须使用。"
---

# AllBot 公司运营

本 Skill 管理法律主体与现实资金，不替代产品订单账本。按需读取：

| 任务 | 文档 |
| --- | --- |
| 总览、资料入口、月结 | `docs/company_operations/00_INDEX.md` |
| 营业执照、主体、账号/门户、备案 | `docs/company_operations/01_主体账户与备案.md` |
| 个税、增值税、企业所得税、征期、月账与季报衔接 | `docs/company_operations/02_税务申报与合规日历.md` |
| 中国银行、支付宝/微信、收退款、提现在途与对账 | `docs/company_operations/03_资金银行与支付对账.md` |
| 新账套、科目、凭证、月结、发票与成本 | `docs/company_operations/04_会计账簿与成本凭证.md` |
| 密码、支付密钥、证件、证据与账务操作日志 | `docs/company_operations/05_本机私密资料与证据库.md` |
| ICP、隐私、AI/算法备案与内容标识 | `docs/company_operations/06_网站与AI服务合规.md` |

支付代码/履约叠加 `allbot-billing-auth`；部署或 secret mutation 叠加
`allbot-ops-deployment`。税率、期限和备案办理前查主管机关。

## 工作流与红线

1. 先运行 `python3 scripts/company_operations_vault.py check --json`；私密资料位于
   `${XDG_CONFIG_HOME:-~/.config}/allbot/company-operations/`，只按任务读取且不打印。
2. 银行/渠道导出是资金事实源，订单、合同和发票用于勾稽；税种、征期和备案以主管
   机关当次页面为准，状态记录观察时间与证据。
3. 密码、E 盾 PIN、私钥和证书不得进入 Git、docs、聊天、日志或第三方服务；只报告
   类别、尾号、配置状态和待办。
4. 银行转账、报税、开票、退款、商户/备案提交和凭据轮换是外部 mutation；执行前
   必须确认具体对象、金额/期间和动作。经办与复核分离，E 盾交易由人核对。
5. 流水和凭证只追加/冲销。每月关联订单、渠道、银行、发票与分录；申报保存草稿、
   回执、缴款和复核证据。
6. Git 只存稳定规则；金额、凭证、余额和时间线进入私密 `accounting/logs/`。

## 最小验证

运行保险库检查和 `scripts/doc_quality_checker.py`；真实账套核对余额、报表与结账状态，
税务口径当次查主管机关。
