# Skill: knowledge_lookup

> Human-readable evidence. The runtime source of truth is the `SkillSpec`
> registered in `app/skills/registry.py` — this file is never parsed for
> permissions.

- **name**: knowledge_lookup
- **version**: 1.0.0
- **purpose**: Retrieve KB evidence for a ticket intent through the scoped read gateway.
- **specialist**: knowledge
- **when_to_use**: any ticket intent that needs KB grounding evidence before authorization.
- **when_not_to_use**: not a substitute for retrieval policy or grounding; never selects or authorizes an action.
- **required_context**: `request_id`, `query`, `intent`, `top_k` (a subset of the Knowledge Specialist projection).
- **allowed_tools**: `search_knowledge_base` (READ; via the SAME scoped gateway the Specialist was given).
- **prompt_ref**: none — deterministic tool skill (no LLM prompt).
- **policy_refs**: `intent_faq_mapping`, `fail_closed_grounding`.
- **output_schema**: `SkillResult{status, data{evidence, coverage}, evidence_refs, reason_codes}`.
- **failure_conditions**:
  - tool/MCP failure → `ERROR` (fail-closed; never an empty success)
  - normal query with no KB result → `NO_EVIDENCE`
  - capability violation → `BLOCKED` (enforced by gateway, never reachable here)
- **completion semantics**: `SUCCESS` = retrieval/evidence valid; `NO_EVIDENCE` = normal query but no result; `BLOCKED` = capability violation; `ERROR` = tool/MCP failure.
