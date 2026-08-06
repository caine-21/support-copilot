# ADR — support-copilot ticket workflow slice（2026-08-07）

### ADR-001：为什么主链路由确定性 Workflow 控制
- 背景：分诊路径可以提前画成状态图；「下一步」由证据等级+风险信号决定，不需要模型规划。
- 最终选择：`run_agent` 的固定流水线（INL→KB→draft→grounding→synthesize）原样复用，`default_decision_fn` 懒加载。
- 为什么不是更复杂的 Agent：授权类决策（AUTO/L1/L2）必须可审计、可复现；模型自由在这里是风险不是能力。
- 代价：人工量可能偏保守（L1 兜底多）。
- 什么条件下需要重审：真实流量出现「固定流水线选错工具/需要回退」且评测集能捕捉时。

### ADR-002：为什么动作执行走 adapter + 幂等，而不是直接调外部系统
- 背景：真实客服系统不可逆、有副作用；本轮不接真实系统。
- 最终选择：`TicketActionAdapter`(protocol) + `MockTicketActionAdapter` 默认；幂等键 `ticket_id:workflow_version:action_type`（UNIQUE + executed 检查）。
- 为什么：外部副作用统一经过决策门 + 人工审核 + 幂等；失败不把工作流标成成功。
- 为什么不是更复杂的 Multi-Agent：单链路可审计是唯一目标，不需要多角色。
- 代价：自动化率被锁住（等真实 adapter + 合规试点）。
- 重审：合规脱敏数据 + 白名单试点通过后，换真实 adapter 同协议。

### ADR-003：为什么用 SQLite（stdlib）+ 轻量 Repository，不用 ORM/Postgres/Redis
- 背景：本地必须零外部服务可跑；slice 是单机审计链路。
- 最终选择：`sqlite3` + `TicketRepository`（显式 SQL，无 ORM）。
- 为什么：零依赖、可重启查询、符合「小团队能接手一条业务链路」。
- 代价：不适合高并发；无连接池。
- 重审：流量上来后（真实 adapter 落地）再评估 Postgres；schema 是显式 DDL，迁移有记录。

### ADR-004：为什么验证方式 = 离线测试 + 真实路径单次 + HTTP smoke
- 背景：离线 fake 证明逻辑，但「是否真接线」必须用真实决策路径证明。
- 最终选择：21 个离线测试（fake decision port）+ REAL-1 真实 run_agent 单次 + uvicorn HTTP smoke。
- 为什么：不把 mock 测试当生产验证，也不把真实调用当常态（成本可控）。
- 代价：真实路径只跑了一次，非回归矩阵。
- 重审：每次换 prompt/模型先跑冻结数据集（现有 eval 变门禁）。
