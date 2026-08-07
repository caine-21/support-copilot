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
| Current architecture label | **Deterministic routing workflow**（LLM 作子过程）+ **bounded read-only tool loop**（opt-in）+ **A1 unified request runtime**（ticket vertical slice）+ deterministic authorization gates + **read-only Multi-Agent Shadow**（EXPERIMENTAL，非正式业务车道） |
| Current maturity label | **Local Verified Prototype**（离线评测 POC；无真实工单系统、无部署、无发送） |

---

## 2. Reproducibility Baselines

> 这是当前唯一可复现的测试基线。`60` 是历史演进证据，`70` 是当前 clean baseline。

| Baseline | Commit | Scope | Result | Meaning |
|---|---|---|---|---|
| Legacy clean | `31e409d` | committed legacy + service 切片 | **60 passed**（21–49s，离线） | pre-tooling 基线 |
| Tooling clean | `c9e1ade` | committed bounded tooling + legacy + service | **70 passed**（29–48s，离线） | bounded tooling 基线 |
| Grounding fail-closed | `2c13496` | + grounding fail-closed（11 safety tests） | **81 passed** | fail-closed 基线 |
| A1 unified runtime | `2429c63` | + app/ + tests/a1（32 tests） | **113 passed** | A1 基线 |
| A2 typed/local tool plane | `6401fb4` | + get_ticket + scoped gateway + tests/a2（18） | **131 passed** | typed read plane |
| A2 MCP parity | `1e1f238` | + MCP backend parity + A1-on-MCP | **148 passed** | MCP read plane |
| A2 action gate | `ffc5eb8` | + execute_approved_reply（11 A2B tests） | **159 passed** | approval-gated action |
| **A2 final** | `23b1415` | + FAILED-retry fix（2 tests） | **161 passed** | A2 基线 |
| **A3 skill registry** | `45adff8` | + app/skills + knowledge_lookup skill + tests/a3（20） | **181 passed** | A3 基线 |
| **A4 hitl checkpoint** | `437b805` | + review checkpoint + approval/execution separation + tests/a4（10） | **191 passed** | **current clean test baseline** |

- 演进链是**架构里程碑**，不是单纯测试数量增长：60（确定性工作流）→ 70（bounded tooling）→ 81（fail-closed grounding）→ 113（A1 unified runtime）→ 131（typed read plane）→ 148（MCP parity）→ 161（approval-gated action + FAILED semantics）→ 181（typed skill registry）→ 191（HITL checkpoint + approval/execution separation）。
- 验证方法：`git archive <commit>` → 全新临时目录 → `py -B -m pytest tests -q`（**离线，无 API key，无 .env，无工作树未提交文件**）。
- docs commit（`a11ad85` / `c84c37b` / `194d73f` 的 docs-only 与 test-harness 部分）不改变业务 test surface 的工程里程碑口径（194d73f 是 12s→30s 的 harness deadline 调整，不改变业务语义）。

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

### ④ A1 Unified Request Runtime（Commit 2，CURRENT VERIFIED）

| 字段 | 值 |
|---|---|
| Commit | `2429c63 feat: add unified request routing and specialist runtime`（21 new files；legacy runtime 0 修改） |
| Clean-room | **113/113 × 2**（连续两次） |
| Architecture | **Additive Domain Facade**（非 Multi-Agent）：Unified IncomingRequest → deterministic Request Router → Context Projection → Support/Knowledge Specialist lanes → existing grounding/risk/authorization → structured trace |
| 入口 | `app/runtime/run_a1.run_a1(request)`；`app/` 只做 contract / coordination / projection / routing / trace |

**Channel capability（诚实三通道）**：

| Channel | Capability | A1 证据 |
|---|---|---|
| ticket | **SUPPORTED** | 完整 vertical slice（3 demo 真实执行） |
| email | **ROUTING_ONLY** | contract + route；无 specialist、无副作用、无业务结果 |
| lead | **ROUTING_ONLY** | 同上 |

**Router 真实动态性（三种可验证行为，execution graph 真变化非 metadata）**：

| Case | intents | 行为 | 证据 |
|---|---|---|---|
| CLEAN | invoice_download | Support+Knowledge，normal route | trace 单 slice / 1× tool / 1× lane |
| MULTI | password_reset + invoice_download | multi_intent → 2 intent slices 独立处理 → 2× knowledge/tool path | trace 4× lane / 2× tool；evidence 分离 FAQ-account-01 ∥ FAQ-billing-01（测试断言 disjoint） |
| HIGH-RISK | sla_uptime + sla signal | early_risk_pre_guard → ESCALATE_L2 → 0 lane / 0 tool / 0 draft | trace route_early_stop；generation 前截停 |

**Context isolation（CURRENT VERIFIED）**：Support/Knowledge 经 `ContextProjection` 获取最小视图。测试证明 `authorization / lane_results / route_decision / grounding_status / executor / idempotency / MockTicketActionAdapter / side-effect capability` 不被投影给 Specialist；Support `sender_context` 仅暴露 allowlist `{plan, region, role}`（不含 email/phone/account_status）。**表述限于"针对当前 projection contract 的测试证明"，不称"完全防止泄漏"。**

**Proposal / Authorization 分离**：Specialist 只产出 `proposal`；`AUTO_REPLY / ESCALATE_L1 / ESCALATE_L2` 由既有 deterministic evidence/risk gate（`agent.reasoner.synthesize`）决定。Specialist 无权产生业务授权。

**Known flake（不归因 A1）**：`test_mcp_backend_matches_local_contract` / `test_mcp_v2_stdio_three_read_tools_and_clean_exit` 在 Windows 负载下偶发 stdio 子进程 12s 启动超时。证据：Commit 1 已观察；Commit 2 未改 MCP path；`2429c63` clean-room 连续 113/113。**pre-existing infrastructure flake，A2 已用 3C 调整 harness deadline（非业务语义）处理。**

### ⑤ A2 MCP Tool Plane（Commit A2，CURRENT VERIFIED）

**架构**：A1 Runtime → injected `ScopedToolGateway` → canonical typed tool registry → Local / MCP stdio backend → same domain handlers。backend selection 在 composition root（`run_a1`），Specialist 无感。

**Server capability set（`agent/support_mcp_server.py`）**：
- READ：`search_knowledge_base` / `get_customer_context` / `get_ticket` / `get_ticket_history`
- EXTERNAL_OR_IRREVERSIBLE：`execute_approved_reply`

⚠️ **Server Capability Set ≠ Specialist Capability Set**（capability withholding：server 是 capability provider，不是把 tools/list 直接喂给模型）。

**Knowledge Specialist capability（CURRENT VERIFIED）**：
- 仅可见 `search_knowledge_base`；backend-agnostic（只依赖注入的 scoped tool interface，不感知 Local/MCP transport）
- 不可发现 `get_ticket` / `execute_approved_reply`；forced 调用 → `FORBIDDEN specialist_tool_not_allowed`（backend 执行前）
- MCP transport failure → Knowledge ERROR/no evidence → grounding fail-closed → AUTO_REPLY forbidden

**Support Specialist scope**：read policy exists（`search_knowledge_base` / `get_customer_context` / `get_ticket_history`），**但当前 A1 Support path 不实际调用工具**（not exercised）。

**Local/MCP parity（CURRENT VERIFIED）**：同一 fixture state（temp SQLite + SUPPORT_DB_PATH）下，4 个 read tools 的 status / business data / error_code / evidence semantics 一致；允许差异仅 transport metadata / latency / trace id。A1 CLEAN：Local final state = MCP final state（trace 仅 backend 不同）。A1 MULTI：2 intent slices → 2 次 MCP call → evidence 分离（FAQ-account-01 ∥ FAQ-billing-01）→ final state 不变。A1 HIGH-RISK：backend=mcp 配置 → early stop → **0 MCP tool contact** → ESCALATE_L2（lazy-connect）。

**MCP failure semantics（CURRENT VERIFIED）**：MCP unavailable / timeout / malformed → `ToolResult ERROR/TIMEOUT` → Knowledge ERROR / no evidence → grounding fail-closed → AUTO_REPLY forbidden。

**stdio diagnostics（ENVIRONMENT OBSERVATION，非 benchmark）**：before（`data/a2/mcp_stdio_diagnostic_before.json`，commit 796d28d）20/20 success，initialize 主导（p50≈4.6s / p95≈7.98s / max≈7.98s），total max≈8.61s；after（`..._after.json`，commit 1e1f238）20/20 success，initialize p95≈10.57s / total max≈11.67s。结论 `initialization_phase_dominates`；dependency import vs server init **not separately resolved**。3C 把 test harness 的 12s startup deadline 调到 30s（12s 落在正常观察尾部）——是 **test-harness robustness adjustment，不是证明 MCP cold-start root cause 已解决**。Connection lifecycle = **per tool call（每次 execute 一个新 stdio 子进程；MULTI 2 slices = 2 cold starts）**——已知限制，未引入 session pooling（prototype 优先验证 transport/permission/failure semantics）。

**A2 action gate（CURRENT VERIFIED）**：`execute_approved_reply(ticket_id)`——input 仅 ticket_id，禁止 caller 提供 `approved/force/review_status/reply_text`；permission `EXTERNAL_OR_IRREVERSIBLE`；Specialist 不可发现不可执行；Executor 可发现。Server-side approval：直接 MCP 调用无 persisted approval → `approval_required`（adapter 0）；`approved=true` 注入 → `invalid_arguments`。**Agent cannot self-authorize through tool arguments.**

**Approval/Execution coupling（LIMITATION，如实记录）**：当前正常 workflow `review_ticket(approved)` → `_perform_approved_action` → **立即** Mock execute → review_status=approved。`approval_execution_coupling = coupled`。`execute_approved_reply` 是 server-side approval-gated executor capability；**不要写**"正常 product flow 是 approval persisted → later MCP execution"（除非架构改变）。`review_status=approved 但 action 未成功` 的真实场景：adapter failure（FAILED 记录）/ test-constructed state。

**Draft integrity（VERIFIED + LIMITATION）**：tool input 无 `reply_text` → caller 不能替换执行内容（VERIFIED）；当前 workflow 无正常 draft_response mutation path（VERIFIED）；executor 读 persisted `ticket.draft_response`。**NOT VERIFIED**：immutable approved-draft hash/version binding——"Execution reads persisted ticket draft rather than caller-supplied content. An immutable approved-draft hash/version binding is not yet implemented."（FUTURE）

**Evidence gate（CURRENT VERIFIED）**：human approval alone ≠ execution authorization——approved + grounding unsafe → `grounding_not_authorized`（adapter 0）。

**Idempotency / FAILED semantics（CURRENT VERIFIED）**：success duplicate → `already_executed`（adapter total=1）；adapter failure → `FAILED` recorded；后续调用 → `previous_execution_failed`（**manual retry required，adapter 不再调**）。**没有自动 retry 已实现。**（本次修复的真实 bug：FAILED + UNIQUE idempotency key → 旧代码二次执行 IntegrityError）

**Exactly-once boundary（KNOWN LIMITATION）**：DB check → mock/external-equivalent call → DB record 存在 crash window；local prototype 无 distributed exactly-once guarantee；未实现 outbox / distributed transaction / external idempotency reconciliation。

### ⑥ A3 Skill Registry（Commit A3，CURRENT VERIFIED）

| 字段 | 值 |
|---|---|
| Commit | `45adff8 feat: add typed skill registry and minimal skill selection` |
| Clean-room | **181 passed** |
| Implemented skills | **1**：`knowledge_lookup`（deterministic tool skill，无 LLM prompt） |
| 未 Skill 化 | `support_proposal` —— 评估为 deterministic function（无独立 context/tool/prompt boundary），强行包装只增加 indirection |

**架构**：IncomingRequest → Deterministic Router → Specialist → **Deterministic Skill Selector** → Skill Registry → Skill Context Projection → Scoped Tool Capability → Skill Result → existing grounding → existing authorization。

**SkillSpec（静态 Python declaration = runtime source of truth）**：name / version / description / specialist / applicability / input_schema / output_schema / required_context / allowed_tools / prompt_ref / policy_refs / completion_contract。SKILL.md 是 human-readable evidence，**runtime 不解析 Markdown 执行权限**。

**Skill 边界（五者区别）**：Specialist = 领域角色/orchestration；Skill = 具体任务能力包；Tool = 原子执行能力；Policy = 不可被 Skill 覆盖的规则；Executor = 授权后的副作用能力。

**确定性选择**：`select_skills(specialist, intent_set)` 无 LLM；无 applicable → 显式 `NO_SKILL`（非随机 default）。

**Context minimization**：Skill context ⊆ Specialist projection（registration 校验 required_context ⊆ `SPECIALIST_CONTEXT_FIELDS`）；knowledge_lookup 仅得 `{request_id, query, intent, top_k}`，无 authorization/executor/idempotency/review。

**Permission intersection（CURRENT VERIFIED，核心安全规则）**：`effective_tools = Specialist scope ∩ Skill allowed_tools`。两层保护：registration-time（Skill 请求超能力工具/context → 拒绝） + runtime（即使绕过 registration，scoped gateway 仍 FORBIDDEN）。恶意 Skill 请求 `get_ticket` / `execute_approved_reply` / EXTERNAL permission → 全拒绝。

**Skill 不能提权**：Skill → AUTO_REPLY authority / execute_approved_reply / override Router / override Specialist capability 全部禁止。

**Completion semantics**：SUCCESS / NO_EVIDENCE / BLOCKED / ERROR（非 LLM free text）。MCP failure → Skill ERROR → no evidence → grounding fail-closed → non-AUTO（与 A1/A2 invariant 串联）。

**Trace**：新增 `skill_selected` / `skill_started` / `skill_completed`（复用 A1 trace，非第二套）；字段 skill_name / skill_version / reason_codes / context_refs / tool_names / status；不记录完整 prompt/customer context。HIGH-RISK：0 skill_selected / 0 tool / 0 MCP / ESCALATE_L2（Registry 不在 risk gate 前 eager load）。

**A1/A2 invariants 保持**：CLEAN final state 不变（新增仅 skill trace 事件）；MULTI 2 slices → 2 次 skill execution（各自 intent/context）；A2 capability（Knowledge 仅 search / get_ticket & execute_approved_reply forbidden / MCP failure fail-closed / FAILED≠EXECUTED）全部保持。

### ⑦ A4 HITL Checkpoint（Commit A4，CURRENT VERIFIED）

| 字段 | 值 |
|---|---|
| Commit | `437b805 feat: persist review checkpoints and separate approval from execution` |
| Clean-room | **191 passed** |
| **approval_execution_coupling** | **separated**（A2 的 coupled → A4 的 separated） |

**状态机**：`PENDING(WAITING_FOR_REVIEW)` → human approve/edit/reject → `APPROVED/EDITED + READY_FOR_EXECUTION`（或 `REJECTED`）→ 显式 resume/executor → `EXECUTED / FAILED`。**approval 与 execution 是不同状态转换**——`review_ticket(approved)` 不再立即执行 mock action（adapter 0）。

**Review checkpoint（SQLite 持久化，非内存）**：ticket 上新增 `approved_payload`（reviewed 内容，source of truth）/ `approved_payload_hash`（SHA-256）/ `reviewed_at` / `review_version`。迁移为 additive idempotent ALTER（旧 DB 自动升级，无 Alembic，不手动删库）。

**Approved content binding（CURRENT VERIFIED，从 FUTURE 升级）**：`what was approved == what may be executed`。canonicalize（trimmed UTF-8）→ SHA-256 → persist；execution 时 re-hash persisted approved_payload 与存储 hash 比对，不一致 → `stale_approved_draft`（execute forbidden）。caller 不能传 reply_text/hash/approved（ticket_id only）。

**Resume / restart proof**：跨 service/repository 新实例（同一 SQLite）读取 checkpoint → 校验 → 执行 approved content 恰一次（测试证明）。进程重启语义明确（checkpoint 不是内存 HITL）。

**Human edit**：Agent draft A → Human edit B → approved payload=B、hash=hash(B) → executor 执行 B（绝不 hash A execute B）。

**Evidence revalidation**：approval 不覆盖 evidence gate——`approved + grounding unsafe → execute 时 NoEvidenceGate → grounding_not_authorized`（adapter 0）。

**Idempotency / FAILED**：保持 A2——EXECUTED → already_executed（adapter total 1）；FAILED → previous_execution_failed（manual retry，adapter 不再调）；WAITING/REJECTED → 不可执行。

**能力边界保持**：Knowledge/Support/Skill 均不可见 executor（execute_approved_reply 仍 Executor only）；HIGH-RISK 仍 0 checkpoint / 0 review state / 0 action / L2；email/lead 仍 ROUTING_ONLY（不建 checkpoint）。

**预期行为变更（EXPECTED）**：`review_ticket(approved)` 从"立即执行"改为"创建 checkpoint，READY_FOR_EXECUTION，adapter 0"——这是 A4 的真实 architecture evolution，已同步更新 service/API 测试。A1 routing/authorization result 与 A2 permission semantics 未变。

**AUTO_REPLY 语义澄清**：在 demo/service slice 中，external-equivalent action 仍经过 review gate——`AUTO_REPLY` 是**授权结果（decision label）**，不是"自动执行"；执行仍需显式 resume/executor。

**Crash window boundary（KNOWN LIMITATION）**：DB check → mock call → DB record 仍存在 crash window；real external exactly-once 不保证（未引入 outbox/distributed transaction）。

### ⑧ A5 Architecture A/B/C Evaluation（CURRENT VERIFIED — 评估本身）

| 字段 | 值 |
|---|---|
| Commits | `a03d75b`（freeze benchmark/policy）· `14ee54b`（harness）· `a953a23`（results） |
| Provider / model | DeepSeek `deepseek-chat`（A 确定性；B/C 同模型同 config） |
| Benchmark | 30 synthetic/de-identified cases（6 single / 8 multi / 5 high-risk / 4 weak-evidence / 4 ambiguous / 3 unknown）；oracle 与 agent view 分离（no-leak 测试） |
| Decision policy | 结果前冻结（unsafe_auto>0→不推广；success 需≥3 case 且≥10% 领先；multi-intent 需≥15%；cost≥3×→保留 A） |

**Overall task_success**（30 例，synthetic/offline）：
| Lane | success | unsafe_auto | model_calls/case | tool_calls/case | latency p50/p95 |
|---|---|---|---|---|---|
| A（deterministic workflow） | 0.633 | 0 | 0.0 | 0.93 | 656ms / 6.2s |
| B（single agent + tools） | 0.300 | 0 | 1.63 | 1.57 | 5.4s / 10.3s |
| C（manager + specialists） | 0.633 | 0 | 0.73 | 0.50 | 1.3s / 6.9s |

**关键发现**：
- **A 与 C 在全部 30 例上 task_success 与 final_authorization 完全一致**——Manager+Specialists 相比确定性工作流零增益，却多花 0.73 model calls/case + ~2× 延迟。确定性工作流已通过 INTENT_FAQ_MAP 逐 intent 检索，specialist 分层未提供额外价值。
- **B 明显更差**（0.300）：single agent 的 LLM 草稿超出 KB 边界 → fail-closed grounding → L1 降级（10 个分歧 case 全部 A/C=P、B=F）。
- 所有 lane unsafe_auto=0（共享授权 gate 公平约束）。
- Multi-intent subset：A 5/8 = C 5/8，B 0/8（C 未超 A 15%）。

**架构决策：KEEP_WORKFLOW_MAIN。** Multi-Agent 保持 experimental/read-only shadow，不 promotion（数据未支持）。这是成功的 A5——证明的是架构判断，不是 buzzword accumulation。**评估数据是 synthetic/offline，不是线上指标。**

**限制**：4 个 ambiguous case 用 malformed partial customer_context fixture → 三 lane 同等报错（0/4，排除于相对比较）；token usage 未 instrumented（adapter 不暴露），成本以 model_calls + latency 度量。

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

> A1 已完成项见 §6④（IncomingRequest / Router / Specialists / ContextProjection / trace，CURRENT VERIFIED）。
> A2 已完成项见 §6⑤（typed MCP read plane / Local-MCP parity / specialist scoped read capability / approval-gated mock MCP action，CURRENT VERIFIED）。
> A3 已完成项见 §6⑥（typed Skill Registry / deterministic selector / minimal context / permission intersection / 1 implemented skill：knowledge_lookup，CURRENT VERIFIED）。
> A4 已完成项见 §6⑦（ticket HITL checkpoint / approval-execution separation / approved-draft SHA-256 binding / restart resume，CURRENT VERIFIED）。
> 以下仍 FUTURE：

- **更多 Skill**（当前仅 knowledge_lookup；support_proposal 评估为不值得 Skill 化）
- **email / lead 完整 vertical slice**（当前 ticket=SUPPORTED，email/lead=ROUTING_ONLY；3-channel HITL / checkpoint 亦 FUTURE）
- **connection / session pooling**（当前 per-tool-call 子进程；未引入 pooling）
- **真实发送 / 真实 CRM / 真实 side effect**
- **Multi-Agent 正式 promotion**（A5 实验已完成：KEEP_WORKFLOW_MAIN——C 未胜 A 且成本更高；Multi-Agent 仍 experimental/read-only shadow）
- **统一多域企业级 MCP / production deployment / real exactly-once**

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
10. 「我设计统一 IncomingRequest 与确定性 Request Router，根据 channel、intent、risk 和 context 动态选择 Specialist 执行路径；多意图请求按 intent slice 独立检索/处理，高风险请求在生成前 early-stop。」（Commit 2 `2429c63`，§6④）
11. 「统一 contract 已覆盖 ticket/email/lead；当前 ticket 有完整 vertical slice，email/lead 只验证到 routing contract。」（诚实三通道）
12. 「我把生成建议与执行授权拆开：Specialist 可以产出 proposal，但 AUTO/L1/L2 仍由既有 deterministic evidence/risk gate 决定。」（§6④）

### Forbidden claims

- ❌ 任何「98% / L2 100% / 99/100 / stable」作为当前结果。
- ❌ 把 95/100 说成 `c9e1ade` / `2c13496` 的评测结果（未重跑）。
- ❌ 「grounding 现在绝对不会出错」/「生产安全问题已解决」/「81 tests 证明线上安全」。
- ❌ 「已实现完整 ticket/email/lead 三通道 Agent」（当前仅 ticket=SUPPORTED；email/lead=ROUTING_ONLY）。
- ❌ 把 A1 说成 Multi-Agent 生产架构（A1 是确定性 Router + Specialist lanes + 既有 gate；Multi-Agent A/B/C 仍 FUTURE）。
- ❌ 「已接真实工单系统 / 已在生产 / 线上准确率」。
- ❌ 「已自动发送客服回复」。
- ❌ 「Multi-Agent 改进正式路由」或「Multi-Agent 是正式链路」。
- ❌ 「120-case Multi-Agent Eval」。
- ❌ 把 customer-context 30/30 说成「业务正确性」或「客服专家验证」。
- ❌ 「Unified Customer Operations MCP / Skill / 三通道 runtime」作为当前能力（FUTURE）。
- ❌ 「grounding 靠 cosine 阈值」（已过时）。
