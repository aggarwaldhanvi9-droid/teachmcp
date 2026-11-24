from __future__ import annotations

import sys
from typing import Any

from models import SuccessCheck


def _log(message: str) -> None:
    print(f"[VERIFY] {message}", file=sys.stderr, flush=True)


def _result(passed: bool, reason: str) -> tuple[bool, str]:
    if passed:
        _log("SUCCESS")
    else:
        _log(f"FAILED: {reason}")
    return passed, reason


def verify(check: SuccessCheck, page: Any = None, outputs: dict | None = None) -> tuple[bool, str]:
    """Verify a ToolSpec success check and return (passed, evidence)."""
    if not isinstance(check, SuccessCheck):
        if hasattr(check, "type") and hasattr(check, "value"):
            check = SuccessCheck.model_validate(check if isinstance(check, dict) else {"type": check.type, "value": check.value})
        else:
            check = SuccessCheck.model_validate(check)

    _log(f"Checking {check.type}: {check.value}")
    outputs = outputs or {}

    if check.type == "text_visible":
        if page is None:
            reason = f"Text not found: {check.value}"
            return _result(False, reason)
        try:
            count = page.get_by_text(check.value, exact=False).count()
            passed = count > 0
        except Exception:
            try:
                text = page.locator("body").inner_text()
                passed = check.value in text
            except Exception:
                passed = False
        reason = (
            f"Found text: {check.value}"
            if passed
            else f"Text not found: {check.value}"
        )
        return _result(passed, reason)

    if check.type == "selector_visible":
        if page is None:
            reason = f"Selector not visible: {check.value}"
            return _result(False, reason)
        try:
            locator = page.locator(check.value)
            passed = locator.count() > 0
            if passed and hasattr(locator, "is_visible"):
                passed = locator.is_visible()
        except Exception:
            passed = False
        reason = (
            f"Selector visible: {check.value}"
            if passed
            else f"Selector not visible: {check.value}"
        )
        return _result(passed, reason)

    if check.type == "url_contains":
        try:
            url = page.url
        except Exception:
            url = ""
        passed = bool(url) and check.value in url
        reason = (
            f"URL contains: {check.value} ({url})"
            if passed
            else f"URL does not contain: {check.value} ({url})"
        )
        return _result(passed, reason)

    if check.type == "output_nonempty":
        value = outputs.get(check.value)
        passed = bool(value)
        reason = (
            f"Output '{check.value}' is nonempty"
            if passed
            else f"Output '{check.value}' is empty or missing"
        )
        return _result(passed, reason)

    reason = f"Unknown success check type: {check.type}"
    return _result(False, reason)
