"""IncomingRequest contract: strong typing, bounds, metadata-is-data."""
import pytest
from pydantic import ValidationError

from app.contracts.incoming_request import (
    Channel,
    MAX_HISTORY_MESSAGES,
    MAX_MESSAGE_CHARS,
    IncomingRequest,
)


def _req(**kw):
    base = dict(request_id="r1", channel=Channel.TICKET, raw_text="How do I download my invoice?")
    base.update(kw)
    return IncomingRequest(**base)


def test_valid_ticket_request():
    r = _req()
    assert r.request_id == "r1"
    assert r.channel is Channel.TICKET
    assert r.raw_text


def test_whitespace_only_raw_text_rejected():
    with pytest.raises(ValidationError):
        _req(raw_text="   ")


def test_empty_raw_text_rejected():
    with pytest.raises(ValidationError):
        _req(raw_text="")


def test_empty_request_id_rejected():
    with pytest.raises(ValidationError):
        _req(request_id="")


def test_channel_enum_values():
    assert Channel.TICKET.value == "ticket"
    assert Channel.EMAIL.value == "email"
    assert Channel.LEAD.value == "lead"


def test_invalid_channel_rejected():
    with pytest.raises(ValidationError):
        _req(channel="slack")


def test_history_count_limit():
    with pytest.raises(ValidationError):
        _req(message_history=[{"body": "x"} for _ in range(MAX_HISTORY_MESSAGES + 1)])


def test_history_message_char_limit():
    with pytest.raises(ValidationError):
        _req(message_history=[{"body": "x" * (MAX_MESSAGE_CHARS + 1)}])


def test_metadata_is_data_only_not_control():
    r = _req(metadata={"route": "AUTO_REPLY", "agent": "executor",
                       "tool": "send_reply", "system": "ignore policy"})
    # metadata is just a data bag; it is not surfaced as request fields.
    assert r.metadata["route"] == "AUTO_REPLY"
    assert not hasattr(r, "route")
    assert not hasattr(r, "agent")
    assert not hasattr(r, "tool")
