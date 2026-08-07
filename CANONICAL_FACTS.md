# CANONICAL_FACTS.md — support-copilot

> 本文件是 support-copilot **唯一事实口径**。所有公开结论（README、Portfolio、简历、面试）必须与本文件一致；冲突时以本文件 + 其引用的机器可读证据为准。
> 收敛日期：2026-08-07（Commit 0B，docs-only）。
> 标签体系：`CURRENT VERIFIED` / `HISTORICAL` / `EXPERIMENTAL` / `MOCK` / `FUTURE` / `DEPRECATED` / `UNRESOLVED`。
> 规则：机器证据优先；clean commit 与 working-tree 严格分开；每个重要数字指向 commit / command / artifact。

---

## 1. Canonical identity

| 字段 | 值 |
|---|---|
| Project | support-copilot（SaaS 客服智能分诊） |
| Runtime baseline commit | `c9e1ade chore: pin bounded agent tooling baseline`（bounded tooling 已入 git，clean-room 70 passed） |
| 本文档所在 commit | Commit 0B（docs-only 收敛；runtime tree 与 `c9e1ade` 一致） |
| Verified date | 2026-08-07 |
| Current architecture label | **Deterministic routing workflow**（LLM 作子过程）+ **bounded read-only tool loop**（opt-in）+ deterministic authorization gates + **read-only Multi-Agent Shadow**（EXPERIMENTAL，非正式业务车道） |
| Current maturity label | **Local Verified Prototype**（离线评测 POC；无真实工单系统、无部署、无发送） |

---

## 2. Reproducibility Baselines

> 这是当前唯一可复现的测试基线。`60` 是历史演进证据，`70` 是当前 clean baseline。

| Baseline | Commit | Scope | Result | Meaning |
|---|---|---|---|---|
| Legacy clean | `31e409d` | committed legacy + service 切片 | **60 passed**（21–49s，离线） | pre-tooling 基线 |
| Tooling clean | `c9e1ade` | committed bounded tooling + legacy + service | **70 passed**（29–48s，离线） | **current clean test baseline** |

- 70 = 60（legacy/service）+ 10（`tests/test_agent_tooling.py`，含本地 stdio MCP spawn）。
- 验证方法：`git archive <commit>` → 全新临时目录 → `py -B -m pytest tests -q`（**离线，无 API key，无 .env，无工作树未提交文件**）。
- 实测：`c9e1ade` clean-room = **70 collected / 70 passed / 0 failed / 0 skipped / 0 warnings**（2026-08-07）。

---

## 3. What the system actually does

- **真实输入**：`ticket_text`（+ `user_id`、可选 `customer_context`）。来源为 CLI（`agent/main.py`）、Gradio（`app.py`）、离线评测（`data/test_tickets.json`、customer_context 数据集）。
- **真实输出**：`{action: AUTO_REPLY | ESCALATE_L1 | ESCALATE_L2, confidence, reason, routing_signals, grounding, intent_set, draft_reply, grounding_check, assumption_trace, assumption_replay}`。无 ABSTAIN。
- **实际控制流**（CURRENT VERIFIED）：Phase 1 并行（`classify_intent` | `kb_search` | `history_lookup` | `tone_check`）→ 确定性 early-L2 正则门 → `draft_reply` → `grounding_compiler` → `reasoner.synthesize()`（纯函数 3 规则）→ 反射循环（≤2 轮）。下一步由证据等级 + 风险信号决定，**不是模型动态决定**。
- **模型真正负责**：`classify_intent`、`tone_check`、`draft_reply`（6 条 KB closure 约束）、grounding claim 判定、customer_context 字段抽取。模型只产出数据，不持有授权。
- **确定性系统负责**：INL（确定性表，`["unknown"]` 才走 LLM）、KB（`INTENT_FAQ_MAP` 全命中 score=1.0；unknown 走 hybrid）、early-L2 正则门、grounding ratio 阈值 0.75、`context_guard`/`customer_context` entitlement、`synthesize()` 3 规则路由。
- **人工负责**：L1 / L2 即人工路径；无显式 HITL 审批环；`AUTO_REPLY` 是**决策输出**，不是**执行发送**。
- **最终动作**：**不执行**。ticket 侧副作用走 `MockTicketActionAdapter`（MOCK，仅记录，见 §8）。

---

## 4. Architecture classification

**主要架构名称：Deterministic Workflow + bounded read-only tool loop。**

- **为什么这样命名**：控制流是固定 DAG + 确定性门（`agent_loop.py` 自述 "hybrid parallel/sequential pipeline"）；`reasoner.synthesize()` 是纯函数（无 LLM 调用）。默认模式 `SUPPORT_AGENT_MODE=legacy`（`run_agent` 默认参数 None → legacy）。
- **bounded read-only tool loop**（CURRENT VERIFIED，c9e1ade）：opt-in `SUPPORT_AGENT_MODE=tool_loop`。模型可选只读工具（`search_knowledge_base` / `get_customer_context` / `get_ticket_history`），loop 有界（≤4 turns / ≤6 calls / ≤15s），最终授权仍过 `synthesize()` 确定性门；loop 不完整时**只能保留或升级**，永不解锁 `AUTO_REPLY`（`tool_loop.py` 不变式）。工具权限在代码层强制（非 READ → FORBIDDEN），非 prompt 约束。
- **为什么不是更开放的 Agent**：分诊路径可预先画成状态图；「下一步」由证据等级决定。tool_loop 只是检索的有界扩展，不改变授权。
- **为什么不是 Multi-Agent（正式车道）**：正式授权源保持单链可审计；Multi-Agent 只作为**只读 Shadow 咨询层**（EXPERIMENTAL），未证明更安全前不进入正式 Reasoner/Authorization。
- **EXPERIMENTAL**：`agent/multi_agent/`（Manager → Billing/Technical Specialist → deterministic merger）是只读 Shadow；20 例离线 eval 断言 `baseline_action_unchanged=True`，shadow 包**不可能改变正式动作**。

---

## 5. Connected implementation

| 能力 | 状态 | 入口 | 证据 |
|---|---|---|---|
| LLM 调用 | ✅ | `agent/llm.py`（LLMRouter：DeepSeek→Groq fallback，native `call_with_tools`） | 真实 provider，需 API key |
| 检索 | ✅ | `agent/kb.py`（INTENT_FAQ_MAP + unknown hybrid） | 确定性为主 |
| 有界工具调用 | ✅ committed | `agent/tool_loop.py` / `tooling.py` / `function_calling.py` | c9e1ade，clean-room 70 |
| 状态保存 | ✅ | `run_ledger.py` append-only（含 `log_tool_execution`） | `data/runs/*.jsonl` |
| Guardrail | ✅ | early-L2 正则门 / customer_context 门 / unknown_fallback 禁 AUTO | 确定性 |
| Verifier | ✅ | `grounding_compiler.py`（claim-graph，ratio 阈值 0.75；no_service 确定性路径） | 无 service 时用 fixture |
| Critic / Revision | ✅ | `agent_loop.py` 反射（≤2 轮，确定性策略） | — |
| HITL（agent 决策路径） | ❌ | 无显式审批环；L1/L2 天然人工路径 | AUTO_REPLY 不发送 |
| HITL（service 动作路径） | ✅ MOCK | `service/engine.py` review gate（approved/edited/rejected）+ `NoEvidenceGate` + idempotency | 90c16ef，见 §8 |
| Memory | ⚠️ | `agent/memory.py` 纯内存，无持久化 | 跨进程丢失 |
| Trace / Ledger | ✅ | `run_ledger.py` + assumption_trace/replay | 离线路径 |
| Shadow / Multi-Agent | ✅ EXPERIMENTAL | `agent/multi_agent/` + `multi_agent_eval.py` | 只读咨询，20 例离线 |
| 最终外部动作 | ❌ | 无发送/落库（mock adapter 仅记录） | no-send 方向 |

---

## 6. CURRENT VERIFIED — 确定性/scripted 评测（可复现，无 provider）

### ① Customer Context Beta（deterministic，provider=none）

| 字段 | 值 |
|---|---|
| Evaluation name | `customer-context-beta-2026-07-31-commit-pinned` |
| Dataset / manifest | `data/customer_context_beta_v2.manifest.json`（dataset SHA-256 `a3d30ed6…b0408`） |
| Sample count | 30（7 类场景） |
| Model / provider | `none`（deterministic_no_service，无 LLM） |
| Run command | `py -B -m agent.customer_context_eval --dataset-version v2` |
| Result artifact | `data/customer_context_beta/evidence/customer_context_beta_2026-07-31-commit-pinned.json` |
| Commit | `efea70b`（working_tree_dirty=true，tracked_dirty=false） |

**允许引用指标**：30/30 合同一致；路由一致 30/30；错误自动回复 **0**；`determinism.matched=true`；`exit_criteria_met=true`。
**诚实边界**：oracle 为 Codex-assisted labels（用户批准），**非客服专家标注**；不是业务正确性证明。

### ② Multi-Agent Shadow Eval（offline scripted，无 provider）

| 字段 | 值 |
|---|---|
| Evaluation name | `multi-agent-shadow-eval` |
| Dataset | `tests/fixtures/multi_agent_cases.json`（20 例 scripted，business_oracle / injected_behavior / expected_observation 三层） |
| Run command | `py -B -m agent.multi_agent_eval` |
| Commit | HEAD 复现成功（2026-08-07） |

**允许引用指标**：Scenario 20/20（正常 + 故障注入均产生预期观察，**不代表 Manager 次次选对**）；Manager Selection Accuracy 18/20=0.90；Multi-intent Coverage 4/5=0.80；Off/Shadow/Delta unsafe AUTO_REPLY = 0/0/0；21 个 valid specialist slice；multi-specialist 5/5 用不同 slice；missing / identical / shared-full-ticket = 0。
**绝不合并为「120-case Multi-Agent Eval」**。

### ③ Grounding Authorization Fail-Closed（Commit 1，CURRENT VERIFIED）

| 字段 | 值 |
|---|---|
| Commit | `2c13496 fix: make grounding authorization fail closed` |
| clean-room | **81 passed**（70 existing + 11 new fail-closed tests；`git archive 2c13496` → temp 复现） |
| Invariant | **Missing, empty, malformed, or failed grounding cannot authorize AUTO_REPLY; valid strong grounding remains eligible** |
| Deterministic evals | customer-context **30/30 unchanged**；multi-agent shadow **20/20 unchanged** |
| Provider 100-case model eval | **not rerun**（95/100 仍 HISTORICAL，见 §9） |

**Failure Matrix（真实 before/after，来自 characterization tests）**：

| Condition | Authorization semantics |
|---|---|
| empty draft / empty KB | AUTO forbidden |
| empty claims（含 malformed response） | AUTO forbidden |
| compiler exception | AUTO forbidden（fail-closed + 可观测日志） |
| missing / `{}` / malformed grounding_check | AUTO forbidden（`synthesize` 默认 False/0.0） |
| valid strong grounding | **AUTO still eligible**（positive control） |

Positive control 证明：valid strong grounding（claims，ratio≥0.75）仍授权 AUTO——修复未关闭正常路径。

---

## 7. Tooling（bounded read-only agent tooling，CURRENT VERIFIED）

- **已提交**：`c9e1ade`（bounded tooling baseline）。
- **内容**：`tool_loop.py`（有界只读工具循环）/ `tooling.py`（`ToolPermission`：read / reversible_write / external_or_irreversible；`ToolGateway` code-level 权限强制）/ `function_calling.py`（native function calling adapter）/ `support_mcp_server.py`（本地 stdio MCP server，read-only）/ `tool_eval.py`（编排/契约指标脚手架）。
- **默认模式**：`SUPPORT_AGENT_MODE` 未设 → `legacy`（旧路径行为不变）。tool_loop 是 opt-in。
- **只读**：当前注册工具全为 READ（`search_knowledge_base` / `get_customer_context` / `get_ticket_history`）；无 write/side-effect 工具。
- **clean-room**：`c9e1ade` = **70 passed**。
- **边界**：model 可提议回应 + 请求只读工具，**不能**选 Risk policy / grounding 校验 / customer-context 授权 / PII / 最终 action。失败/超时/loop 上限只能保留或升级，**不能解锁 AUTO_REPLY**。
- 详见 `docs/AGENT_TOOLING.md`（已纳入 git，标 verified baseline c9e1ade）。

---

## 8. Service（ticket workflow slice，MOCK）

- **已提交**：`90c16ef feat: add auditable ticket workflow slice`（clean-room 60 passed 于该 commit；现含于 70 基线）。
- **内容**：SQLite（`tickets` + `ticket_actions` append-only audit）+ FastAPI + `service/engine.py`（review gate：`ReviewRequest(approved|edited|rejected)`）+ `NoEvidenceGate`（grounding 不足时人工批准也禁止发送）+ idempotency（`ticket_id:workflow_version:action_type` UNIQUE）。
- **MOCK**：`MockTicketActionAdapter`（`create_reply`/`create_escalation` 仅记录，`{"status":"sent_mock"|"escalated_mock"}`，不接触外部系统）。真实 CRM/Zendesk 为 FUTURE。
- **决策链**：decision gate + human review + idempotency + evidence gate（ADR-002）。

---

## 9. HISTORICAL / UNRESOLVED（旧 model-evaluation 证据）

> 以下为**需真实 API key 的历史评测**，非确定性，且**未在 `c9e1ade` clean-room 中重跑**。c9e1ade 验证的是 test/tooling parity（70 passed），**不是**重新执行 requires-key canonical model eval。

| 旧结果 | 位置 | 状态 |
|---|---|---|
| 100 例正式路由 eval（epistemic-r3 / v22_rule6 / inl-coverage / rrf-hybrid / parallel-pipeline 等） | `data/reports/report_*.json` | **HISTORICAL**：需真实 provider、非确定性、数字互斥（README 95/100 vs CLAUDE.md 98% vs report L2 0.97） |
| `report_epistemic-r3.json` = 95/100（action_accuracy 0.96 base / 0.93 adv，L2 recall 1.0，unsafe AUTO 0） | `data/reports/`（gitignored） | **HISTORICAL artifact**：绑定其产生时的 commit/config（README 引用的复核快照）；**未在 c9e1ade clean-room 重跑**。引用时必须标注来源 + 未重跑 |
| RAGAS faithfulness（v17–v21） | `data/eval_reports/*_ragas.json` | **HISTORICAL**：非确定 48–73% 跨 run，LLM-as-judge 有宽松偏差 |
| v17 metrics（action_accuracy 0.55 vs passed 98%） | `data/eval_log_v17*` | **UNRESOLVED**：早期 positional slicing 算错 baseline |
| README "98% / L2 100% / 99/100 / stable" | 历史 README/CLAUDE.md | **DEPRECATED**：无 HEAD 权威快照，与可复现证据不一致 |

> 声明：**historical artifacts 是不可变证据**，可能含已被取代的术语；为保持一致性不篡改旧结果文件。

---

## 10. Reproduction commands

> 环境：Windows。**必须用 `py`**（`python` 不在 PATH）。密钥只能来自环境变量，禁止写死。

- **Environment**：`py -m pip install -r requirements.txt`
- **全量离线 pytest（CURRENT，70 passed，~30–50s）**：`py -B -m pytest tests -q`（含 tooling tests + 本地 stdio MCP spawn，**离线，无 API key**）
- **确定性/scripted canonical（可复现）**：
  - customer-context：`py -B -m agent.customer_context_eval --dataset-version v2`（默认目录；复现会新增 run 文件夹，勿覆盖 commit-pinned）
  - multi-agent shadow：`py -B -m agent.multi_agent_eval`
- **需真实 key 的历史 eval**：`py -m agent.eval --tag <tag>`（100 条真实 LLM 调用；产 HISTORICAL 报告）
- **MCP server**：`py -B -m agent.support_mcp_server`（本地 stdio）
- **Artifact verification**：校验 `data/customer_context_beta/evidence/customer_context_beta_2026-07-31-commit-pinned.json` 的 `run.git_commit==efea70b`、`determinism.matched==true`、`summary.passed==30`。
- ⚠️ 已知：`--output-dir` 自定义路径在 Windows 因 `Path.relative_to` 报错（2026-08-07 实测）；用默认目录即可。

---

## 11. Current limitations

- 无真实工单系统 / Zendesk / CRM 适配器；无真实用户；无部署。
- 无发送动作：`AUTO_REPLY` 是决策输出，不是执行；发送需外部 HITL（FUTURE）。
- 100 例正式路由 eval 依赖真实 provider，非确定，未在 `c9e1ade` 固化重跑（HISTORICAL/UNRESOLVED）。
- customer-context 与 multi-agent 评测均为合成/scripted 数据；oracle 非客服专家标注。
- 记忆（`AgentMemory`）纯内存，无持久化。
- 指标只说明：确定性门控在固定合成数据集上的正确性与回归稳定性；不能说明真实解决率 / ROI / 线上准确率。
- Grounding fail-closed invariant 已落地（Commit 1 `2c13496`）：missing/empty/malformed/failed grounding 不能授权 AUTO_REPLY；valid strong grounding 仍可（positive control）。详见 §6③。剩余边界：`grounding_compiler` 各 reason_code 未纳入运行时消费（仅测试断言），非 fail-open 风险。

---

## 12. FUTURE（未实现，不得写成 current）

- **Unified Customer Operations MCP**（多工具企业级 MCP 服务器）——当前只有本地只读 stdio MCP server
- **Skill Registry / Skill 系统**
- **三通道（ticket/email/lead）统一 runtime**（当前仅 ticket）
- **真实发送 / 真实 CRM / 在线反馈闭环**
- **Multi-Agent A/B/C 对照实验**

---

## 13. Deprecated claims

| 旧说法 | 出现位置 | 为什么废弃 | 替代口径 |
|---|---|---|---|
| 「Support 98% 准确率 / L2 召回 100% / 99/100」 | README / CLAUDE.md / 历史 Portfolio | 数字互斥，来自需真实 provider 的历史 run，HEAD 无单一权威快照 | 引用 §6 的两个 CURRENT VERIFIED；正式路由历史数字标 HISTORICAL |
| 「30/30」单独使用 | 旧表述 | 不说明数据集/mode/provider/证据文件 | 完整引用：customer-context-beta-v2，deterministic_no_service，provider=none，commit efea70b |
| 「120-case Multi-Agent Eval」 | 可能的错误合并 | 100 例正式 + 20 例 shadow 是不同数据集/评测 | 分开表述 |
| 「Multi-Agent 改进正式路由」 | 过度宣称 | Shadow 是只读，不改正式 action | 「Multi-Agent 是只读 Shadow（EXPERIMENTAL），未进入正式授权源」 |
| 「grounding 靠 cosine 阈值」 | CLAUDE.md / adr/001 | 已过时：已知 intent 走 INTENT_FAQ_MAP score=1.0，cosine 仅 unknown hybrid | 「已知 intent 确定性映射；unknown 走 dense+BM25 hybrid」 |
| 「tool_loop / MCP 未实现 / DESIGN ONLY」 | 旧 canonical | **已过时**：c9e1ade 已提交 bounded tooling + 本地 MCP server | 见 §7 |
| 「pytest 全量超时 / 非全离线」 | 旧 canonical §6 | **已证伪**：c9e1ade clean-room 70 passed ~30–50s 全离线 | 见 §2 |
| 「无 DB / HTTP / action 层」 | 旧 canonical | **已过时**：90c16ef 已加 ticket workflow slice | 见 §8 |

---

## 14. Allowed interview claims

1. 「确定性路由工作流：模型负责理解与起草，代码持有授权——意图用确定性表、风险用正则信号、证据用 grounding 门，3 条规则纯函数路由，没有一步是模型自批。」（`agent_loop.py` / `reasoner.py`）
2. 「授权门在固定数据集上的确定性：customer-context 30 例、provider none、复现 2 次一致、30/30、错误自动回复 0。」（commit-pinned JSON）
3. 「Multi-Agent 我做过，但只让它当只读 Shadow：Manager 调度 Billing/Technical，20 例离线 20/20、Manager 选择 0.90、断言不改正式 action。」（`multi_agent_eval.py`）
4. 「Specialist 只拿领域切片不拿完整工单，代码校验切片必须是原文子串——最小权限设计。」（`multi_agent/context.py`）
5. 「LLM-as-judge 有宽松偏差，所以 grounding 修复放在生成期——6 条 KB closure 约束进 draft prompt，claim-graph 只是事后兜底。」（`tools.py` 6 规则）
6. 「v21 根因是 KB snippet 截断 300 字符把关键事实藏起来——改 600 才解决。检索层截断，不是模型能力问题。」
7. 「bounded tooling 是 committed baseline：只读工具 + 代码层权限门 + 有界循环，clean-room 70 passed。」（c9e1ade）
8. 「当前是本地验证原型：无真实工单系统、无发送，AUTO_REPLY 只是决策输出，ticket 副作用走 Mock adapter。」
9. 「我修过一个授权链的 fail-open：grounding 未运行、空 claims 或 compiler 异常原本可能被默认解释成 safe。我把 unknown/error 统一改成 fail-closed，并用 positive control 确认强证据路径仍然可以 AUTO。」（Commit 1 `2c13496`，11 个 fail-closed 测试）

### Forbidden claims

- ❌ 任何「98% / L2 100% / 99/100 / stable」作为当前结果。
- ❌ 把 95/100 说成 `c9e1ade` / `2c13496` 的评测结果（未重跑）。
- ❌ 「grounding 现在绝对不会出错」/「生产安全问题已解决」/「81 tests 证明线上安全」。
- ❌ 「已接真实工单系统 / 已在生产 / 线上准确率」。
- ❌ 「已自动发送客服回复」。
- ❌ 「Multi-Agent 改进正式路由」或「Multi-Agent 是正式链路」。
- ❌ 「120-case Multi-Agent Eval」。
- ❌ 把 customer-context 30/30 说成「业务正确性」或「客服专家验证」。
- ❌ 「Unified Customer Operations MCP / Skill / 三通道 runtime」作为当前能力（FUTURE）。
- ❌ 「grounding 靠 cosine 阈值」（已过时）。
