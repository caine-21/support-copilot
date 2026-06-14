# 用 KB grounding score 做路由，而不是 LLM 自报置信度

路由决策（AUTO_REPLY / ESCALATE_L1 / ESCALATE_L2）基于 KB 余弦相似度得分（`_GROUNDING_STRONG = 0.60`），而非 LLM 输出的 `confidence` 字段。

## 决策

`reasoner.py` 的 `grounding_level()` 函数是一个纯确定性函数：拿 KB top 命中的 cosine score 与阈值比较，输出 `strong / weak / none`。只有 `strong` 状态下才允许 AUTO_REPLY（`eval.py:73-78` 用这条规则做安全检查）。

LLM 的 `confidence` 字段存在但只是辅助展示——它是一个后验复合扣分（`base=0.85 - intent不确定 - KB弱匹配 - 多意图 - ...`），本身也包含 KB grounding 信号，不是独立来源。

## 为什么不直接用 LLM 置信度

**被否决方案**：让 LLM 判断"我的回答有多大把握"，按置信度高低决定是否自动回复。

**否决原因**：
1. LLM 自报置信度不可审计——同一张 ticket 换个措辞可能给出 0.9 → 0.6 的漂移，没有外部锚点。
2. 客服场景的 false negative 代价不对称：如果"退款承诺"被误判为高置信度 AUTO_REPLY，造成的公司风险远大于多了一次 ESCALATE。
3. KB grounding 是可测量的：sentence-transformers 的 cosine score 是可复现的，阈值是可以基于历史数据校准的。

**结果**：35 case 评测中 unsafe AUTO_REPLY rate = 0%，L2 recall = 100%（`eval.py` 指标）。

## Considered Options

| 方案 | 原因被否决 |
|---|---|
| LLM 置信度路由 | 不可审计，无锚点，压力下可能给高分 |
| 人工规则（关键词黑名单）| 覆盖有限，维护成本高，无语义理解 |
| LLM + KB 联合投票 | 复杂性不值当；KB grounding 单独已足够 |
| **KB grounding score（选用）** | 可测量，可复现，阈值可校准 |

## 面试追问备答

**Q：KB grounding 的 0.60 阈值怎么来的？**
A：是从历史 ticket 数据归纳的经验值，不是凭感觉。sentence-transformers 在这个语料上 ≥ 0.60 对应"语义完全命中 FAQ"，0.40-0.60 对应"相关但不完整"。如果换语料库，这个阈值需要重新标注。

**Q：LLM 置信度完全没用吗？**
A：它用在 reflection loop 里——`agent_loop.py:134` 中 `confidence < 0.65` 会触发 KB 重查（用更宽泛的 query 重试）。但它不影响最终路由决策，只影响"要不要多查一次"。
