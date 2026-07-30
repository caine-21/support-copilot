# Customer Context Beta 开发者人工复核表

> 状态：待填写。填写前不得声明已完成开发者人工复核或用户验证。

| Case | 系统决定 | 判断依据 | 我的判断 | 是否接受 | 修改原因 |
|---|---|---|---|---|---|
| `CCB-001` | `ESCALATE_L1` | existing_policy_requires_human; fields=plan |  |  |  |
| `CCB-004` | `AUTO_REPLY` | customer_context_ok; fields=plan, role, permissions, account_status |  |  |  |
| `CCB-007` | `ESCALATE_L1` | customer_context_missing; fields=plan |  |  |  |
| `CCB-012` | `ESCALATE_L1` | customer_context_conflicting; fields=plan |  |  |  |
| `CCB-017` | `ESCALATE_L1` | customer_context_stale; fields=plan |  |  |  |
| `CCB-021` | `ESCALATE_L1` | customer_context_unknown; fields=plan |  |  |  |
| `CCB-025` | `ESCALATE_L1` | ticket_context_override_attempt, customer_context_plan_mismatch; fields=plan |  |  |  |
| `CCB-028` | `ESCALATE_L1` | existing_policy_requires_human; fields=plan, contract_status, account_status |  |  |  |
| `CCB-029` | `ESCALATE_L2` | existing_policy_requires_human; fields=none |  |  |  |

本次自动评测没有系统失败案例时，不另造失败案例；如后续运行失败，应把原失败记录加入下一版复核表。
