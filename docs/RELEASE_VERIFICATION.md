# Release Verification — support-copilot

> Clean-room verification: 提取 `90c16ef` 的 committed 树到临时目录，不用当前工作区未提交文件、不读 `.env`、无真实 API 调用。

- **Verified commit**: `90c16ef feat: add auditable ticket workflow slice`
- **Verified date**: 2026-08-07
- **Environment**: Windows 11 / Python 3.14.4 / pytest 9.0.3 / fastapi 0.136.1 / pydantic 2.10 / sqlite3 (stdlib)。依赖已在本机预装，未做全新 venv。
- **Isolation method**: `git archive 90c16ef | tar -x -C <tmpdir>` — committed 树，不含任何未跟踪文件。

## Install command
```bash
py -m pip install -r requirements.txt
py -m pip install -r service/requirements.txt   # fastapi, uvicorn, httpx
```

## Test command
```bash
py -B -m pytest tests -q
```

## Result
- **60 passed, 0 failed**（39 个 committed multi-agent 测试 + 21 个 ticket-slice 新增）
- ⚠️ 上轮「70 passed」含用户未跟踪的 `tests/test_agent_tooling.py` + `_mcp_stdio_*`（working-tree only）；**clean commit 下为 60**。

## Smoke command
```bash
# clean-room smoke（fake decision port，离线）
# create → completed/AUTO_REPLY → review(executed) → repeat review(idempotent) → 1 action row
```
输出：
```
APP_BOOT: OK
AGENT_LOOP_IMPORT: OK (committed run_agent callable)
CREATE: completed AUTO_REPLY | review: pending_review
REVIEW1: executed create_reply
REVIEW2 idempotent: True | msg: already reviewed — no re-execution
ACTIONS_ROWS: 1
```

## Result

| 项目 | 状态 |
|---|---|
| `90c16ef` 独立可运行 | ✅ **Clean-room verified** |
| API 启动 | ✅ Clean-room verified（无 agent 依赖，顶层仅 stdlib+fastapi+pydantic） |
| 服务切片测试 | ✅ Clean-room verified（60 passed） |
| 真实决策路径接线 | ✅ Import 级 verified（committed `run_agent` callable）；**完整决策需 `DEEPSEEK_API_KEY` → 非 clean-room 可测**（`working-tree verified / requires real API key`） |
| canonical eval 100 例 | ⚠️ 需真实 API key → **not reproduced in clean-room**（引用 committed report_epistemic-r3 数字） |

## Known warnings
- `service/engine.py` 懒加载 `agent.agent_loop` / `agent.run_ledger`（committed 版本，已验证 import 正常）；不依赖用户未提交的 tool_loop 工作。
- 用户工作区 6 个已改文件 + 10 个未跟踪文件**不在本验证范围内**，也未被 clean-room 使用。

## Mocked components
- `MockTicketActionAdapter`（记录动作，不真发）
- 测试用 `make_fake_decision_fn`（fake decision port）

## Not verified
- 真实 LLM 决策路径的**业务正确性**（需 API key + 真实数据）
- canonical 100 例 eval 在 clean 环境的重新运行
- 真实客服系统接入 / 真实发送
