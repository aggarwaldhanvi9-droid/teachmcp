import json
import threading
import time
import urllib.request
from pathlib import Path

import pytest
from flask import Flask

from models import load_spec
from runner import run_spec


class MockTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class MockResponse:
    def __init__(self, text):
        self.content = [MockTextBlock(text)]


class MockAnthropic:
    def __init__(self, api_key=None):
        self.messages = self

    def create(self, **kwargs):
        return MockResponse(
            json.dumps({
                "step": "Click Submit Request",
                "failed_selectors": ["#submit-btn", "button[type=submit]", "text=Submit Request"],
                "suggested_selector": "#send-btn",
                "reason": "The submit button has been renamed and now uses id=send-btn.",
            })
        )


@pytest.fixture
def modified_repair_portal():
    app = Flask("repair_suggestion_portal")

    @app.get("/certificate")
    def certificate():
        return """<!doctype html><html><body>
        <form id="cert-form" method="post" action="/certificate">
          <select id="cert-type" name="cert_type"><option>Bonafide</option></select>
          <textarea id="reason" name="reason"></textarea>
          <button id="send-btn" type="submit">Submit Request</button>
        </form></body></html>"""

    @app.post("/certificate")
    def submit():
        return "<h2>Request submitted</h2><span id=\"ref-number\">CERT-1001</span>"

    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=5055, use_reloader=False),
        daemon=True,
    )
    thread.start()

    for _ in range(40):
        try:
            urllib.request.urlopen("http://127.0.0.1:5055/certificate", timeout=0.25)
            break
        except Exception:
            time.sleep(0.1)
    else:
        pytest.fail("Repair suggestion fixture did not start")

    yield "http://127.0.0.1:5055"


def test_llm_repair_suggestion_does_not_mutate_spec(monkeypatch, modified_repair_portal):
    import anthropic
    import runner

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(anthropic, "Anthropic", MockAnthropic)

    spec_path = Path("specs/request_certificate.json")
    original = spec_path.read_text(encoding="utf-8")
    spec = load_spec(spec_path)
    spec.base_url = modified_repair_portal

    for step in spec.steps:
        if step.action == "click":
            step.selectors = ["#missing-submit", "#also-missing", "text=No Such Button"]
            break

    result = run_spec(
        spec,
        {"certificate_type": "Bonafide", "reason": "test"},
        confirmed=True,
        headless=True,
    )

    assert result["status"] == "failed"
    assert result["repair_suggestion"]["suggested_selector"] == "#send-btn"
    assert result["repair_suggestion"]["step"] == "Click Submit Request"
    assert result["repair_suggestion"]["failed_selectors"]
    assert spec_path.read_text(encoding="utf-8") == original
