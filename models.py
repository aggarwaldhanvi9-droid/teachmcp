"""
TeachMCP shared contract: the ToolSpec.

Person A (teach side) PRODUCES ToolSpecs (recorder -> generator -> review).
Person B (run side) CONSUMES ToolSpecs (runner -> verify -> MCP server).

Do NOT change this file without telling the other person.

Selector convention (Playwright selector strings, tried in order):
    "#submit-btn"                          css
    "button[type=submit]"                  css
    "text=Submit Request"                  visible text
    "role=button[name='Submit Request']"   accessible role + name
Put the most specific / most stable selector FIRST, fallbacks after it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

PLACEHOLDER = re.compile(r"\{(\w+)\}")


class ParamSpec(BaseModel):
    """One input the agent must provide when calling the tool."""
    type: Literal["string", "integer", "number", "boolean"] = "string"
    description: str
    enum: list[str] | None = None          # allowed values, if limited
    required: bool = True


class Step(BaseModel):
    action: Literal["goto", "click", "fill", "select", "extract"]
    description: str                        # plain-English line shown in review
    # goto: use `value` as the path/URL (may contain {params})
    # click/fill/select/extract: `selectors` are tried in order (self-healing)
    selectors: list[str] = Field(default_factory=list)
    value: str | None = None                # text to type / option to choose / URL
    # extract only:
    extract_as: Literal["text", "table"] | None = None
    save_as: str | None = None              # name of the output value

    @model_validator(mode="after")
    def check_step(self):
        if self.action == "goto":
            if not self.value:
                raise ValueError("goto needs `value` (path or URL)")
        else:
            if not self.selectors:
                raise ValueError(f"{self.action} needs at least one selector")
        if self.action in ("fill", "select") and self.value is None:
            raise ValueError(f"{self.action} needs `value`")
        if self.action == "extract" and not (self.extract_as and self.save_as):
            raise ValueError("extract needs `extract_as` and `save_as`")
        return self


class SuccessCheck(BaseModel):
    """How the runner PROVES the task worked. Never report success without it."""
    type: Literal["text_visible", "selector_visible", "url_contains", "output_nonempty"]
    value: str                              # text / selector / url part / output name


class ToolSpec(BaseModel):
    name: str                               # snake_case, becomes the MCP tool name
    description: str                        # what the agent reads to decide to use it
    base_url: str = "http://localhost:5000"
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    steps: list[Step]
    success_check: SuccessCheck
    outputs: list[str] = Field(default_factory=list)   # save_as names to return
    irreversible: bool = False              # True -> runner must ask approval first
    approved: bool = False                  # set True only after human review

    @model_validator(mode="after")
    def check_spec(self):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError("name must be snake_case")

        saved = {s.save_as for s in self.steps if s.save_as}

        # every {placeholder} must be a declared param
        for s in self.steps:
            for text in [s.value or ""]:
                for ph in PLACEHOLDER.findall(text):
                    if ph not in self.params:
                        raise ValueError(f"step uses {{{ph}}} but it is not in params")

        # outputs must come from extract steps
        for o in self.outputs:
            if o not in saved:
                raise ValueError(f"output '{o}' is never produced by an extract step")

        if self.success_check.type == "output_nonempty" and self.success_check.value not in saved:
            raise ValueError("success_check output is never produced")
        return self

    # ---- helpers both sides can use -------------------------------------
    def mcp_input_schema(self) -> dict:
        """JSON Schema for the MCP tool's arguments (Person B uses this)."""
        props, required = {}, []
        for name, p in self.params.items():
            prop = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            props[name] = prop
            if p.required:
                required.append(name)
        return {"type": "object", "properties": props, "required": required}

    def plain_english(self) -> str:
        """Readable summary for the human review screen (Person A uses this)."""
        lines = [f"Tool: {self.name}", self.description, ""]
        if self.params:
            lines.append("Inputs:")
            lines += [f"  - {n}: {p.description}" for n, p in self.params.items()]
            lines.append("")
        lines.append("Steps:")
        lines += [f"  {i}. {s.description}" for i, s in enumerate(self.steps, 1)]
        lines.append("")
        lines.append(f"Success check: {self.success_check.type} -> {self.success_check.value}")
        if self.irreversible:
            lines.append("WARNING: irreversible action, asks for approval before running.")
        return "\n".join(lines)


def fill_value(template: str | None, args: dict) -> str | None:
    """Replace {param} placeholders with actual argument values."""
    if template is None:
        return None
    return PLACEHOLDER.sub(lambda m: str(args[m.group(1)]), template)


def load_spec(path: str | Path) -> ToolSpec:
    return ToolSpec.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def load_all(folder: str | Path = "specs") -> list[ToolSpec]:
    return [load_spec(p) for p in sorted(Path(folder).glob("*.json"))]


if __name__ == "__main__":
    # `python models.py` -> validates every spec in specs/
    ok = True
    for p in sorted(Path("specs").glob("*.json")):
        try:
            spec = load_spec(p)
            print(f"OK   {p.name}  ->  tool '{spec.name}'")
        except Exception as e:
            ok = False
            print(f"FAIL {p.name}\n{e}")
    sys.exit(0 if ok else 1)
