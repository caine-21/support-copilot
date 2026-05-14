# Support Copilot — 面试讲稿（10–15 min structured talk）

---

## 开场（1 min）— 定性，不是描述功能

> "我做的这个系统，表面上是一个客服工单分诊 agent，但我真正想解决的问题是：
> 如何用 evaluation 驱动一个 AI 决策系统收敛到安全行为，
> 而不是靠调 prompt 靠直觉。"

停顿。如果对方没有打断，继续：

> "我们可以从系统设计讲起，但如果你更感兴趣，
> 我也可以直接从 evaluation 的部分讲，那是这个项目最核心的东西。"

→ 根据对方反应选择入口。

---

## Part 1 — System Design（3 min）

**一句话：**
> "5 个工具顺序执行，信息逐层传递，最终 reasoner 做一个不可逆决策。"

```
classify_intent → kb_search → history_lookup → draft_reply → tone_check
                                                                    ↓
                                              reasoner: 3-rule policy → action
```

**3 条路由规则（画出来或口述）：**

| 条件 | Action |
|---|---|
| churn_risk ≥ 0.6 或 SLA 关键词 | ESCALATE_L2 |
| confidence ≥ 0.75 AND grounding == "strong" | AUTO_REPLY（需过 context_guard） |
| 其他 | ESCALATE_L1 |

**一个关键设计决策（引出 grounding）：**
> "grounding 是确定性的，不是 LLM 自评的。
> 早期版本让 LLM 说 grounded: true/false，
> 结果它在部分匹配上说 true，在强匹配上说 false。
> 我换成了 cosine score ≥ 0.60 作为强匹配门槛，
> 这是一个不能被模型推翻的工程约束。"

---

## Part 2 — Evaluation Design（4 min）

**从数字入题：**
> "我做了 35 个 case，20 个 baseline，15 个 adversarial。
> Baseline 准确率 45%，adversarial 准确率 73%。
> 这个结果一开始看起来很奇怪——为什么对抗集反而更高？"

**解释这个反常：**
> "因为系统的失败是集中的，不是随机的。
> Baseline 里有 6 个 case 是'表达了不满但没有流失风险'，
> 系统都错误路由到了 L2。这是 tone classifier 的系统性偏差，不是边缘案例。
> Adversarial 集专门设计来攻击我已知的 decision boundary，
> 所以它的通过率反映的是'系统是否可以被设计攻击'，不是难度。"

**Adversarial 框架（3 类攻击）：**

| 类型 | 目标 | 结果 |
|---|---|---|
| A — KB misleading | KB 强匹配但答案 plan-specific | 3/5 |
| B — Emotional noise | 情绪 ≠ 流失风险 | 3/5 |
| C — Multi-intent | 混合意图路由稳定性 | 5/5 |

> "设计 adversarial set 的原则是：
> 不是更难的题，而是能破坏你当前 decision boundary 的题。
> A 类攻击的是'grounding 够强就能 auto-reply'这个假设，
> B 类攻击的是'churn signal = frustrated tone'这个假设。"

**安全指标（一定要说）：**
> "有两个指标我从不妥协：
> L2 recall = 100%（真正高风险的工单一个都不能漏）
> unsafe auto-reply rate = 0%（没有强 KB 支撑绝不自动回复）
> 这两个在 35 个 case 里全部成立。
> 这是不对称风险设计：auto-reply 发出去不能撤，escalate 可以撤。"

---

## Part 3 — Failure Taxonomy（3 min）

**直接上图（画或口述）：**

```
              HIGH IMPACT
                   ↑
     F2            │   ← 最危险：eval 看不见
 (silent           │
  false-safe)      │
                   │
     F3            │   ← 可见，影响 accuracy
 (tone             │
  miscalibration)  │
                   │
     F1            │   ← 可见，安全路由到 L1
 (retrieval        │
  noise)           │
                   └──────────────────────→ DETECTABILITY
                       low            high
```

> "我把失败分成三个流形，不是三种 case。
> F1 是检索问题，看得见，路由到 L1 安全。
> F3 是情绪误判，看得见，accuracy 下降但可以量化。
> F2 是最危险的：系统以高置信度 auto-reply，但答案对这个用户是错的。
> 而且当前的 eval 看不见它。"

---

## Part 4 — Oracle Mismatch（2–3 min）— 面试天花板

> "这是整个项目里我觉得最有价值的发现。"

**定义 oracle mismatch：**
> "我的 eval 问的是：'系统有没有路由对？'
> 但真正应该问的是：'如果系统 auto-reply 了，答案对这个用户是正确的吗？'
> 这两个问题不一样。第一个只需要 ticket text，
> 第二个需要这个用户的 plan、region、role——而 ticket 里没有。"

**F2 benchmark：**
> "所以我设计了一个专门的 benchmark。
> 每个 case 有一个 ground-truth user context，
> 但 ticket 里故意不写。
> Metric 叫 safe_wrong_answer_rate：
> 系统 auto-reply 的时候，答案有多少比例对这个用户来说是错的。
> 预测当前系统在这个 benchmark 上大约 60–80% false-safe rate。"

**一句话收束：**
> "这说明 grounding = strong 不等于 answer = correct for this user。
> 这不是模型的问题，是 evaluation 设计的边界问题。
> 我没有 fix 它，因为 fix 需要 user context 作为系统输入，
> 但我把它 document 下来，设计了能测量它的 benchmark。"

---

## 可能的追问 & 回答

**"为什么不直接问用户的 plan？"**
> "可以，这是 v2 的正确方向。
> 需要 user context 作为系统输入，而不是从 ticket 里推断。
> 当前系统是 context-unaware 的，我把这个 gap 文档化了而不是绕过它。"

**"45% baseline 准确率不是很低吗？"**
> "如果唯一指标是 action accuracy，是的。
> 但安全指标从未失效：L2 recall 100%，unsafe auto-reply 0%。
> 这是不对称设计——错误路由到 L1/L2 是保守失败，代价是 agent 时间；
> 错误 auto-reply 是不可撤销的失败，代价是客户信任。
> 系统故意偏向保守。"

**"adversarial 73% 比 baseline 45% 高，这说明什么？"**
> "说明系统的失败是结构性的，不是随机的。
> Baseline 里的失败集中在 L2 over-trigger 上，是单一 root cause。
> Adversarial 集是我已知的攻击点，所以它告诉我的是设计边界，不是能力上限。"

**"context_guard 是怎么工作的？"**
> "两步：先用 LLM 从 ticket 里提取结构化字段 {plan, region}，
> 然后用确定性规则判断这个 plan 能不能访问 KB 里的功能。
> 这是把'语义理解'和'policy 执行'分开。
> LLM 负责理解 paraphrase，规则负责执行策略。
> v1 用关键词匹配，会漏掉'large org'/'corporate tier'这类 paraphrase。
> v2 把理解交给 LLM，把决策留给规则。"

---

## 结尾（30 sec）

> "总结一下：
> 这不只是一个 agent 项目。
> 我用 evaluation 驱动了 policy 收敛，
> 用 adversarial design 暴露了 decision boundary，
> 用 failure taxonomy 把 accuracy 分解成有 root cause 的结构，
> 最后发现 eval oracle 本身有盲区，设计了 benchmark 来量化它。
> 这是我对'怎么做 AI 系统评估'的完整理解。"
