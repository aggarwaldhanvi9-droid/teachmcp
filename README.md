# TeachMCP: Teach once. Automate anywhere.

## Folder layout
```
teachmcp/
  models.py        # SHARED contract (ToolSpec). Don't edit alone.
  specs/           # approved tool specs (JSON)
  # Person A
  demo_portal/app.py   recorder.py   generator.py   review.py
  # Person B
  runner.py   verify.py   server.py   audit.py
```

## Setup
```
pip install playwright mcp pydantic flask anthropic
playwright install chromium
python models.py        # validates every spec in specs/
```

## Review pending specs
From the repository root (`MCP_Whackiest`), run:
```
.\teachmcp\.venv\Scripts\python.exe .\teachmcp\review.py
```
Or change into `teachmcp` first and run:
```
.\.venv\Scripts\python.exe review.py
```

## Portal contract (Person A must build exactly this)
Person B's runner and the example specs depend on these IDs. Rename nothing without telling B.

| Route | Page contents |
|---|---|
| `GET /attendance` | `<table id="attendance-table">` with header row (Subject, Attended, Total, Percentage) and one row per subject. Make one or two subjects below 75%. |
| `GET /certificate` | `<form id="cert-form" method="post">` containing `<select id="cert-type" name="cert_type">` (options: Bonafide, No Dues, Character), `<textarea id="reason" name="reason">`, and `<button id="submit-btn" type="submit">Submit Request</button>` |
| `POST /certificate` | Shows a page with `<h2>Request submitted</h2>` and `<span id="ref-number">CERT-1001</span>` (increment the number each time) |

Self-healing demo: change the button to `<button id="send-btn" type="submit">Submit Request</button>`. The first selector fails, and `button[type=submit]` or `text=Submit Request` should recover it.

Portal button toggle (while the demo app is running):
```
Invoke-RestMethod -Method Post -Uri http://localhost:5000/__demo/toggle-broken
```
`GET /certificate?variant=broken` still forces `send-btn`, regardless of the toggle.

For the approved `certificate_request` workflow, pass `cert_type` and `reason`. The first call returns `needs_approval`; after user consent, call again with `confirmed=true`. To exercise the scenarios:
- **Selection and approval:** choose `Bonafide` and confirm; the runner selects by visible label first.
- **Self-healing:** toggle the portal to broken mode, confirm the request, then check `runs\audit.jsonl` for a non-empty `healed_steps`.
- **Failed verification:** run `pytest tests\test_runner.py::test_failed_success_check_captures_screenshot_and_audit`; it checks the failed status, screenshot, and audit entry.
- **Decline:** after `needs_approval`, call with `declined=true`; the result is `declined` and no browser actions run.

## Ownership
- **Person A:** demo_portal, recorder, generator, review step (uses `ToolSpec.plain_english()`)
- **Person B:** runner, verification, MCP server (uses `ToolSpec.mcp_input_schema()`), approval, audit log

## Rules
- Specs with `irreversible: true` must pause for approval before the final click.
- Never report success without passing `success_check`.
- Never store passwords in specs.
