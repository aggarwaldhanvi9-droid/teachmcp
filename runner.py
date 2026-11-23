from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from models import ToolSpec, fill_value
from verify import verify


def _error(message: str, **extra: Any) -> dict:
    result = {
        "status": "error",
        "outputs": {},
        "steps": [],
        "evidence": {},
        "screenshot": None,
        "failed_step": None,
    }
    result.update(extra)
    result["error"] = message
    return result


def _validate_args(spec: ToolSpec, args: dict) -> str | None:
    if not isinstance(args, dict):
        return "args must be an object"

    for name, param in spec.params.items():
        if name not in args:
            if param.required:
                return f"Missing required argument: {name}"
            continue

        value = args[name]
        expected = param.type
        valid = (
            isinstance(value, str)
            if expected == "string"
            else isinstance(value, int) and not isinstance(value, bool)
            if expected == "integer"
            else isinstance(value, (int, float)) and not isinstance(value, bool)
            if expected == "number"
            else isinstance(value, bool)
            if expected == "boolean"
            else False
        )
        if not valid:
            return f"Argument '{name}' must be of type {expected}"
        if param.enum and value not in param.enum:
            return f"Argument '{name}' must be one of: {', '.join(param.enum)}"
    return None


def _join_url(base_url: str, path: str) -> str:
    if re.match(r"^https?://", path, re.I):
        return path
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _find_element(page, selectors: list[str], timeout_ms: int = 1000):
    last_error = None
    for index, selector in enumerate(selectors):
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator, selector, index > 0
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not find any selector {selectors}") from last_error


def _extract_table(locator) -> list[dict]:
    headers = []
    header_cells = locator.locator("thead tr th").all()
    if not header_cells:
        header_cells = locator.locator("tr").first.locator("th, td").all()
    headers = [cell.inner_text().strip() for cell in header_cells]

    rows = locator.locator("tbody tr").all()
    if not rows:
        all_rows = locator.locator("tr").all()
        rows = all_rows[1:] if all_rows else []

    table = []
    for row in rows:
        cells = row.locator("th, td").all()
        values = [cell.inner_text().strip() for cell in cells]
        if values:
            table.append({header: values[i] if i < len(values) else "" for i, header in enumerate(headers)})
    return table


def run_spec(spec: ToolSpec | dict, args: dict, confirmed: bool = False,
             dry_run: bool = False, headless: bool = True) -> dict:
    """Execute or plan a ToolSpec and return a serializable result."""
    try:
        if isinstance(spec, dict):
            spec = ToolSpec.model_validate(spec)
        elif not isinstance(spec, ToolSpec):
            return _error("spec must be a ToolSpec or JSON-compatible dict")
    except Exception as exc:
        return _error(f"Invalid spec: {exc}")

    if args is None:
        args = {}
    validation_error = _validate_args(spec, args)
    if validation_error:
        return _error(validation_error)

    base_result = {
        "status": "error",
        "outputs": {},
        "steps": [],
        "evidence": {},
        "screenshot": None,
        "failed_step": None,
    }

    if spec.irreversible and not confirmed:
        base_result["status"] = "needs_approval"
        base_result["summary"] = spec.plain_english()
        base_result["args"] = args
        base_result["steps"] = [
            {
                "index": index,
                "action": step.action,
                "description": step.description,
                "status": "planned",
            }
            for index, step in enumerate(spec.steps, 1)
        ]
        return base_result

    planned_steps = []
    for index, step in enumerate(spec.steps, 1):
        planned = {
            "index": index,
            "action": step.action,
            "description": step.description,
            "status": "planned",
        }
        if step.action == "goto":
            planned["url"] = _join_url(spec.base_url, fill_value(step.value, args) or "")
        elif step.value:
            planned["value"] = fill_value(step.value, args)
        planned_steps.append(planned)

    if dry_run:
        base_result["status"] = "verified"
        base_result["steps"] = planned_steps
        base_result["evidence"] = {"dry_run": True}
        return base_result

    runs_dir = Path("runs")
    runs_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = runs_dir / f"{spec.name}-{int(time.time() * 1000)}.png"

    page = None
    context = None
    browser = None
    p = None
    outputs: dict[str, Any] = {}
    step_results: list[dict] = []

    try:
        p = sync_playwright().start()
        profile = os.environ.get("TEACHMCP_PROFILE")
        if profile:
            context = p.chromium.launch_persistent_context(
                profile,
                headless=headless,
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

        for index, step in enumerate(spec.steps, 1):
            step_result = {
                "index": index,
                "action": step.action,
                "description": step.description,
                "status": "ok",
                "selector_used": None,
                "healed": False,
            }
            try:
                if step.action == "goto":
                    url = _join_url(spec.base_url, fill_value(step.value, args) or "")
                    page.goto(url, wait_until="domcontentloaded")
                    step_result["url"] = page.url
                elif step.action in ("click", "fill", "select", "extract"):
                    locator, selector_used, healed = _find_element(page, step.selectors)
                    step_result["selector_used"] = selector_used
                    step_result["healed"] = healed

                    if step.action == "click":
                        locator.click()
                        page.wait_for_load_state("domcontentloaded")
                    elif step.action == "fill":
                        locator.fill(fill_value(step.value, args) or "")
                    elif step.action == "select":
                        locator.select_option(value=fill_value(step.value, args) or "")
                    elif step.action == "extract":
                        if step.extract_as == "text":
                            value = locator.inner_text().strip()
                        else:
                            value = _extract_table(locator)
                        outputs[step.save_as] = value
                        step_result["value"] = value
            except Exception as exc:
                step_result["status"] = "failed"
                step_result["error"] = str(exc)
                step_results.append(step_result)
                base_result["status"] = "failed"
                base_result["failed_step"] = index
                base_result["steps"] = step_results
                base_result["outputs"] = {name: outputs[name] for name in spec.outputs if name in outputs}
                base_result["evidence"] = {"url": page.url, "error": str(exc)}
                page.screenshot(path=str(screenshot_path), full_page=True)
                base_result["screenshot"] = screenshot_path.as_posix()
                return base_result

            step_results.append(step_result)

        returned_outputs = {name: outputs[name] for name in spec.outputs if name in outputs}
        passed, verification_evidence = verify(spec.success_check, page, outputs)
        base_result["outputs"] = returned_outputs
        base_result["steps"] = step_results
        base_result["evidence"] = {
            "url": page.url,
            "title": page.title(),
            "success_check": {
                "type": spec.success_check.type,
                "value": spec.success_check.value,
                "passed": passed,
                "evidence": verification_evidence,
            },
        }
        page.screenshot(path=str(screenshot_path), full_page=True)
        base_result["screenshot"] = screenshot_path.as_posix()
        base_result["status"] = "verified" if passed else "failed"
        if not passed:
            base_result["failed_step"] = "success_check"
        return base_result
    except Exception as exc:
        base_result["status"] = "error"
        base_result["outputs"] = outputs
        base_result["steps"] = step_results
        base_result["evidence"] = {"error": str(exc)}
        base_result["error"] = str(exc)
        base_result["failed_step"] = len(step_results) + 1 if step_results else 1
        if page:
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
                base_result["screenshot"] = screenshot_path.as_posix()
            except Exception:
                pass
        return base_result
    finally:
        if context:
            context.close()
        elif browser:
            browser.close()
        if p:
            p.stop()
