import pytest

from demo_portal.app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("demo_portal.app.broken_submit_button", False)
    return app.test_client()


def test_submit_button_toggle_and_query_override(client):
    normal = client.get("/certificate")
    assert 'id="submit-btn"' in normal.get_data(as_text=True)

    toggled = client.post("/__demo/toggle-broken")
    assert toggled.json == {"broken": True, "button_id": "send-btn"}
    assert 'id="send-btn"' in client.get("/certificate").get_data(as_text=True)

    toggled = client.post("/__demo/toggle-broken")
    assert toggled.json == {"broken": False, "button_id": "submit-btn"}
    assert 'id="submit-btn"' in client.get("/certificate").get_data(as_text=True)
    assert 'id="send-btn"' in client.get(
        "/certificate?variant=broken"
    ).get_data(as_text=True)
