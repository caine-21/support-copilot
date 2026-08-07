"""Native OpenAI-compatible function-calling adapters.

The production adapter forwards provider `tool_calls` directly. ScriptedAdapter
exists only for deterministic no-service tests and accepts an explicit sequence.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class ToolCallingModel(Protocol):
    def next_turn(self, messages: list[dict], tools: list[dict]) -> ModelTurn: ...


class NativeFunctionCallingAdapter:
    """Uses the current OpenAI-compatible provider's native `tools` API."""
    def __init__(self, router=None, model: str = "deepseek-chat"):
        from .llm import router as default_router
        self.router, self.model = router or default_router, model

    def next_turn(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        response = self.router.call_with_tools(messages=messages, tools=tools, model=self.model)
        message = response.choices[0].message
        calls = []
        for call in message.tool_calls or []:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"__invalid_json__": True}
            calls.append(ToolCall(call_id=call.id, name=call.function.name, arguments=args))
        return ModelTurn(content=message.content, tool_calls=calls)


class ScriptedModelAdapter:
    """Test-only adapter: each item is a ModelTurn or a dict representation."""
    def __init__(self, turns: list[ModelTurn | dict]):
        self.turns = list(turns)
        self.seen_messages: list[list[dict]] = []

    def next_turn(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        self.seen_messages.append(messages)
        if not self.turns:
            return ModelTurn(content="I need human review because evidence is unavailable.")
        item = self.turns.pop(0)
        if isinstance(item, ModelTurn):
            return item
        calls = [ToolCall(call_id=call["call_id"], name=call["name"], arguments=call.get("arguments", {})) for call in item.get("tool_calls", [])]
        return ModelTurn(content=item.get("content"), tool_calls=calls)
