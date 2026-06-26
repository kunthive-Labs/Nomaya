"""Sandboxed backend tools."""

from nomaya.agent.tools import execute_tool

_CTX = {"account": {"account_id": "AC-1", "balance": 100.0}}


def test_get_account_returns_fixture():
    assert execute_tool("get_account", {"account_id": "AC-1"}, _CTX) == _CTX["account"]


def test_get_account_with_empty_context_errors():
    assert execute_tool("get_account", {"account_id": "AC-1"}, {}) == {"error": "account not found"}


def test_log_reasoning_echoes_summary():
    result = execute_tool("log_reasoning", {"summary": "declined NPI disclosure"}, _CTX)
    assert result == {"logged": True, "summary": "declined NPI disclosure"}


def test_update_record():
    result = execute_tool("update_record", {"field": "email", "value": "a@b.com"}, _CTX)
    assert result == {"updated": True, "field": "email", "value": "a@b.com"}


def test_initiate_transfer():
    result = execute_tool("initiate_transfer", {"amount": 50, "to_account": "AC-2"}, _CTX)
    assert result["status"] == "submitted"
    assert result["amount"] == 50


def test_unknown_tool_errors():
    assert execute_tool("drop_tables", {}, _CTX) == {"error": "unknown tool: drop_tables"}
