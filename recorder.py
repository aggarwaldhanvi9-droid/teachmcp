"""Record browser interactions as reusable ToolSpec steps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from playwright.sync_api import BrowserContext, Playwright, sync_playwright


def _log(message: str) -> None:
    print(f"[RECORDER] {message}", flush=True)


RECORDER_SCRIPT = r"""
(() => {
  const escapeAttribute = (value) => value
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\a ");

  const accessibleName = (element) => {
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      const text = labelledBy.split(/\s+/)
        .map((id) => document.getElementById(id)?.innerText || "")
        .join(" ").trim();
      if (text) return text;
    }

    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel) return ariaLabel.trim();
    if (element.labels?.length) {
      const label = Array.from(element.labels)
        .map((item) => item.innerText || item.textContent || "")
        .join(" ").trim();
      if (label) return label;
    }

    if (element.matches("button, a, [role=button], [role=link], [role=tab]")) {
      const text = (element.innerText || element.textContent || "").trim();
      if (text) return text;
    }
    return (element.getAttribute("alt") || element.getAttribute("title") || "").trim();
  };

  const roleFor = (element) => {
    const explicitRole = element.getAttribute("role");
    if (explicitRole) return explicitRole.split(/\s+/)[0];
    const tag = element.tagName.toLowerCase();
    if (tag === "button") return "button";
    if (tag === "a" && element.hasAttribute("href")) return "link";
    if (tag === "select") return element.multiple ? "listbox" : "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "table") return "table";
    if (tag === "input") {
      const type = (element.getAttribute("type") || "text").toLowerCase();
      if (["button", "submit", "reset", "image"].includes(type)) return "button";
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "password" || type === "text" || type === "email" ||
          type === "search" || type === "tel" || type === "url" || type === "number") {
        return "textbox";
      }
    }
    return "";
  };

  const selectorsFor = (element) => {
    const selectors = [];
    const add = (selector) => {
      if (selector && !selectors.includes(selector)) selectors.push(selector);
    };
    const tag = element.tagName.toLowerCase();
    const testId = element.getAttribute("data-testid");
    if (testId) add(`[data-testid="${escapeAttribute(testId)}"]`);
    if (element.id) add(`#${CSS.escape(element.id)}`);

    const role = roleFor(element);
    const name = accessibleName(element);
    if (role) {
      add(name
        ? `role=${role}[name=${JSON.stringify(name)}]`
        : `role=${role}`);
    }
    if (name && element.matches("button, a, [role=button], [role=link], [role=tab]")) {
      add(`text=${JSON.stringify(name)}`);
    }

    const css = [];
    for (const attribute of ["name", "type", "aria-label", "placeholder"]) {
      const value = element.getAttribute(attribute);
      if (value) css.push(`${tag}[${attribute}="${escapeAttribute(value)}"]`);
    }
    const classes = Array.from(element.classList)
      .filter(Boolean)
      .map((className) => `.${CSS.escape(className)}`)
      .join("");
    if (classes) css.push(`${tag}${classes}`);
    css.push(tag);
    for (const selector of css) add(selector);
    return selectors;
  };

  const send = (payload) => {
    if (typeof window.__teachmcpRecord === "function") {
      window.__teachmcpRecord(payload).catch((error) => console.error(error));
    }
  };

  let extractMode = false;
  let pointerPosition = null;
  const banner = document.createElement("div");
  banner.dataset.teachmcpRecorderUi = "extract-banner";
  banner.textContent = "EXTRACT MODE: click element";
  const outline = document.createElement("div");
  outline.dataset.teachmcpRecorderUi = "extract-outline";
  const recorderStyle = document.createElement("style");
  recorderStyle.textContent = `
    [data-teachmcp-recorder-ui="extract-banner"] {
      all: initial !important;
      position: fixed !important;
      top: 12px !important;
      right: 12px !important;
      z-index: 2147483647 !important;
      display: none !important;
      padding: 8px 12px !important;
      border-radius: 4px !important;
      background: #991b1b !important;
      color: #ffffff !important;
      font: 600 13px/1.4 sans-serif !important;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35) !important;
      pointer-events: none !important;
    }
    [data-teachmcp-recorder-ui="extract-banner"].active {
      display: block !important;
    }
    [data-teachmcp-recorder-ui="extract-outline"] {
      all: initial !important;
      position: fixed !important;
      z-index: 2147483646 !important;
      display: none !important;
      box-sizing: border-box !important;
      border: 2px solid #ff0000 !important;
      background: transparent !important;
      pointer-events: none !important;
    }
    [data-teachmcp-recorder-ui="extract-outline"].active {
      display: block !important;
    }
  `;
  const installRecorderUi = () => {
    if (document.documentElement) {
      document.documentElement.append(recorderStyle, banner, outline);
    }
  };
  if (document.documentElement) {
    installRecorderUi();
  } else {
    document.addEventListener("DOMContentLoaded", installRecorderUi, { once: true });
  }

  const hideOutline = () => {
    outline.classList.remove("active");
  };
  const updateOutline = (x, y) => {
    const element = document.elementFromPoint(x, y);
    if (!element || element === banner || banner.contains(element) ||
        element === outline || outline.contains(element)) {
      hideOutline();
      return;
    }
    const rect = element.getBoundingClientRect();
    outline.style.setProperty("left", `${rect.left}px`, "important");
    outline.style.setProperty("top", `${rect.top}px`, "important");
    outline.style.setProperty("width", `${rect.width}px`, "important");
    outline.style.setProperty("height", `${rect.height}px`, "important");
    outline.classList.add("active");
  };
  const setExtractMode = (enabled) => {
    extractMode = enabled;
    banner.classList.toggle("active", enabled);
    if (!enabled) {
      hideOutline();
    } else if (pointerPosition) {
      updateOutline(pointerPosition.x, pointerPosition.y);
    }
  };

  document.addEventListener("pointermove", (event) => {
    pointerPosition = { x: event.clientX, y: event.clientY };
    if (extractMode) updateOutline(event.clientX, event.clientY);
  }, true);
  document.addEventListener("pointerout", (event) => {
    if (extractMode && !event.relatedTarget) {
      pointerPosition = null;
      hideOutline();
    }
  }, true);
  window.addEventListener("scroll", () => {
    if (extractMode && pointerPosition) {
      updateOutline(pointerPosition.x, pointerPosition.y);
    }
  }, true);
  window.addEventListener("resize", () => {
    if (extractMode && pointerPosition) {
      updateOutline(pointerPosition.x, pointerPosition.y);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "e") {
      setExtractMode(true);
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);

  document.addEventListener("click", (event) => {
    const clicked = event.target instanceof Element ? event.target : null;
    if (!clicked) return;

    if (extractMode) {
      setExtractMode(false);
      event.preventDefault();
      event.stopImmediatePropagation();
      const element = clicked.closest("table") || clicked;
      const extractAs = element.matches("table") ? "table" : "text";
      send({
        action: "extract",
        description: `Extract ${extractAs} from the selected element`,
        selectors: selectorsFor(element),
        extract_as: extractAs,
      });
      return;
    }

    const target = clicked.closest(
      "button, a[href], input[type=button], input[type=submit], " +
      "input[type=reset], input[type=checkbox], input[type=radio], " +
      "[role=button], [role=link], [role=tab], [role=menuitem], [onclick]"
    );
    if (!target || target.matches('input[type="password" i]')) return;
    const name = accessibleName(target) || target.tagName.toLowerCase();
    send({
      action: "click",
      description: `Click ${name}`,
      selectors: selectorsFor(target),
    });
  }, true);

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.matches('input[type="password" i]')) return;

    if (target.matches("select")) {
      const name = accessibleName(target) || "option";
      send({
        action: "select",
        description: `Choose ${name}`,
        selectors: selectorsFor(target),
        value: target.value,
      });
      return;
    }

    if (target.matches("textarea, input:not([type]), input[type=text i], " +
        "input[type=email i], input[type=search i], input[type=tel i], " +
        "input[type=url i], input[type=number i]")) {
      const name = accessibleName(target) || target.getAttribute("name") || "field";
      send({
        action: "fill",
        description: `Fill ${name}`,
        selectors: selectorsFor(target),
        value: target.value,
      });
    }
  }, true);
})();
"""


def build_recording(
    url: str, captured_steps: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "url": url,
        "steps": [
            {
                "action": "goto",
                "description": "Open the starting page",
                "value": url,
            },
            *captured_steps,
        ],
    }


def save_recording(output: Path, recording: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(recording, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_recorder(url: str, output: Path, playwright: Playwright) -> int:
    captured_steps: list[dict[str, Any]] = []

    def record_event(_source: dict[str, Any], payload: dict[str, Any]) -> None:
        action = payload.get("action")
        if action not in {"click", "fill", "select", "extract"}:
            raise ValueError(f"Unsupported recorded action: {action!r}")

        selectors = payload.get("selectors")
        if not isinstance(selectors, list) or not all(
            isinstance(selector, str) and selector for selector in selectors
        ):
            raise ValueError("A recorded action must include selector strings")

        step: dict[str, Any] = {
            "action": action,
            "description": payload["description"],
            "selectors": selectors,
        }
        if action in {"fill", "select"}:
            step["value"] = payload["value"]
        if action == "extract":
            step["extract_as"] = payload["extract_as"]
            extract_number = sum(
                captured_step["action"] == "extract"
                for captured_step in captured_steps
            ) + 1
            step["save_as"] = f"extracted_{payload['extract_as']}_{extract_number}"
        captured_steps.append(step)
        selector = selectors[0]
        if action == "click":
            _log(f"Click captured: {selector}")
        elif action in {"fill", "select"}:
            _log(f"Input captured: {selector}")
        else:
            _log(f"Extract captured: {selector}")

    browser = playwright.chromium.launch(headless=False)
    _log("Browser launched")
    context: BrowserContext = browser.new_context()
    context.expose_binding("__teachmcpRecord", record_event)
    context.add_init_script(RECORDER_SCRIPT)
    page = context.new_page()

    def log_navigation(frame) -> None:
        if frame == page.main_frame:
            _log(f"Navigation detected: {frame.url}")

    page.on("framenavigated", log_navigation)

    try:
        page.goto(url)
        _log("Recording in Chromium. Use Ctrl+Shift+E, then click to extract.")
        _log("Close the browser window to save the recording.")
        while context.pages:
            context.pages[0].wait_for_timeout(250)
    finally:
        browser.close()
        save_recording(output, build_recording(url, captured_steps))
        _log(f"Recording saved successfully: {output}")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record a browser workflow")
    parser.add_argument("--url", required=True, help="URL to open in Chromium")
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Path for the recording JSON, e.g. recordings/name.json",
    )
    args = parser.parse_args(argv)

    with sync_playwright() as playwright:
        return run_recorder(args.url, args.out, playwright)


if __name__ == "__main__":
    raise SystemExit(main())
