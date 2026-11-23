from __future__ import annotations

from typing import Any

from models import SuccessCheck


def verify(check: SuccessCheck, page: Any = None, outputs: dict | None = None) -> tuple[bool, str]:
    """Verify a ToolSpec success check and return (passed, evidence)."""
    if not isinstance(check, SuccessCheck):
        if hasattr(check, "type") and hasattr(check, "value"):
            check = SuccessCheck.model_validate(check if isinstance(check, dict) else {"type": check.type, "value": check.value})
        else:
            check = SuccessCheck.model_validate(check)

    outputs = outputs or {}

    if check.type == "text_visible":
        if page is None:
            return False, f"Text not found: {check.value}"
        try:
            count = page.get_by_text(check.value, exact=False).count()
            passed = count > 0
        except Exception:
            try:
                text = page.locator("body").inner_text()
                passed = check.value in text
            except Exception:
                passed = False
        return (passed, f"Found text: {check.value}" if passed else f"Text not found: {check.value}")

    if check.type == "selector_visible":
        if page is None:
            return False, f"Selector not visible: {check.value}"
        try:
            locator = page.locator(check.value)
            passed = locator.count() > 0
            if passed and hasattr(locator, "is_visible"):
                passed = locator.is_visible()
        except Exception:
            passed = False
        return (
            (True, f"Selector visible: {check.value}")
            if passed
            else (False, f"Selector not visible: {check.value}")
        )

    if check.type == "url_contains":
        try:
            url = page.url
        except Exception:
            url = ""
        passed = bool(url) and check.value in url
        return (
            (True, f"URL contains: {check.value} ({url})")
            if passed
            else (False, f"URL does not contain: {check.value} ({url})")
        )

    if check.type == "output_nonempty":
        value = outputs.get(check.value)
        passed = bool(value)
        return (
            (True, f"Output '{check.value}' is nonempty")
            if passed
            else (False, f"Output '{check.value}' is empty or missing")
        )

    return False, f"Unknown success check type: {check.type}"
