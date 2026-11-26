from itertools import count

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)
reference_numbers = count(1001)
broken_submit_button = False


BASE_LAYOUT = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }} · CampusERP</title>
    <style>
      :root {
        color-scheme: light;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
        color: #172033;
        background: #f1f5f9;
        font-synthesis: none;
        text-rendering: optimizeLegibility;
      }

      * { box-sizing: border-box; }
      body { margin: 0; min-height: 100vh; background: #f1f5f9; }
      a { color: inherit; }
      .app-shell { min-height: 100vh; }
      .sidebar {
        position: fixed;
        inset: 0 auto 0 0;
        z-index: 2;
        display: flex;
        width: 248px;
        flex-direction: column;
        padding: 27px 17px;
        background: #111b35;
        color: #d7dfef;
      }
      .brand-row { display: flex; align-items: center; gap: 10px; padding: 0 10px; }
      .brand-mark {
        display: grid;
        width: 35px;
        height: 35px;
        place-items: center;
        border-radius: 11px;
        background: #3269e8;
        color: #fff;
        font-size: 15px;
        font-weight: 800;
      }
      .brand-name { color: #fff; font-size: 16px; font-weight: 750; letter-spacing: -.3px; }
      .demo-badge {
        margin-left: auto;
        padding: 3px 6px;
        border: 1px solid #42506c;
        border-radius: 5px;
        color: #aab8d2;
        font-size: 9px;
        font-weight: 750;
        letter-spacing: .9px;
      }
      .nav-label {
        margin: 43px 10px 12px;
        color: #8290aa;
        font-size: 10px;
        font-weight: 750;
        letter-spacing: 1.3px;
        text-transform: uppercase;
      }
      .nav-links { display: grid; gap: 5px; }
      .nav-link {
        display: flex;
        min-height: 43px;
        align-items: center;
        gap: 12px;
        padding: 0 12px;
        border-radius: 8px;
        color: #c4cee0;
        font-size: 13px;
        font-weight: 550;
        text-decoration: none;
        transition: background-color .15s ease, color .15s ease;
      }
      .nav-link:hover { background: #202d4b; color: #fff; }
      .nav-link.active { background: #263b67; color: #fff; }
      .nav-icon {
        display: grid;
        width: 19px;
        place-items: center;
        color: #a9bad8;
        font-size: 15px;
      }
      .nav-link.active .nav-icon { color: #85aaff; }
      .sidebar-footer {
        margin-top: auto;
        padding: 16px 10px 2px;
        border-top: 1px solid #2b3650;
        color: #8491a8;
        font-size: 11px;
      }
      .main-area { min-height: 100vh; margin-left: 248px; }
      .topbar {
        display: flex;
        height: 72px;
        align-items: center;
        justify-content: space-between;
        padding: 0 36px;
        border-bottom: 1px solid #e6eaf0;
        background: #fff;
      }
      .topbar-title { margin: 0; color: #172033; font-size: 17px; font-weight: 700; }
      .user-profile { display: flex; align-items: center; gap: 11px; }
      .user-name { color: #3a465b; font-size: 12px; font-weight: 600; }
      .avatar {
        display: grid;
        width: 35px;
        height: 35px;
        place-items: center;
        border: 1px solid #d7e3ff;
        border-radius: 50%;
        background: #edf3ff;
        color: #315fca;
        font-size: 13px;
        font-weight: 750;
      }
      .content-wrap { width: min(100% - 72px, 760px); margin: 38px auto 60px; }
      .content-wrap.narrow { max-width: 600px; }
      .page-intro { margin-bottom: 19px; }
      .eyebrow {
        margin: 0 0 7px;
        color: #758198;
        font-size: 10px;
        font-weight: 750;
        letter-spacing: 1.15px;
        text-transform: uppercase;
      }
      .page-heading { margin: 0; color: #172033; font-size: 23px; font-weight: 730; letter-spacing: -.55px; }
      .content-card {
        overflow: hidden;
        border: 1px solid #e8edf3;
        border-radius: 12px;
        background: #fff;
        box-shadow: 0 6px 22px rgba(24, 39, 75, .055);
      }
      .card-heading {
        padding: 21px 24px;
        border-bottom: 1px solid #edf0f4;
        color: #263247;
        font-size: 14px;
        font-weight: 700;
      }
      .form-body { display: grid; gap: 20px; padding: 24px; }
      .field-group { display: grid; gap: 8px; }
      .field-label {
        color: #657187;
        font-size: 10px;
        font-weight: 750;
        letter-spacing: 1px;
        text-transform: uppercase;
      }
      .form-control {
        width: 100%;
        min-height: 44px;
        padding: 10px 12px;
        border: 1px solid #d8dee8;
        border-radius: 7px;
        outline: none;
        background: #fff;
        color: #263247;
        font: inherit;
        font-size: 13px;
        transition: border-color .15s ease, box-shadow .15s ease;
      }
      .form-control:focus {
        border-color: #4a7bea;
        box-shadow: 0 0 0 3px rgba(65, 117, 230, .16);
      }
      textarea.form-control { min-height: 112px; resize: vertical; }
      .form-actions {
        display: flex;
        justify-content: flex-end;
        padding-top: 3px;
      }
      .primary-button {
        display: inline-flex;
        min-height: 42px;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 0 17px;
        border: 0;
        border-radius: 7px;
        background: #3269e8;
        box-shadow: 0 2px 4px rgba(41, 91, 207, .18);
        color: #fff;
        cursor: pointer;
        font: inherit;
        font-size: 12px;
        font-weight: 700;
        transition: background-color .15s ease, box-shadow .15s ease;
      }
      .primary-button:hover { background: #2459d3; box-shadow: 0 4px 9px rgba(41, 91, 207, .25); }
      .primary-button:focus-visible { outline: 3px solid #a9c2ff; outline-offset: 2px; }
      .table-wrap { overflow-x: auto; }
      .attendance-table { width: 100%; border-collapse: collapse; text-align: left; }
      .attendance-table thead { background: #f8fafc; }
      .attendance-table th {
        padding: 13px 17px;
        color: #6d788c;
        font-size: 10px;
        font-weight: 750;
        letter-spacing: .8px;
        text-transform: uppercase;
      }
      .attendance-table td {
        padding: 16px 17px;
        border-top: 1px solid #edf0f4;
        color: #384459;
        font-size: 12px;
      }
      .attendance-table td:first-child { color: #202c41; font-weight: 650; }
      .percentage { font-weight: 750; }
      .percentage-green { color: #16834a !important; }
      .percentage-amber { color: #b77912 !important; }
      .percentage-red { color: #cf3e45 !important; }
      .table-note { padding: 14px 17px; border-top: 1px solid #edf0f4; color: #7a8598; font-size: 11px; }
      .confirmation-card { padding: 34px 25px; text-align: center; }
      .check-icon {
        display: grid;
        width: 52px;
        height: 52px;
        margin: 0 auto 16px;
        place-items: center;
        border-radius: 50%;
        background: #e7f7ee;
        color: #17864c;
        font-size: 25px;
        font-weight: 700;
      }
      .confirmation-heading { margin: 0 0 10px; color: #1d2b40; font-size: 20px; font-weight: 740; }
      .reference-copy { margin: 0; color: #69758a; font-size: 13px; }
      .reference-number {
        display: inline-block;
        margin-top: 9px;
        padding: 7px 12px;
        border: 1px solid #d9e5ff;
        border-radius: 999px;
        background: #f0f5ff;
        color: #285dce;
        font-size: 13px;
        font-weight: 750;
        letter-spacing: .35px;
      }
      .dashboard-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; padding: 20px; }
      .dashboard-link {
        display: flex;
        min-height: 116px;
        flex-direction: column;
        justify-content: space-between;
        padding: 17px;
        border: 1px solid #e7ecf3;
        border-radius: 9px;
        background: #fff;
        color: #263247;
        text-decoration: none;
      }
      .dashboard-link:hover { border-color: #bdd0fb; background: #f8faff; }
      .dashboard-link strong { font-size: 13px; }
      .dashboard-link span { color: #768197; font-size: 11px; }
      @media (max-width: 760px) {
        .sidebar { position: static; width: auto; padding: 15px; }
        .nav-label, .sidebar-footer { display: none; }
        .nav-links { display: flex; overflow-x: auto; margin-top: 14px; }
        .nav-link { min-height: 38px; flex: 0 0 auto; padding: 0 10px; }
        .main-area { margin-left: 0; }
        .topbar { height: 62px; padding: 0 18px; }
        .content-wrap { width: min(100% - 32px, 760px); margin-top: 25px; }
        .user-name { max-width: 160px; }
      }
      @media (max-width: 460px) {
        .user-name { display: none; }
        .content-wrap { width: calc(100% - 22px); }
        .form-body { padding: 18px; }
        .attendance-table th, .attendance-table td { padding: 12px 10px; }
        .dashboard-grid { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <div class="app-shell">
      <aside class="sidebar">
        <div class="brand-row">
          <span class="brand-mark" aria-hidden="true">C</span>
          <span class="brand-name">CampusERP</span>
          <span class="demo-badge">DEMO</span>
        </div>
        <p class="nav-label">Student portal</p>
        <nav class="nav-links" aria-label="Main navigation">
          <a class="nav-link{% if active == 'dashboard' %} active{% endif %}"
             href="/" {% if active == 'dashboard' %}aria-current="page"{% endif %}>
            <span class="nav-icon" aria-hidden="true">⌂</span>Dashboard
          </a>
          <a class="nav-link{% if active == 'attendance' %} active{% endif %}"
             href="/attendance" {% if active == 'attendance' %}aria-current="page"{% endif %}>
            <span class="nav-icon" aria-hidden="true">▤</span>Attendance
          </a>
          <a class="nav-link{% if active == 'certificates' %} active{% endif %}"
             href="/certificate" {% if active == 'certificates' %}aria-current="page"{% endif %}>
            <span class="nav-icon" aria-hidden="true">▧</span>Certificates
          </a>
          <a class="nav-link" href="#">
            <span class="nav-icon" aria-hidden="true">▣</span>Exam Forms
          </a>
        </nav>
        <div class="sidebar-footer">Student services · demo environment</div>
      </aside>
      <div class="main-area">
        <header class="topbar">
          <div class="topbar-title">{{ title }}</div>
          <div class="user-profile">
            <span class="user-name">Demo Student · 1XX24CS000</span>
            <span class="avatar" aria-hidden="true">D</span>
          </div>
        </header>
        <main class="content-wrap {{ content_width }}">
          {{ content|safe }}
        </main>
      </div>
    </div>
  </body>
</html>"""


ATTENDANCE_PAGE = """<section class="page-intro">
  <p class="eyebrow">Academic overview</p>
  <h1 class="page-heading">Attendance</h1>
</section>
<section class="content-card" aria-label="Attendance summary">
  <div class="card-heading">Subject attendance</div>
  <div class="table-wrap">
    <table id="attendance-table" class="attendance-table">
      <thead>
        <tr>
          <th>Subject</th>
          <th>Attended</th>
          <th>Total</th>
          <th>Percentage</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Mathematics</td><td>18</td><td>20</td><td class="percentage percentage-green">90%</td></tr>
        <tr><td>Physics</td><td>14</td><td>20</td><td class="percentage percentage-red">70%</td></tr>
        <tr><td>Literature</td><td>15</td><td>20</td><td class="percentage percentage-amber">75%</td></tr>
      </tbody>
    </table>
  </div>
  <div class="table-note">Attendance is calculated from recorded classes.</div>
</section>"""


CERTIFICATE_FORM = """<section class="page-intro">
  <p class="eyebrow">Student services</p>
  <h1 class="page-heading">Certificate Request</h1>
</section>
<section class="content-card" aria-label="Certificate request form">
  <div class="card-heading">Request details</div>
  <form id="cert-form" method="post">
    <div class="form-body">
      <div class="field-group">
        <label class="field-label" for="cert-type">Certificate Type</label>
        <select class="form-control" id="cert-type" name="cert_type">
          <option value="Bonafide">Bonafide</option>
          <option value="No Dues">No Dues</option>
          <option value="Character">Character</option>
        </select>
      </div>
      <div class="field-group">
        <label class="field-label" for="reason">Reason</label>
        <textarea class="form-control" id="reason" name="reason"></textarea>
      </div>
      <div class="form-actions">
        <button class="primary-button" id="{{ button_id }}" type="submit">Submit Request</button>
      </div>
    </div>
  </form>
</section>"""


CONFIRMATION_PAGE = """<section class="content-card confirmation-card">
  <span class="check-icon" aria-hidden="true">✓</span>
  <h2 class="confirmation-heading">Request submitted</h2>
  <p class="reference-copy">Your reference number is</p>
  <span class="reference-number" id="ref-number">{{ reference_number }}</span>
</section>"""


DASHBOARD_PAGE = """<section class="page-intro">
  <p class="eyebrow">Student portal</p>
  <h1 class="page-heading">Dashboard</h1>
</section>
<section class="content-card" aria-label="Student services">
  <div class="card-heading">Quick links</div>
  <div class="dashboard-grid">
    <a class="dashboard-link" href="/attendance">
      <strong>Attendance</strong><span>Review subject attendance</span>
    </a>
    <a class="dashboard-link" href="/certificate">
      <strong>Certificates</strong><span>Submit a certificate request</span>
    </a>
  </div>
</section>"""


def _render_page(title: str, active: str, content: str, content_width: str = ""):
    return render_template_string(
        BASE_LAYOUT,
        title=title,
        active=active,
        content_width=content_width,
        content=content,
    )


@app.get("/")
def dashboard():
    return _render_page("Dashboard", "dashboard", DASHBOARD_PAGE)


@app.get("/attendance")
def attendance():
    return _render_page("Attendance", "attendance", ATTENDANCE_PAGE)


@app.get("/certificate")
def certificate_form():
    is_broken = request.args.get("variant") == "broken" or broken_submit_button
    button_id = "send-btn" if is_broken else "submit-btn"
    content = render_template_string(CERTIFICATE_FORM, button_id=button_id)
    return _render_page("Certificate Request", "certificates", content, "narrow")


@app.post("/__demo/toggle-broken")
def toggle_broken_button():
    global broken_submit_button
    broken_submit_button = not broken_submit_button
    return jsonify(
        broken=broken_submit_button,
        button_id="send-btn" if broken_submit_button else "submit-btn",
    )


@app.post("/certificate")
def submit_certificate():
    reference_number = f"CERT-{next(reference_numbers)}"
    content = render_template_string(
        CONFIRMATION_PAGE, reference_number=reference_number
    )
    return _render_page("Certificate Request", "certificates", content, "narrow")


if __name__ == "__main__":
    app.run(port=5000)
