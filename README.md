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

## Ownership
- **Person A:** demo_portal, recorder, generator, review step (uses `ToolSpec.plain_english()`)
- **Person B:** runner, verification, MCP server (uses `ToolSpec.mcp_input_schema()`), approval, audit log

## Rules
- Specs with `irreversible: true` must pause for approval before the final click.
- Never report success without passing `success_check`.
- Never store passwords in specs.
