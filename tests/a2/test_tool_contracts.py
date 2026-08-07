"""A2A: typed read-tool contracts — schema bounds, validation, extra=forbid."""
import pytest
from pydantic import ValidationError

from agent.tooling import (
    CustomerContextArgs,
    GetTicketArgs,
    SearchKnowledgeArgs,
    TicketHistoryArgs,
)


def test_search_knowledge_args_valid():
    a = SearchKnowledgeArgs(query="how do I download my invoice", top_k=3)
    assert a.top_k == 3


def test_search_knowledge_args_bounds():
    with pytest.raises(ValidationError):
        SearchKnowledgeArgs(query="")          # min_length=1
    with pytest.raises(ValidationError):
        SearchKnowledgeArgs(query="x", top_k=0)   # ge=1
    with pytest.raises(ValidationError):
        SearchKnowledgeArgs(query="x", top_k=99)  # le=5


def test_get_ticket_args_valid_and_required():
    assert GetTicketArgs(ticket_id="T-1").ticket_id == "T-1"
    with pytest.raises(ValidationError):
        GetTicketArgs(ticket_id="")
    with pytest.raises(ValidationError):
        GetTicketArgs()  # ticket_id required


def test_args_extra_forbidden():
    # A self-approval field must not be able to sneak into a read tool's args.
    with pytest.raises(ValidationError):
        GetTicketArgs(ticket_id="T-1", approved=True)   # extra="forbid"
    with pytest.raises(ValidationError):
        SearchKnowledgeArgs(query="x", route="AUTO_REPLY")  # extra="forbid"


def test_customer_and_history_args():
    assert CustomerContextArgs(customer_context={"plan": "team"}).customer_context["plan"] == "team"
    assert TicketHistoryArgs(user_id="u-1").user_id == "u-1"
    with pytest.raises(ValidationError):
        TicketHistoryArgs(user_id="")
