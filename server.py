from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from models import load_all
from runner import run_spec


SPECS_DIR = Path(__file__).parent / "specs"
SPECS = load_all(SPECS_DIR)
APPROVED_SPECS = [spec for spec in SPECS if spec.approved is True]
SPEC_BY_NAME = {spec.name: spec for spec in APPROVED_SPECS}

mcp = FastMCP(
    "TeachMCP",
    instructions="Approved TeachMCP workflows. Irreversible workflows require explicit user consent.",
)


def list_workflows() -> list[dict]:
    """Return metadata for approved workflows."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "irreversible": spec.irreversible,
            "params": {
                name: {
                    "type": param.type,
                    "description": param.description,
                    "enum": param.enum,
                    "required": param.required,
                }
                for name, param in spec.params.items()
            },
        }
        for spec in APPROVED_SPECS
    ]


def run_workflow(name: str, params: dict[str, Any] | None = None, confirmed: bool = False) -> dict:
    """Run an approved workflow by name."""
    spec = SPEC_BY_NAME.get(name)
    if spec is None:
        return {
            "status": "error",
            "error": f"Unknown or unapproved workflow: {name}",
            "outputs": {},
            "steps": [],
            "evidence": {},
            "screenshot": None,
            "failed_step": None,
        }
    return run_spec(spec, params or {}, confirmed=confirmed)


mcp.tool()(list_workflows)
mcp.tool()(run_workflow)


def _register_workflow_tool(spec) -> None:
    def workflow(**kwargs):
        confirmed = bool(kwargs.pop("confirmed", False))
        return run_workflow(spec.name, kwargs, confirmed=confirmed)

    description = spec.description
    if spec.irreversible:
        description += (
            "\n\nThis workflow is irreversible. Present the returned `needs_approval` "
            "summary to the user, obtain explicit consent, and only re-call this tool "
            "with `confirmed=true` after that consent."
        )

    tool = mcp._tool_manager.add_tool(
        workflow,
        name=spec.name,
        description=description,
    )

    input_schema = spec.mcp_input_schema()
    input_schema["properties"]["confirmed"] = {
        "type": "boolean",
        "description": "Set true only after the user explicitly approves this irreversible workflow.",
        "default": False,
    }
    if "required" not in input_schema:
        input_schema["required"] = []
    tool.parameters = input_schema


for approved_spec in APPROVED_SPECS:
    _register_workflow_tool(approved_spec)


if __name__ == "__main__":
    mcp.run(transport="stdio")
