from __future__ import annotations

import os
import re
import sys
import time
import json
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

load_dotenv(Path(__file__).resolve().parent / ".env")

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from models import SuccessCheck, ToolSpec, fill_value
from verify import verify
from audit import log_run


def _log(message: str) -> None:
    print(f"[RUNNER] {message}", file=sys.stderr, flush=True)


def _log_result(spec: ToolSpec, args: dict, result: dict) -> dict:
    log_run(spec.name, args, result)
    return result


def _interactive_dom(page: Any, limit: int = 3000) -> str:
    try:
        snippet = page.evaluate(
            """() => {
                const elements = [...document.querySelectorAll(
                    'button,input,select,textarea,a,[role=\"button\"]'
                )].slice(0, 40);
                return elements.map((el, index) => {
                    const attrs = [];
                    for (const name of ['id','name','type','role','aria-label','class']) {
                        const value = el.getAttribute(name);
                        if (value) attrs.push(`${name}="${value}"`);
                    }
                    const text = (el.innerText || el.value || el.getAttribute('value') || '').trim();
                    return `<${el.tagName.toLowerCase()} ${attrs.join(' ')}>${text}</${el.tagName.toLowerCase()}>`;
                }).join('\\n');
            }"""
        )
        return (snippet or "")[:limit]
    except Exception:
        return ""


def _offline_repair(step: Any, failed_selectors: list[str], dom_snippet: str) -> dict:
    suggested = None
    action = step.action
    for line in dom_snippet.splitlines():
        lower = line.lower()
        if action == "click" and (lower.startswith("<button") or 'role="button"' in lower):
            match = re.search(r'id="([^"]+)"', line)
            if match:
                suggested = f"#{match.group(1)}"
                break
            match = re.search(r'name="([^"]+)"', line)
            if match:
                suggested = f"{line.split()[0][1:].split(' ')[0]}[name={match.group(1)}]"
                break
        if action == "fill" and "<textarea" in lower:
            match = re.search(r'id="([^"]+)"', line)
            if match:
                suggested = f"#{match.group(1)}"
                break
        if action == "select" and "<select" in lower:
            match = re.search(r'id="([^"]+)"', line)
            if match:
                suggested = f"#{match.group(1)}"
                break

    if suggested is None:
        suggested = "NO_VALID_SELECTOR_FOUND"

    return {
        "step": step.description,
        "failed_selectors": failed_selectors,
        "suggested_selector": suggested,
        "reason": "Offline fallback inferred a selector from the trimmed interactive DOM." if suggested != "NO_VALID_SELECTOR_FOUND" else "No unambiguous interactive element could be inferred from the page DOM.",
    }


def _propose_repair(step: Any, failed_selectors: list[str], dom_snippet: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _offline_repair(step, failed_selectors, dom_snippet)

    prompt = (
        "The following Playwright step selectors all failed.\n"
        f"Step: {step.description}\n"
        f"Action: {step.action}\n"
        f"Failed selectors: {json.dumps(failed_selectors)}\n"
        "Interactive DOM snippet:\n" + dom_snippet + "\n\n"
        "Return only a JSON object with keys step, failed_selectors, "
        "suggested_selector, and reason."
    )
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in getattr(response, "content", [])
            if getattr(block, "type", None) == "text"
        )
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("LLM response did not contain JSON")
        suggestion = json.loads(match.group(0))
        return {
            "step": suggestion.get("step", step.description),
            "failed_selectors": suggestion.get("failed_selectors", failed_selectors),
            "suggested_selector": suggestion.get("suggested_selector", "NO_VALID_SELECTOR_FOUND"),
            "reason": suggestion.get("reason", "Suggested by Anthropic."),
        }
    except Exception as exc:
        fallback = _offline_repair(step, failed_selectors, dom_snippet)
        fallback["reason"] += f" Anthropic unavailable: {type(exc).__name__}."
        return fallback


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
    headers = [(cell.text_content() or "").strip() for cell in header_cells]

    rows = locator.locator("tbody tr").all()
    if not rows:
        all_rows = locator.locator("tr").all()
        rows = all_rows[1:] if all_rows else []

    table = []
    for row in rows:
        cells = row.locator("th, td").all()
        values = [(cell.text_content() or "").strip() for cell in cells]
        if values:
            table.append({header: values[i] if i < len(values) else "" for i, header in enumerate(headers)})
    if table:
        return table

    cards = locator.locator("article.product_pod").all()
    books = []
    for card in cards:
        title_link = card.locator("h3 a").first
        price_label = card.locator(".price_color").first
        title = (
            title_link.get_attribute("title")
            or (title_link.text_content() or "").strip()
        )
        price = (price_label.text_content() or "").strip()
        if not title or not price:
            raise RuntimeError("Book card is missing its title or price")
        books.append({"title": title, "price": price})
    return books


def _select_option(locator: Any, option: str) -> str:
    try:
        locator.select_option(label=option)
        return "label"
    except Exception as label_error:
        _log("Option label was not found; retrying selection by value")
        try:
            locator.select_option(value=option)
            return "value"
        except Exception as value_error:
            raise RuntimeError(
                f"Could not select {option!r} by label ({label_error}) "
                f"or value ({value_error})"
            ) from value_error


def run_spec(spec: ToolSpec | dict, args: dict, confirmed: bool = False,
             dry_run: bool = False, headless: bool | None = None,
             declined: bool = False) -> dict:
    """Execute or plan a ToolSpec and return a serializable result."""
    try:
        if isinstance(spec, dict):
            spec = ToolSpec.model_validate(spec)
        elif not isinstance(spec, ToolSpec):
            return _error("spec must be a ToolSpec or JSON-compatible dict")
    except Exception as exc:
        return _error(f"Invalid spec: {exc}")

    if headless is None:
        headless = os.environ.get("TEACHMCP_HEADLESS") == "1"
    _log(f"Starting workflow: {spec.name}")

    if declined:
        _log("Workflow declined; no browser actions were run")
        return _log_result(
            spec,
            args if isinstance(args, dict) else {},
            {
                "status": "declined",
                "message": "User declined this workflow; no browser actions were run.",
                "outputs": {},
                "steps": [],
                "evidence": {"execution_started": False},
                "screenshot": None,
                "failed_step": None,
            },
        )

    if args is None:
        args = {}
    validation_error = _validate_args(spec, args)
    if validation_error:
        _log(f"FAILED: {validation_error}")
        result = _error(validation_error, error_code="invalid_arguments")
        tool_name = spec.name if isinstance(spec, ToolSpec) else "unknown"
        log_run(tool_name, args, result)
        return result

    base_result = {
        "status": "error",
        "outputs": {},
        "steps": [],
        "evidence": {},
        "screenshot": None,
        "failed_step": None,
    }

    if spec.irreversible and not confirmed:
        _log("Waiting for explicit approval before running this workflow")
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
        return _log_result(spec, args, base_result)

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
        _log(f"Dry run completed: {len(planned_steps)} step(s) planned")
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
    slow_mo = 600 if headless else 2000
    outputs: dict[str, Any] = {}
    step_results: list[dict] = []

    try:
        p = sync_playwright().start()
        profile = os.environ.get("TEACHMCP_PROFILE")
        _log(
            "Launching Chromium "
            f"(headless={headless}, slow_mo={slow_mo} ms)"
        )
        if profile:
            context = p.chromium.launch_persistent_context(
                profile,
                headless=headless,
                slow_mo=slow_mo,
                viewport={"width": 1280, "height": 800},
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()
        page.bring_to_front()

        for index, step in enumerate(spec.steps, 1):
            selectors = [
                fill_value(selector, args) or "" for selector in step.selectors
            ]
            if selectors:
                step_target = selectors[0]
            elif step.action == "goto":
                step_target = "navigation"
            else:
                step_target = ""
            target_suffix = f" ({step_target})" if step_target else ""
            _log(
                f"Step {index}/{len(spec.steps)}: "
                f"{step.description}{target_suffix}"
            )
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
                    locator, selector_used, healed = _find_element(page, selectors)
                    step_result["selector_used"] = selector_used
                    step_result["healed"] = healed
                    if healed:
                        _log(f"Selector fallback matched: {selector_used}")

                    if step.action in ("fill", "click"):
                        locator.evaluate(
                            "el => el.style.outline = '3px solid red'"
                        )
                        locator.evaluate(
                            "el => setTimeout(() => { el.style.outline = ''; }, 5000)"
                        )

                    if step.action == "click":
                        locator.click()
                        page.wait_for_load_state("domcontentloaded")
                    elif step.action == "fill":
                        locator.fill(fill_value(step.value, args) or "")
                    elif step.action == "select":
                        selected_by = _select_option(
                            locator, fill_value(step.value, args) or ""
                        )
                        _log(f"Selected option using {selected_by}")
                    elif step.action == "extract":
                        if step.extract_as == "text":
                            value = locator.inner_text().strip()
                        else:
                            value = _extract_table(locator)
                        outputs[step.save_as] = value
                        step_result["value"] = value
            except Exception as exc:
                _log(f"FAILED at step {index}: {exc}")
                step_result["status"] = "failed"
                step_result["error"] = str(exc)
                step_results.append(step_result)
                base_result["status"] = "failed"
                base_result["failed_step"] = index
                base_result["steps"] = step_results
                base_result["outputs"] = {name: outputs[name] for name in spec.outputs if name in outputs}
                failed_selectors = selectors if step.action in ("click", "fill", "select", "extract") else []
                dom_snippet = _interactive_dom(page) if page else ""
                base_result["evidence"] = {
                    "url": page.url,
                    "error": str(exc),
                    "failed_step_description": step.description,
                    "interactive_dom_snippet": dom_snippet,
                }
                if failed_selectors:
                    base_result["repair_suggestion"] = _propose_repair(step, failed_selectors, dom_snippet)
                page.screenshot(path=str(screenshot_path), full_page=True)
                base_result["screenshot"] = screenshot_path.as_posix()
                return _log_result(spec, args, base_result)

            step_results.append(step_result)

        returned_outputs = {name: outputs[name] for name in spec.outputs if name in outputs}
        success_check = spec.success_check.model_copy(
            update={
                "value": fill_value(spec.success_check.value, args) or ""
            },
        )
        passed, verification_evidence = verify(success_check, page, outputs)
        if not headless:
            page.wait_for_timeout(3000)
        base_result["outputs"] = returned_outputs
        base_result["steps"] = step_results
        base_result["evidence"] = {
            "url": page.url,
            "title": page.title(),
            "success_check": {
                "type": success_check.type,
                "value": success_check.value,
                "passed": passed,
                "evidence": verification_evidence,
            },
        }
        page.screenshot(path=str(screenshot_path), full_page=True)
        base_result["screenshot"] = screenshot_path.as_posix()
        base_result["status"] = "verified" if passed else "failed"
        if not passed:
            base_result["failed_step"] = "success_check"
            _log("FAILED: success check did not pass")
        else:
            _log(f"Workflow succeeded: {spec.name}")
        return _log_result(spec, args, base_result)
    except Exception as exc:
        _log(f"FAILED: {exc}")
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
        return _log_result(spec, args, base_result)
    finally:
        if context:
            context.close()
        elif browser:
            browser.close()
        if p:
            p.stop()
