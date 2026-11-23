"""Review generated ToolSpecs before adding them to the approved specs folder."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from models import ToolSpec, load_spec


ROOT = Path(__file__).resolve().parent
PENDING_SPECS_DIR = ROOT / "specs_pending"
APPROVED_SPECS_DIR = ROOT / "specs"
PARAM_NAME = re.compile(r"[a-z][a-z0-9_]*")


def list_pending_specs() -> list[Path]:
    return sorted(PENDING_SPECS_DIR.glob("*.json"))


def show_pending_specs(paths: list[Path]) -> None:
    if not paths:
        print("No pending ToolSpecs.")
        return
    print("Pending ToolSpecs:")
    for index, path in enumerate(paths, start=1):
        print(f"  {index}. {path.name}")


def choose_pending_spec(paths: list[Path]) -> Path | None:
    while True:
        choice = input("Select a number to review, or Q to quit: ").strip()
        if choice.lower() == "q":
            return None
        try:
            index = int(choice) - 1
        except ValueError:
            print("Enter a listed number or Q.")
            continue
        if 0 <= index < len(paths):
            return paths[index]
        print("That number is not in the list.")


def resolve_pending_spec(name: str) -> Path:
    if Path(name).name != name:
        raise ValueError("Specify a pending filename or tool name, not a path")
    filename = name if name.endswith(".json") else f"{name}.json"
    return PENDING_SPECS_DIR / filename


def update_spec_field(spec: ToolSpec, field: str, value: str) -> ToolSpec:
    if field not in {"name", "description"}:
        raise ValueError("Only the name and description can be edited here")
    data = spec.model_dump(mode="json")
    data[field] = value
    return ToolSpec.model_validate(data)


def _replace_parameter_placeholders(
    value: Any, placeholder: re.Pattern[str], replacement: str
) -> Any:
    if isinstance(value, str):
        return placeholder.sub(
            lambda match: (
                "{{" + replacement + "}}"
                if match.group(0).startswith("{{")
                else "{" + replacement + "}"
            ),
            value,
        )
    if isinstance(value, list):
        return [
            _replace_parameter_placeholders(item, placeholder, replacement)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _replace_parameter_placeholders(item, placeholder, replacement)
            for key, item in value.items()
        }
    return value


def rename_parameter(spec: ToolSpec, old_name: str, new_name: str) -> ToolSpec:
    if old_name not in spec.params:
        raise ValueError(f"No parameter named '{old_name}'")
    if not PARAM_NAME.fullmatch(new_name):
        raise ValueError("Parameter names must be snake_case identifiers")
    if new_name != old_name and new_name in spec.params:
        raise ValueError(f"A parameter named '{new_name}' already exists")
    if new_name == old_name:
        return spec

    data = spec.model_dump(mode="json")
    data["params"] = {
        new_name if name == old_name else name: value
        for name, value in data["params"].items()
    }
    placeholder = re.compile(
        r"\{\{"
        + re.escape(old_name)
        + r"\}\}|\{"
        + re.escape(old_name)
        + r"\}"
    )
    data["steps"] = [
        _replace_parameter_placeholders(step, placeholder, new_name)
        for step in data["steps"]
    ]
    return ToolSpec.model_validate(data)


def save_pending_spec(path: Path, spec: ToolSpec) -> None:
    data = spec.model_dump(mode="json")
    data["approved"] = False
    validated = ToolSpec.model_validate(data)
    path.write_text(
        json.dumps(validated.model_dump(mode="json"), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def approve_pending_spec(path: Path, spec: ToolSpec) -> Path:
    data = spec.model_dump(mode="json")
    data["approved"] = True
    approved_spec = ToolSpec.model_validate(data)
    destination = APPROVED_SPECS_DIR / f"{approved_spec.name}.json"
    with destination.open("x", encoding="utf-8") as file:
        json.dump(approved_spec.model_dump(mode="json"), file, indent=2, ensure_ascii=False)
        file.write("\n")
    path.unlink()
    return destination


def _show_validation_error(error: ValidationError) -> None:
    messages = [
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors(include_input=False)
    ]
    print("Edit not applied: " + "; ".join(messages))


def review_pending_spec(path: Path) -> None:
    spec = load_spec(path)
    while True:
        print()
        print(spec.plain_english())
        print()
        print("[A]pprove  [N]ame  [D]escription  [P]aram rename  [R]eject  [Q]uit")
        action = input("Choose an action: ").strip().lower()

        if action in {"a", "approve"}:
            try:
                destination = approve_pending_spec(path, spec)
            except FileExistsError:
                print(f"An approved spec already exists at {APPROVED_SPECS_DIR}.")
                continue
            print(f"Approved and saved to {destination}")
            return

        if action in {"n", "name"}:
            value = input("New snake_case tool name (blank to cancel): ").strip()
            if not value:
                continue
            try:
                updated = update_spec_field(spec, "name", value)
            except ValidationError as error:
                _show_validation_error(error)
                continue
            spec = updated

        elif action in {"d", "description"}:
            value = input("New description (blank to cancel): ").strip()
            if not value:
                continue
            spec = update_spec_field(spec, "description", value)

        elif action in {"p", "param", "rename"}:
            print("Parameters: " + ", ".join(spec.params))
            old_name = input("Parameter to rename (blank to cancel): ").strip()
            new_name = input("New snake_case parameter name: ").strip()
            if not old_name or not new_name:
                continue
            try:
                spec = rename_parameter(spec, old_name, new_name)
            except (ValueError, ValidationError) as error:
                if isinstance(error, ValidationError):
                    _show_validation_error(error)
                else:
                    print(f"Rename not applied: {error}")
                continue

        elif action in {"r", "reject"}:
            confirmation = input(
                f"Reject and delete {path.name}? [y/N]: "
            ).strip().lower()
            if confirmation == "y":
                path.unlink()
                print(f"Rejected and deleted {path.name}")
                return
            continue

        elif action in {"q", "quit"}:
            return

        else:
            print("Choose A, N, D, P, R, or Q.")
            continue

        save_pending_spec(path, spec)
        print("Pending spec updated.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review pending ToolSpecs")
    parser.add_argument(
        "pending",
        nargs="?",
        help="Pending filename or tool name; omit to choose from a list",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List pending specs without opening one",
    )
    args = parser.parse_args(argv)
    if args.list and args.pending:
        parser.error("Use either --list or a pending filename, not both")

    pending = list_pending_specs()
    if args.list:
        show_pending_specs(pending)
        return 0

    if args.pending:
        try:
            path = resolve_pending_spec(args.pending)
        except ValueError as error:
            parser.error(str(error))
        if not path.is_file():
            parser.error(f"No pending spec named '{args.pending}'")
    else:
        show_pending_specs(pending)
        if not pending:
            return 0
        path = choose_pending_spec(pending)
        if path is None:
            return 0

    review_pending_spec(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
