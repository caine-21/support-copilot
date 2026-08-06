# CANONICAL_FACTS — support-copilot

> 权威事实快照。所有面试数字只能引用本文件标注为 canonical 的结果。
> 规则：选「当前 HEAD 最容易复现、证据最完整」的版本，不选数字最高的版本。
> 标签：A=源码事实 / B=推断 / C=未实现。

## Project
`support-copilot` — SaaS 客服智能分诊系统（确定性路由工作流 + LLM 子任务）

## Canonical commit
- 工作树：`main` @ `56dfeb9f3a07d3fa8f125598b47b63623cdcf039`（2026-08-07 核查）
- ⚠️ 工作树含未提交改动：`agent_loop.py` / `grounding_compiler.py` / `llm.py` / `run_ledger.py` / `README.md` / `requirements.txt`（用户未提交）+ 未跟踪 tool 文件（`function_calling.py`/`tool_loop.py`/`tooling.py`/`support_mcp_server.py`/`tool_eval.py` 等）
- **Canonical 评测证据**：`data/reports/report_epistemic-r3.json`（README 引用的复核快照）

## Verified date
2026-08-07

## Current architecture
确定性路由工作流：`run_agent(ticket_text, ticket_id, user_id)` →
Phase1 并行（classify_intent | kb_search | history_lookup | tone_check）→
early-L2 正则门（sla_signal / hidden_cancel_signal）→
`draft_reply` → `grounding_compiler` → `synthesize()`（纯函数 3 规则）→ 反射循环（≤2 轮）。
可选 `SUPPORT_AGENT_MODE=tool_loop` 有界只读工具循环；旁路只读 multi-agent shadow。
Decision 类型：字符串常量 `AUTO_REPLY` / `ESCALATE_L1` / `ESCALATE_L2`（**无 ABSTAIN**，`reasoner.py`）。
持久化：仅文件系统（`data/runs/<run_id>/*.jsonl` append-only ledger + `data/reports/report_*.json`）。
**无数据库、无 HTTP API、无动作执行层**（截至本轮升级前）。

## Current maturity
离线 POC。有最完整的评测/安全组合（6 处确定性 gate + run ledger + assumption replay + RAGAS + 100-case 冻结回归 + shadow），但无真实工单流、无发送、无线上闭环。

## Canonical evaluation
100-case 冻结回归（`data/test_tickets.json`，85 baseline + 15 adversarial），expected 只标 action/min_confidence/tone/churn_risk_min。**非真实工单**。

## Dataset
`data/test_tickets.json` — 100 条，expected 分布 {AUTO_REPLY:24, L1:45, L2:31}；difficulty 分布 easy 24 / medium 28 / hard 29 / edge 4 / adversarial 15。

## Run command
- 全量离线 pytest：`py -B -m pytest tests -q`（49 个用例，全部离线可跑，无真实 API 依赖）
- canonical eval：`py -m agent.eval --tag <tag>`（100 条真实 LLM 调用，需 `DEEPSEEK_API_KEY`/`GROQ_API_KEY`）

## Result artifact
`data/reports/report_epistemic-r3.json`（canonical）— summary {total:100, passed:95, pct:95.0}；metrics {action_accuracy:0.96, l2_recall:1.0, unsafe_auto_reply_rate:0.0, intent_accuracy:0.0}。

## Current verified metrics
| 指标 | 值 | 来源 | 分子/分母 |
|---|---|---|---|
| 通过率 | 95/100 (95%) | report_epistemic-r3.json | passed=95 / total=100 |
| Action accuracy | 0.96（base 0.96 / adv 0.93） | 同上 | 96/100 |
| L2 recall | 1.0 | 同上 | 31/31（本快照） |
| Unsafe AUTO_REPLY | 0.0 | 同上 | 0/… |
| intent_accuracy | 0.0（未评分） | 同上 | intent_scored=0（数据集无 expected intent） |

⚠️ 多源互斥现状：`report_latest.json`（6/15）= 98/100/0.98；CLAUDE.md 声称 v22=98%/L2 100%；README 引用 epistemic-r3（95/100）。**canonical = epistemic-r3**（README 引用、证据完整）。其余为历史快照，引用时必须标注。

## Known limitations
- 无真实工单/发送/客服验证；faithfulness（RAGAS）非确定 48–73% 跨 run 波动
- pytest 收集 49 个用例全部离线，但 `agent/eval.py` 等脚本需真实 key
- 无 DB/HTTP/动作执行（本轮升级补齐）
- CLAUDE.md grounding 描述过时（已知 intent 走 INTENT_FAQ_MAP 命中 score=1.0，cosine 仅 unknown 路径）

## Deprecated claims
- ❌「v22 = 98% / L2 100%」（CLAUDE.md）— 与 canonical 95/100 冲突；无对应 committed report 标签
- ❌「30/30」「100%」等无来源口径
- ❌ v17 metrics 块（action_accuracy 0.55）— 早期 positional slicing 算错 baseline，不可信

## Allowed interview claims
- 「100 例冻结回归 95/100（canonical epistemic-r3 快照），action_accuracy 0.96、L2 recall 1.0、unsafe AUTO 0 —— 离线合成数据上的回归结果，非线上准确率」
- 「6 处确定性 gate + append-only ledger + assumption replay + RAGAS faithfulness（48–73%，非确定）」
- 「L2 recall 在不同快照为 0.97–1.0 波动（v22 报 0.97），说数字必须带 commit + 报告名」

## Forbidden claims
- ❌「98% 准确率 / L2 召回 100%」作为当前状态
- ❌ 把离线评测数字当线上成绩
- ❌ 声称已接入真实客服系统 / 已发送真实回复

## 本轮升级后（完成后更新）
- 新增：SQLite ticket 工作流切片（API + 持久化 + 人工审核 + mock action + 幂等），见 `service/` 与新增测试
- 更新本文件指标为含新切片的实测结果
