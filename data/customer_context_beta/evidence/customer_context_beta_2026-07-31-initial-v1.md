# Customer Context Beta 本地结构化评测

- 运行时间：`2026-07-31T02:34:48+08:00`
- 基础 commit：`51154a8b419abb58b4b8d96e49121304f63a224c`（working tree dirty：`true`）
- 源码快照 SHA-256：`636e5f4d9634c62171298dc6ecf157ae6af6ac399c6f10f5ecb9df7b2194ef84`
- 数据版本：`customer-context-beta-v1`
- 数据 SHA-256：`577bd3afaee52a6ec36c1dd3f99f533adff0117fcedcb10d7ad9bd8904de95bc`
- 运行方式：`deterministic_no_service`；provider：`none`
- Oracle 来源：Codex-assisted labels derived from the user-approved Customer Context Beta contract; not customer-support expert annotation.

## 汇总

- 场景：30 条；合同一致：27 条；不一致：3 条。
- 路由一致：28 / 30。
- 自动回复：4 条；错误自动回复：0 条。
- 重复运行：2 次；确定性决策一致：true。
- 达到退出条件：false。

## 场景分布

| 类型 | 总数 | 合同一致 |
|---|---:|---:|
| `complete_low_risk` | 6 | 4 |
| `conflicting_sources` | 5 | 5 |
| `existing_high_risk` | 3 | 2 |
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
- 未通过：`all_oracles_match`

## 失败案例

- `CCB-001`：expected `AUTO_REPLY`，actual `ESCALATE_L1`；失败分类：route_mismatch, reason_code_mismatch。
- `CCB-002`：expected `AUTO_REPLY`，actual `ESCALATE_L1`；失败分类：route_mismatch, reason_code_mismatch。
- `CCB-029`：expected `ESCALATE_L2`，actual `ESCALATE_L2`；失败分类：relevant_field_mismatch。

## Oracle 修正与修复迭代

- Oracle 修正：无。若需要修正，必须保留本版本并创建新数据版本。
- 评测后修复：无。

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
