import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from models import load_spec
from runner import _extract_table, run_spec


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
