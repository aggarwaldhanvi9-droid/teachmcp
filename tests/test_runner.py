import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from models import load_spec
from runner import _extract_table, _select_option, run_spec


ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session", autouse=True)
def fake_server():
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "tests" / "fake_server.py")],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto("http://127.0.0.1:5000/attendance", timeout=500)
                browser.close()
                break
        except Exception:
            time.sleep(0.1)
    else:
        process.terminate()
        raise RuntimeError("fake server did not start")
    yield
    process.terminate()
    process.wait(timeout=5)


def test_attendance_spec():
    spec = load_spec(ROOT / "specs" / "check_attendance.json")
    spec.base_url = "http://127.0.0.1:5000"
    result = run_spec(spec, {}, headless=True)
    assert result["status"] == "verified"
    assert result["outputs"]["attendance"]
    assert result["outputs"]["attendance"][0]["Subject"] == "Mathematics"
    assert result["evidence"]["url"].endswith("/attendance")
    assert result["screenshot"]


def test_argument_validation():
    spec = load_spec(ROOT / "specs" / "request_certificate.json")
    result = run_spec(spec, {})
    assert result["status"] == "error"
    assert "Missing required argument" in result["error"]

    result = run_spec(spec, {"certificate_type": "Invalid", "reason": "test"})
    assert result["status"] == "error"


def test_dry_run_no_browser():
    spec = load_spec(ROOT / "specs" / "check_attendance.json")
    result = run_spec(spec, {}, dry_run=True)
    assert result["status"] == "verified"
    assert result["evidence"]["dry_run"] is True
    assert len(result["steps"]) == 2
    assert result["screenshot"] is None


def test_extract_table_preserves_header_case_under_css_transform():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            """<style>th { text-transform: uppercase; }</style>
            <table id="attendance-table">
              <thead><tr><th>Subject</th><th>Percentage</th></tr></thead>
              <tbody><tr><td>Physics</td><td>70%</td></tr></tbody>
            </table>"""
        )

        rows = _extract_table(page.locator("#attendance-table"))
        browser.close()

    assert rows == [{"Subject": "Physics", "Percentage": "70%"}]


def test_extract_table_returns_book_cards_as_title_price_rows():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            """<ol class="row">
                 <li><article class="product_pod">
                   <h3><a title="Sharp Objects">Sharp Objects</a></h3>
                   <p class="price_color">&#163;47.82</p>
                 </article></li>
                 <li><article class="product_pod">
                   <h3><a title="In a Dark, Dark Wood">In a Dark, Dark ...</a></h3>
                   <p class="price_color">&#163;19.63</p>
                 </article></li>
               </ol>"""
        )

        books = _extract_table(page.locator("ol.row"))
        browser.close()

    assert books == [
        {"title": "Sharp Objects", "price": "\u00a347.82"},
        {"title": "In a Dark, Dark Wood", "price": "\u00a319.63"},
    ]


def test_select_option_prefers_visible_label_and_falls_back_to_value():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            """<select id="by-label">
                 <option value="bonafide">Bonafide</option>
               </select>
               <select id="by-value">
                 <option value="Bonafide">Bonafide Certificate</option>
               </select>"""
        )

        assert _select_option(page.locator("#by-label"), "Bonafide") == "label"
        assert _select_option(page.locator("#by-value"), "Bonafide") == "value"
        assert page.locator("#by-label").input_value() == "bonafide"
        assert page.locator("#by-value").input_value() == "Bonafide"
        browser.close()


def test_category_placeholder_is_resolved_in_selector_and_success_check():
    spec = {
        "name": "check_category_placeholder",
        "description": "Check dynamic placeholder resolution",
        "base_url": "http://127.0.0.1:5000",
        "params": {
            "category": {
                "type": "string",
                "description": "Text to find",
                "required": True,
            }
        },
        "steps": [
            {
                "action": "goto",
                "description": "Open attendance",
                "value": "/attendance",
            },
            {
                "action": "click",
                "description": "Click the requested text",
                "selectors": ['text="{category}"'],
            },
        ],
        "success_check": {
            "type": "text_visible",
            "value": "{category}",
        },
        "outputs": [],
    }

    result = run_spec(spec, {"category": "Mathematics"}, headless=True)

    assert result["status"] == "verified"
    assert result["steps"][1]["selector_used"] == 'text="Mathematics"'
    assert result["evidence"]["success_check"]["value"] == "Mathematics"


def test_approval_required():
    spec = load_spec(ROOT / "specs" / "request_certificate.json")
    spec.base_url = "http://127.0.0.1:5000"
    result = run_spec(
        spec,
        {"certificate_type": "Bonafide", "reason": "scholarship application"},
        confirmed=False,
    )
    assert result["status"] == "needs_approval"
    assert "irreversible" in result["summary"]
    assert result["args"]["certificate_type"] == "Bonafide"


def test_certificate_verified():
    spec = load_spec(ROOT / "specs" / "request_certificate.json")
    spec.base_url = "http://127.0.0.1:5000"
    result = run_spec(
        spec,
        {"certificate_type": "Bonafide", "reason": "scholarship application"},
        confirmed=True,
        headless=True,
    )
    assert result["status"] == "verified"
    assert result["outputs"]["reference_number"].startswith("CERT-")


def test_declined_irreversible_workflow_is_audited_without_browser(
    tmp_path, monkeypatch
):
    import audit
    import runner

    spec = load_spec(ROOT / "specs" / "certificate_request.json")
    audit_path = tmp_path / "runs" / "audit.jsonl"
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(
        runner,
        "sync_playwright",
        lambda: pytest.fail("declined workflow must not start Playwright"),
    )

    result = run_spec(spec, {}, declined=True)

    assert result["status"] == "declined"
    assert result["screenshot"] is None
    assert result["steps"] == []
    assert result["evidence"]["execution_started"] is False
    record = json.loads(audit_path.read_text(encoding="utf-8"))
    assert record["status"] == "declined"


def test_failed_success_check_captures_screenshot_and_audit(
    tmp_path, monkeypatch
):
    import audit

    monkeypatch.chdir(tmp_path)
    audit_path = tmp_path / "runs" / "audit.jsonl"
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)

    spec = load_spec(ROOT / "specs" / "check_attendance.json")
    spec.base_url = "http://127.0.0.1:5000"
    spec.success_check.value = "Text that is not present"

    result = run_spec(spec, {}, headless=True)

    assert result["status"] == "failed"
    assert result["failed_step"] == "success_check"
    assert result["screenshot"]
    assert (tmp_path / result["screenshot"]).is_file()
    record = json.loads(audit_path.read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert record["screenshot"] == result["screenshot"]
