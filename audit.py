from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent
AUDIT_PATH = ROOT / "runs" / "audit.jsonl"
SENSITIVE_KEY = re.compile(r"(password|otp|token|secret|key)", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    return value


def log_run(tool: str, args: dict, result: dict) -> dict:
    """Append one redacted run record to runs/audit.jsonl and return it."""
    healed_steps = []
    for step in result.get("steps", []):
        if step.get("healed") is True:
            healed_steps.append(f"{step.get('index', '?')}: {step.get('description', '')}".rstrip(": "))

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "args": redact(args if isinstance(args, dict) else {}),
        "status": result.get("status"),
        "healed_steps": healed_steps,
        "screenshot": result.get("screenshot"),
    }

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a", encoding="utf-8") as audit_file:
        audit_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_recent(limit: int = 20) -> list[dict]:
    if not AUDIT_PATH.exists():
        return []

    records = []
    with AUDIT_PATH.open("r", encoding="utf-8") as audit_file:
        for line in audit_file:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records[-limit:]


def print_recent(limit: int = 20) -> None:
    records = read_recent(limit)
    if not records:
        print("No audit runs recorded.")
        return

    headers = ["Timestamp", "Tool", "Status", "Healed steps", "Screenshot"]
    rows = [
        [
            record.get("timestamp", ""),
            record.get("tool", ""),
            record.get("status", ""),
            ", ".join(record.get("healed_steps", [])) or "-",
            record.get("screenshot", "") or "-",
        ]
        for record in records
    ]

    widths = [
        max(len(headers[i]), *(len(str(row[i])) for row in rows))
        for i in range(len(headers))
    ]

    def format_row(row):
        return " | ".join(str(value).ljust(widths[i]) for i, value in enumerate(row))

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(format_row(row))


if __name__ == "__main__":
    print_recent()
