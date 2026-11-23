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


def test_irreversible_requires_confirmation(monkeypatch):
    spec = SPEC_BY_NAME["request_certificate"]
    params = {"certificate_type": "Bonafide", "reason": "scholarship application"}

    result = run_workflow(spec.name, params, confirmed=False)
    assert result["status"] == "needs_approval"
    assert "explicit" not in result["summary"].lower() or "irreversible" in result["summary"].lower()

    def fake_run_spec(received_spec, received_args, confirmed=False, dry_run=False, headless=True):
        assert received_spec is spec
        assert confirmed is True
        return {"status": "verified", "outputs": {"reference_number": "CERT-1001"}}

    monkeypatch.setattr("server.run_spec", fake_run_spec)
    result = run_workflow(spec.name, params, confirmed=True)
    assert result["status"] == "verified"
