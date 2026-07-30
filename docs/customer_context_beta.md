# Customer Context Beta

## 当前完成范围

本 Beta 使用合成的本地客户资料，在现有路由和 grounding 门控上增加一个确定性检查：只有当前请求依赖的客户字段处于可用状态，并且字段值满足套餐与权限约束时，才允许继续考虑 `AUTO_REPLY`。

主链路：

```text
本地合成客户资料
→ 校验并标准化字段
→ 根据当前 KB 结果确定相关字段
→ 检查缺失、未知、不适用、冲突和过期状态
→ 检查字段是否允许参与自动回复判断
→ 检查套餐与权限约束
→ 与现有风险、grounding 和路由规则合并
→ 保存原因码、使用字段、阻断字段和逐条运行记录
```

确定性 L2 规则已经要求人工处理时，不再读取客户字段作为路由依据。客户在工单中写出的套餐、地区或角色也不会替换系统提供的字段值。

## 数据结构

Customer Context 包含六个业务字段：

- `plan`
- `region`
- `role`
- `permissions`
- `contract_status`
- `account_status`

每个字段都必须包含：

- `value`
- `status`
- `source`
- `updated_at`
- `allowed_for_auto_reply`

信息状态固定为：

| 状态 | 含义 | 相关请求能否用于自动回复判断 |
|---|---|---|
| `known` | 有明确值 | 还需 `allowed_for_auto_reply=true` |
| `missing` | 数据源没有该字段 | 否 |
| `unknown` | 已检查但无法确定 | 否 |
| `not_applicable` | 该记录明确不适用 | 否；不能当作 unknown |
| `conflicting` | 多个来源值不一致 | 否；不能静默选一个 |
| `stale` | 字段已明确过期 | 否 |

## 原因码

原因码写入 `customer_context_decision` 和 run ledger：

- `customer_context_missing`
- `customer_context_unknown`
- `customer_context_not_applicable`
- `customer_context_conflicting`
- `customer_context_stale`
- `customer_context_not_authorized`
- `customer_context_plan_mismatch`
- `customer_context_permission_denied`
- `ticket_context_override_attempt`
- `existing_policy_requires_human`

## 固定评测合同

原始 v1 数据保存在 `data/customer_context_beta_v1.json`，SHA-256 为：

```text
577bd3afaee52a6ec36c1dd3f99f533adff0117fcedcb10d7ad9bd8904de95bc
```

第一次运行保留了 27/30 的结果。v2 没有删除或替换失败案例，而是在 `data/customer_context_beta_v2_oracle_corrections.json` 中记录三条 oracle 修正；v2 组合哈希为：

```text
a3d30ed655290a92acb4a78eb0995048fdde431b9d18e65a0f099c918e3b0408
```

Oracle 来自用户批准的业务合同和 Codex 辅助整理，不是客服专家标注。

最终 v2 报告：

- 30/30 场景产生结构完整的逐条记录；
- 30/30 与版本化 oracle 一致；
- 4 条 `AUTO_REPLY` 候选；
- 0 条错误自动回复；
- 两次运行的确定性决策一致；
- 缺失、冲突、过期和工单覆盖系统事实的场景均没有自动回复。

权威逐条数据位于：

- `data/customer_context_beta/evidence/customer_context_beta_2026-07-31-final-v2.json`
- `data/customer_context_beta/evidence/customer_context_beta_2026-07-31-final-v2.md`

## 可复现命令

```powershell
cd D:\ehe\support-copilot
py -m agent.customer_context_eval --dataset-version v2 --tag <new-tag>
```

该入口使用 `deterministic_no_service` 模式和固定工具输出，不读取真实客户资料，不调用外部模型，也不把 fixture 当成 provider 输出。

## 证据分类

1. 自动化测试：验证结构、状态、权限、套餐、文本覆盖、现有 L2 规则、工作流集成和报告字段。
2. Codex 辅助本地结构化评测：固定 30 场景通过真实 `run_agent` 入口运行，工具边界使用合成 fixture，保存逐条记录。
3. 开发者人工复核：`developer_review_2026-07-31-final-v2.md` 已生成但尚未填写，因此当前不能声明完成开发者走查。

## 当前限制

- 没有真实 CRM、客服平台或客户数据。
- 没有独立客服人员复核。
- 没有 Shadow Mode、人工审批队列、真实自动发送或生产部署。
- 没有线上流量、业务效果或 ROI 数据。
- 报告记录基础 commit `51154a8` 和本轮源码快照哈希；由于本轮按要求不自动提交，最终 commit-pinned 复跑仍需在 Reviewer 审核并提交代码后执行。
