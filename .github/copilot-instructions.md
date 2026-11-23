# TeachMCP: instructions for Copilot

## Project
TeachMCP lets a normal person demonstrate a browser task once. A recorder captures it, an LLM turns it into a reusable, parameterized ToolSpec JSON, the human reviews and approves it, and an MCP server exposes approved specs as tools that AI agents can call. AI is used only when GENERATING a tool. Running a tool is deterministic, verified, and asks for approval before irreversible actions. Pitch: "less magic, more utility".

## First Action Every Session
Before editing or creating any code, read models.py, README.md, and specs/*.json.

## Rules for everyone
- Python only. Playwright (sync API), pydantic, flask, anthropic, official mcp SDK (FastMCP, stdio).
- models.py is the shared ToolSpec contract. NEVER edit it. If a change seems needed, stop and tell me so I can discuss it with my teammate.
- README.md has the portal contract (routes and element IDs). Follow it exactly.
- Selectors are Playwright strings, ordered most stable first, with fallbacks.
- Never store passwords or tokens in specs, logs or recordings.
- Never report success unless success_check passed. Report failures honestly.
- Generated specs are saved with pproved=false. Only the review step sets 	rue.
- Keep code simple and readable. No databases, no frontend frameworks.
- Work one task at a time. After each task, tell me exactly how to run and test it.
- Do not install packages or run commands that delete files without asking me.

## Two people, two roles
At the start of a chat I will tell you whether I am Person A or Person B.
Only edit files owned by my role.

### Person A: teach side
- Owns: demo_portal/, ecorder.py, generator.py, eview.py, specs_pending/, ecordings/
- Must NOT touch: unner.py, erify.py, server.py, udit.py, 	ests/, uns/
- Task order: (1) Flask demo portal, max ~1 hour, plain HTML; (2) recorder; (3) generator (Anthropic API, ANTHROPIC_MODEL env var, validate with ToolSpec.model_validate, retry once); (4) review CLI using spec.plain_english(); (5) end-to-end teach test; (6) test 3-4 real login-free sites later.
- Portal extras: ?variant=broken renders the submit button as id="send-btn" (still 	ype=submit, text "Submit Request") for the self-healing demo.
- Recorder: store several selector candidates per element, Ctrl+Shift+E then click marks an extract step, never record password field values.

### Person B: run side
- Owns: unner.py, erify.py, server.py, udit.py, 	ests/, uns/
- Must NOT touch: demo_portal/, ecorder.py, generator.py, eview.py, specs_pending/, ecordings/
- Task order: (1) unner.py: un_spec(spec, args, confirmed, dry_run); try selectors in order, mark healed steps, 
eeds_approval for irreversible specs; (2) erify.py: four success_check types, returns (passed, evidence); (3) server.py: FastMCP, only approved specs, list_workflows, un_workflow, one named tool per spec using spec.mcp_input_schema(); (4) udit.py: JSONL log with redaction; (5) self-healing test; (6) optional LLM repair suggestion.
- Until the real portal exists, test against static HTML in 	ests/fake_portal/.
- For irreversible tools: first call returns 
eeds_approval, the agent asks the user, then calls again with confirmed=true.
