import asyncio
import inspect
import threading
from pathlib import Path

import pytest

import server
from models import ToolSpec
from server import APPROVED_SPECS, SPEC_BY_NAME, list_workflows, run_workflow


def test_unapproved_specs_excluded():
    unapproved = ToolSpec.model_validate({
        "name": "unapproved_test",
        "description": "Unapproved test workflow",
        "steps": [{"action": "goto", "description": "Open page", "value": "/"}],
        "success_check": {"type": "url_contains", "value": "/"},
        "approved": False,
    })
    assert unapproved.name not in SPEC_BY_NAME

    names = {workflow["name"] for workflow in list_workflows()}
    assert "check_attendance" in names
    assert "request_certificate" in names
    assert "unapproved_test" not in names


def test_dynamic_tool_schemas_match_spec():
    tools = {tool.name: tool for tool in server.mcp._tool_manager.list_tools()}

    for spec in APPROVED_SPECS:
        assert spec.name in tools
        expected = spec.mcp_input_schema()
        expected["properties"]["confirmed"] = {
            "type": "boolean",
            "description": "Set true only after the user explicitly approves this irreversible workflow.",
            "default": False,
        }
        assert tools[spec.name].parameters == expected


def test_dynamic_tool_accepts_named_mcp_arguments(monkeypatch):
    tool = next(
        tool
        for tool in server.mcp._tool_manager.list_tools()
        if tool.name == "request_certificate"
    )
    signature = inspect.signature(tool.fn)
    assert list(signature.parameters) == [
        "certificate_type",
        "reason",
        "confirmed",
    ]
    assert signature.parameters["confirmed"].default is False

    received = {}

    async def fake_run_workflow(name, params, confirmed=False):
        received.update(name=name, params=params, confirmed=confirmed)
        return {"status": "needs_approval"}

    monkeypatch.setattr(server, "run_workflow", fake_run_workflow)
    result = asyncio.run(
        tool.run(
            {
                "certificate_type": "Bonafide",
                "reason": "scholarship",
                "confirmed": True,
            }
        )
    )

    assert result == {"status": "needs_approval"}
    assert received == {
        "name": "request_certificate",
        "params": {
            "certificate_type": "Bonafide",
            "reason": "scholarship",
        },
        "confirmed": True,
    }


def test_irreversible_requires_confirmation(monkeypatch):
    spec = SPEC_BY_NAME["request_certificate"]
    params = {"certificate_type": "Bonafide", "reason": "scholarship application"}

    result = asyncio.run(run_workflow(spec.name, params, confirmed=False))
    assert result["status"] == "needs_approval"
    assert "explicit" not in result["summary"].lower() or "irreversible" in result["summary"].lower()

    event_loop_thread = threading.get_ident()

    def fake_run_spec(received_spec, received_args, confirmed=False, dry_run=False, headless=True):
        assert received_spec is spec
        assert confirmed is True
        assert threading.get_ident() != event_loop_thread
        return {"status": "verified", "outputs": {"reference_number": "CERT-1001"}}

    monkeypatch.setattr("server.run_spec", fake_run_spec)
    result = asyncio.run(run_workflow(spec.name, params, confirmed=True))
    assert result["status"] == "verified"
