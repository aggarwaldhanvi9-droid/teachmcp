from pathlib import Path

from playwright.sync_api import sync_playwright

from models import SuccessCheck
from verify import verify


class FakeLocator:
    def __init__(self, count=0, visible=False):
        self._count = count
        self._visible = visible

    def count(self):
        return self._count

    def is_visible(self):
        return self._visible


class FakePage:
    def __init__(self, text="", url="http://example.test/", selectors=None):
        self.url = url
        self._text = text
        self._selectors = selectors or {}

    def get_by_text(self, value, exact=False):
        return FakeLocator(1 if value in self._text else 0)

    def locator(self, selector):
        if selector == "body":
            locator = FakeLocator(1)
            locator.inner_text = lambda: self._text
            return locator
        return FakeLocator(**self._selectors.get(selector, {}))


def test_text_visible_pass_and_fail():
    page = FakePage(text="Request submitted successfully")
    passed, evidence = verify(SuccessCheck(type="text_visible", value="Request submitted"), page)
    assert passed is True
    assert "Request submitted" in evidence

    passed, evidence = verify(SuccessCheck(type="text_visible", value="Missing"), page)
    assert passed is False
    assert "Missing" in evidence


def test_selector_visible_pass_and_fail():
    page = FakePage(selectors={"#result": {"count": 1, "visible": True}})
    passed, evidence = verify(SuccessCheck(type="selector_visible", value="#result"), page)
    assert passed is True
    assert "#result" in evidence

    passed, evidence = verify(SuccessCheck(type="selector_visible", value="#missing"), page)
    assert passed is False
    assert "#missing" in evidence


def test_url_contains_pass_and_fail():
    page = FakePage(url="http://example.test/confirmation")
    passed, evidence = verify(SuccessCheck(type="url_contains", value="/confirmation"), page)
    assert passed is True
    assert "/confirmation" in evidence

    passed, evidence = verify(SuccessCheck(type="url_contains", value="/other"), page)
    assert passed is False
    assert "/other" in evidence


def test_output_nonempty_pass_and_fail():
    check = SuccessCheck(type="output_nonempty", value="reference_number")
    passed, evidence = verify(check, outputs={"reference_number": "CERT-1001"})
    assert passed is True
    assert "reference_number" in evidence

    passed, evidence = verify(check, outputs={"reference_number": ""})
    assert passed is False
    assert "reference_number" in evidence


def test_runner_uses_verifier_for_real_page():
    from models import ToolSpec
    from runner import run_spec

    spec = ToolSpec.model_validate({
        "name": "test_success",
        "description": "Test success verification",
        "base_url": "http://127.0.0.1:5000",
        "steps": [{"action": "goto", "description": "Open attendance", "value": "/attendance"}],
        "success_check": {"type": "text_visible", "value": "Attendance"},
        "approved": True,
    })

    result = run_spec(spec, {}, headless=True)
    assert result["status"] in ("verified", "failed")
