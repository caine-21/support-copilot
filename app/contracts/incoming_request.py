"""Unified IncomingRequest contract.

One DTO for ticket / email / lead entries. metadata is data only — it must
never influence routing or authorization. channel capability is the honest
three-channel boundary: only ticket runs a full vertical slice in A1.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Channel(str, Enum):
    TICKET = "ticket"
    EMAIL = "email"
    LEAD = "lead"


class ChannelCapability(str, Enum):
    SUPPORTED = "supported"
    ROUTING_ONLY = "routing_only"


CHANNEL_CAPABILITY: dict[Channel, ChannelCapability] = {
    Channel.TICKET: ChannelCapability.SUPPORTED,
    Channel.EMAIL: ChannelCapability.ROUTING_ONLY,
    Channel.LEAD: ChannelCapability.ROUTING_ONLY,
}

MAX_RAW_TEXT = 4000
MAX_HISTORY_MESSAGES = 20
MAX_MESSAGE_CHARS = 2000


class IncomingRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    channel: Channel
    raw_text: str = Field(min_length=1, max_length=MAX_RAW_TEXT)
    sender_context: dict | None = None
    message_history: list[dict] | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("raw_text")
    @classmethod
    def _reject_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("raw_text must not be whitespace-only")
        return v

    @field_validator("message_history")
    @classmethod
    def _bound_history(cls, v: list[dict] | None) -> list[dict] | None:
        if v is None:
            return v
        if len(v) > MAX_HISTORY_MESSAGES:
            raise ValueError(f"message_history exceeds {MAX_HISTORY_MESSAGES} messages")
        for msg in v:
            body = msg.get("body", "") if isinstance(msg, dict) else ""
            if isinstance(body, str) and len(body) > MAX_MESSAGE_CHARS:
                raise ValueError(f"message body exceeds {MAX_MESSAGE_CHARS} chars")
        return v
