import json
from pathlib import Path

from audit import AUDIT_PATH, log_run, read_recent, redact
from models import ToolSpec
from runner import run_spec


def test_redaction_recursive():
    value = {
        "password": "hidden",
        "login": "student",
        "otp_code": "123456",
        "nested": {"api_token": "abc", "safe": "visible"},
        "items": [{"secret": "x"}, {"key_name": "y"}],
    }
    redacted = redact(value)

    assert redacted["password"] == "[REDACTED]"
    assert redacted["otp_code"] == "[REDACTED]"
    assert redacted["nested"]["api_token"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "visible"
    assert redacted["items"][0]["secret"] == "[REDACTED]"
    assert redacted["items"][1]["key_name"] == "[REDACTED]"


def test_log_run_appends_jsonl(tmp_path, monkeypatch):
    audit_path = tmp_path / "runs" / "audit.jsonl"
    monkeypatch.setattr("audit.AUDIT_PATH", audit_path)

    result = {
        "status": "verified",
        "screenshot": "runs/test.png",
        "steps": [
            {"index": 2, "description": "Fallback button", "healed": True},
            {"index": 3, "description": "Normal field", "healed": False},
        ],
    }
    record = log_run(
        "request_certificate",
        {"reason": "test", "password": "do-not-log", "api_key": "do-not-log"},
        result,
    )

    assert audit_path.exists()
    with audit_path.open("r", encoding="utf-8") as audit_file:
        lines = audit_file.readlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved["tool"] == "request_certificate"
    assert saved["args"]["password"] == "[REDACTED]"
    assert saved["args"]["api_key"] == "[REDACTED]"
    assert saved["args"]["reason"] == "test"
    assert saved["status"] == "verified"
    assert saved["screenshot"] == "runs/test.png"
    assert saved["healed_steps"] == ["2: Fallback button"]
    assert saved["timestamp"]
    assert record == saved


def test_runner_logs_non_dry_run(tmp_path, monkeypatch):
    audit_path = tmp_path / "runs" / "audit.jsonl"
    monkeypatch.setattr("audit.AUDIT_PATH", audit_path)

    spec = ToolSpec.model_validate({
        "name": "approval_test",
        "description": "Approval test",
        "params": {},
        "steps": [{"action": "goto", "description": "Open page", "value": "/"}],
        "success_check": {"type": "url_contains", "value": "/"},
        "irreversible": True,
        "approved": True,
    })
    result = run_spec(spec, {}, confirmed=False)

    assert result["status"] == "needs_approval"
    assert audit_path.exists()
    saved = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert saved["tool"] == "approval_test"
    assert saved["status"] == "needs_approval"


def test_invalid_enum_is_clear_in_runner_result_and_audit(tmp_path, monkeypatch):
    audit_path = tmp_path / "runs" / "audit.jsonl"
    monkeypatch.setattr("audit.AUDIT_PATH", audit_path)

    spec = ToolSpec.model_validate({
        "name": "certificate_enum_test",
        "description": "Validate certificate type",
        "params": {
            "cert_type": {
                "type": "string",
                "description": "Type of certificate",
                "enum": ["Bonafide", "No Dues", "Character"],
                "required": True,
            }
        },
        "steps": [
            {"action": "goto", "description": "Open page", "value": "/certificate"}
        ],
        "success_check": {"type": "text_visible", "value": "Request submitted"},
        "approved": True,
    })

    result = run_spec(spec, {"cert_type": "Invalid"})

    assert result["status"] == "error"
    assert result["error"] == (
        "Argument 'cert_type' must be one of: Bonafide, No Dues, Character"
    )
    saved = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert saved["error_code"] == "invalid_arguments"
    assert saved["error"] == result["error"]
