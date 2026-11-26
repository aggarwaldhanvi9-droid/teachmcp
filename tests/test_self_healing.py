import json
import threading

import pytest
from flask import Flask, request

from models import load_spec
from runner import run_spec


@pytest.fixture
def modified_portal(monkeypatch):
    app = Flask("modified_self_healing_portal")

    @app.get("/certificate")
    def certificate():
        return """<!doctype html>
        <html>
          <head><title>Modified Certificate Request</title></head>
          <body>
            <h1>Certificate Request</h1>
            <form id="cert-form" method="post" action="/certificate">
              <select id="cert-type" name="cert_type" aria-label="Certificate Type">
                <option>Bonafide</option><option>No Dues</option><option>Character</option>
              </select>
              <textarea id="reason" name="reason" aria-label="Reason"></textarea>
              <button id="send-btn" type="submit">Submit Request</button>
            </form>
          </body>
        </html>"""

    @app.post("/certificate")
    def submit_certificate():
        return "<h2>Request submitted</h2><span id=\"ref-number\">CERT-1001</span>"

    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=5055, use_reloader=False),
        daemon=True,
    )
    thread.start()

    import urllib.request
    import time

    for _ in range(40):
        try:
            urllib.request.urlopen("http://127.0.0.1:5055/certificate", timeout=0.25)
            break
        except Exception:
            time.sleep(0.1)
    else:
        pytest.fail("Modified fake portal did not start")

    yield "http://127.0.0.1:5055"


def test_certificate_click_self_heals(modified_portal, tmp_path, monkeypatch):
    audit_path = tmp_path / "runs" / "audit.jsonl"
    monkeypatch.setattr("audit.AUDIT_PATH", audit_path)

    spec = load_spec("specs/certificate_request.json")
    spec.base_url = modified_portal

    result = run_spec(
        spec,
        {"cert_type": "Bonafide", "reason": "scholarship application"},
        confirmed=True,
        headless=True,
    )

    assert result["status"] == "verified"
    click_step = next(step for step in result["steps"] if step["action"] == "click")
    assert click_step["selector_used"] in (
        'button[type="submit"]',
        "text=Submit Request",
    )
    assert click_step["healed"] is True

    assert audit_path.exists()
    records = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    latest = records[-1]
    assert latest["tool"] == "certificate_request"
    assert any("Click Submit Request" in step or "button" in step.lower() for step in latest["healed_steps"])


def test_broken_button_selectors_fail(modified_portal):
    spec = load_spec("specs/request_certificate.json")
    spec.base_url = modified_portal

    for step in spec.steps:
        if step.action == "click":
            step.selectors = ["#missing-submit", "#also-missing", "text=No Such Button"]
            break

    result = run_spec(
        spec,
        {"certificate_type": "Bonafide", "reason": "scholarship application"},
        confirmed=True,
        headless=True,
    )

    assert result["status"] == "failed"
    assert result["failed_step"] == 4
