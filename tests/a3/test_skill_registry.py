"""A3: SkillSpec + Registry — static declaration, registration-time capability validation."""
import pytest

from app.skills.contracts import SkillSpec
from app.skills.registry import get, list_skills, register
from app.skills.runtime import knowledge_lookup


def _spec(name, *, specialist="knowledge", tools=("search_knowledge_base",),
          context=("request_id", "query", "intent", "top_k")):
    return SkillSpec(
        name=name, version="1.0.0", description="test", specialist=specialist,
        applicability={"intents": ["*"]}, input_schema=knowledge_lookup.Input,
        output_schema=knowledge_lookup.Output, required_context=context,
        allowed_tools=tools, prompt_ref=None, policy_refs=(),
    )


def test_knowledge_lookup_registered():
    spec = get("knowledge_lookup")
    assert spec is not None
    assert spec.specialist == "knowledge"
    assert spec.allowed_tools == ("search_knowledge_base",)
    assert spec.prompt_ref is None  # deterministic tool skill, no LLM prompt


def test_registry_is_static_and_listable():
    assert "knowledge_lookup" in {s.name for s in list_skills()}


def test_duplicate_registration_rejected():
    with pytest.raises(ValueError):
        register(_spec("knowledge_lookup"))


def test_skill_requesting_get_ticket_rejected():
    with pytest.raises(ValueError):
        register(_spec("evil_read", tools=("get_ticket",)))


def test_skill_requesting_execute_approved_reply_rejected():
    with pytest.raises(ValueError):
        register(_spec("evil_action", tools=("execute_approved_reply",)))


def test_skill_requesting_external_permission_rejected():
    from agent.tooling import ToolPermission

    spec = _spec("evil_external", tools=("execute_approved_reply",))
    # execute_approved_reply is EXTERNAL_OR_IRREVERSIBLE and not in the
    # knowledge capability; registration must reject before it is added.
    with pytest.raises(ValueError):
        register(spec)


def test_skill_requesting_authorization_context_rejected():
    with pytest.raises(ValueError):
        register(_spec("evil_ctx", context=("request_id", "query", "intent", "authorization")))


def test_wrong_specialist_tool_rejected():
    with pytest.raises(ValueError):
        register(_spec("wrong", specialist="support", tools=("get_ticket",)))


def test_empty_name_rejected():
    with pytest.raises(ValueError):
        register(_spec(""))
