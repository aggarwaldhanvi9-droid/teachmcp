import json

from generator import SYSTEM_PROMPT, generate_tool_spec


def test_books_category_recording_generates_reusable_spec():
    recording = {
        "url": "https://books.toscrape.com",
        "steps": [
            {
                "action": "goto",
                "description": "Open the starting page",
                "value": "https://books.toscrape.com",
            },
            {
                "action": "click",
                "description": "Click Mystery",
                "selectors": [
                    'role=link[name="Mystery"]',
                    'text="Mystery"',
                    "a",
                ],
            },
            {
                "action": "extract",
                "description": "Extract section text",
                "selectors": ["section"],
                "extract_as": "text",
                "save_as": "extracted_text_1",
            },
            {
                "action": "extract",
                "description": "Extract product list",
                "selectors": ["div.col-sm-8.col-md-9", "div"],
                "extract_as": "text",
                "save_as": "extracted_text_2",
            },
        ],
    }
    generated = {
        "name": "browse_books",
        "description": "Browse books in a requested category.",
        "base_url": "https://books.toscrape.com",
        "params": {
            "category": {
                "type": "string",
                "description": "Book category to browse",
                "required": True,
            }
        },
        "steps": [
            {
                "action": "goto",
                "description": "Open Books to Scrape",
                "value": "/",
            },
            {
                "action": "click",
                "description": "Open the requested category",
                "selectors": [
                    'role=link[name="{category}"]',
                    'text="{category}"',
                    "a",
                ],
            },
            {
                "action": "extract",
                "description": "Extract book titles and prices",
                "selectors": ["div.col-sm-8.col-md-9", "ol.row"],
                "extract_as": "table",
                "save_as": "books",
            },
        ],
        "success_check": {
            "type": "text_visible",
            "value": "{category}",
        },
        "outputs": ["books"],
        "irreversible": False,
        "approved": False,
    }
    calls = []

    def fake_generate_response(prompt):
        calls.append(prompt)
        return json.dumps(generated)

    spec = generate_tool_spec(
        recording,
        {"name": "example"},
        fake_generate_response,
    )

    assert len(calls) == 1
    assert "treat its recorded label as an example value" in SYSTEM_PROMPT
    assert "repeated product or item cards" in SYSTEM_PROMPT
    assert spec.name == "browse_books"
    assert spec.params["category"].required

    click_step = next(step for step in spec.steps if step.action == "click")
    assert click_step.selectors == [
        'role=link[name="{category}"]',
        'text="{category}"',
        "a",
    ]
    assert "Mystery" not in click_step.selectors
    assert "Mystery" not in spec.name
    assert spec.success_check.value == "{category}"

    extract_steps = [step for step in spec.steps if step.action == "extract"]
    assert len(extract_steps) == 1
    assert extract_steps[0].extract_as == "table"
    assert extract_steps[0].save_as == "books"
    assert spec.outputs == ["books"]
    assert spec.approved is False
