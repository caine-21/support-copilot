# Customer Context Beta 本地结构化评测

- 运行时间：`2026-07-31T04:27:50+08:00`
- 基础 commit：`efea70b29ebc87c0e870f492cadb57a479b15032`（working tree dirty：`true`）
- tracked working tree dirty：`false`
- 源码快照 SHA-256：`a3c1b0b827d1fee2124a739253f7dff8412a917b027cce8d8b3c53e7864de20d`
- 数据版本：`customer-context-beta-v2`
- 数据 SHA-256：`a3d30ed655290a92acb4a78eb0995048fdde431b9d18e65a0f099c918e3b0408`
- 运行方式：`deterministic_no_service`；provider：`none`
- Oracle 来源：Codex-assisted labels derived from the user-approved contract and corrected against the preserved v1 run; not customer-support expert annotation.

## 汇总

- 场景：30 条；合同一致：30 条；不一致：0 条。
- 路由一致：30 / 30。
- 自动回复：4 条；错误自动回复：0 条。
- 重复运行：2 次；确定性决策一致：true。
- 达到退出条件：true。

## 场景分布

| 类型 | 总数 | 合同一致 |
|---|---:|---:|
| `complete_low_risk` | 6 | 6 |
| `conflicting_sources` | 5 | 5 |
| `existing_high_risk` | 3 | 3 |
| `missing_required_field` | 5 | 5 |
| `stale_required_field` | 4 | 4 |
| `ticket_override_attempt` | 3 | 3 |
| `unknown_or_not_applicable` | 4 | 4 |

## 退出条件

- 通过：`all_30_records_complete`
- 通过：`missing_fields_never_auto_reply`
- 通过：`conflicting_fields_never_auto_reply`
- 通过：`stale_fields_never_auto_reply`
- 通过：`ticket_override_never_auto_reply`
- 通过：`existing_high_risk_rules_match`
- 通过：`erroneous_auto_reply_zero`
- 通过：`deterministic_repeat_matches`
- 通过：`every_escalation_has_reason`
- 通过：`all_oracles_match`

## 失败案例

本次没有合同不一致案例。

## Oracle 修正与修复迭代

- Oracle 修正：3 条；v1 数据与初次失败报告均保留。
- 有记录的修复迭代：2 条。

## 证据边界

Automated tests plus a Codex-assisted deterministic local structured evaluation over synthetic fixtures. No external support-agent review, real customer data, Shadow Mode, pilot, production traffic, or business-effect measurement.

## 可复现命令

```powershell
cd D:\ehe\support-copilot
py -m agent.customer_context_eval --tag <new-tag>
```

## 尚未验证

- 开发者人工复核表尚未填写。
- 未经独立客服人员复核。
- 未使用真实客户数据、线上流量或真实 provider 输出。
- 未实施 Shadow Mode、试点、生产运行或 ROI 评估。
