from itertools import count

from flask import Flask, render_template_string, request

app = Flask(__name__)
reference_numbers = count(1001)


ATTENDANCE_PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Attendance</title>
  </head>
  <body>
    <main>
      <h1>Attendance</h1>
      <table id="attendance-table">
        <thead>
          <tr>
            <th>Subject</th>
            <th>Attended</th>
            <th>Total</th>
            <th>Percentage</th>
          </tr>
        </thead>
        <tbody>
          <tr><td>Mathematics</td><td>18</td><td>20</td><td>90%</td></tr>
          <tr><td>Physics</td><td>14</td><td>20</td><td>70%</td></tr>
          <tr><td>Literature</td><td>15</td><td>20</td><td>75%</td></tr>
        </tbody>
      </table>
    </main>
  </body>
</html>"""


CERTIFICATE_FORM = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Certificate Request</title>
  </head>
  <body>
    <main>
      <h1>Certificate Request</h1>
      <form id="cert-form" method="post">
        <label for="cert-type">Certificate Type</label>
        <select id="cert-type" name="cert_type">
          <option value="Bonafide">Bonafide</option>
          <option value="No Dues">No Dues</option>
          <option value="Character">Character</option>
        </select>
        <label for="reason">Reason</label>
        <textarea id="reason" name="reason"></textarea>
        <button id="{{ button_id }}" type="submit">Submit Request</button>
      </form>
    </main>
  </body>
</html>"""


CONFIRMATION_PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Request Submitted</title>
  </head>
  <body>
    <main>
      <h2>Request submitted</h2>
      <p>Your reference number is <span id="ref-number">{{ reference_number }}</span>.</p>
    </main>
  </body>
</html>"""


@app.get("/attendance")
def attendance():
    return render_template_string(ATTENDANCE_PAGE)


@app.get("/certificate")
def certificate_form():
    button_id = "send-btn" if request.args.get("variant") == "broken" else "submit-btn"
    return render_template_string(CERTIFICATE_FORM, button_id=button_id)


@app.post("/certificate")
def submit_certificate():
    reference_number = f"CERT-{next(reference_numbers)}"
    return render_template_string(
        CONFIRMATION_PAGE, reference_number=reference_number
    )


if __name__ == "__main__":
    app.run(port=5000)
