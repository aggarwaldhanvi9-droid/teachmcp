from pathlib import Path

from flask import Flask, request


PORTAL = Path(__file__).parent / "fake_portal"
app = Flask(__name__)
next_reference = 1001


@app.get("/attendance")
def attendance():
    return (PORTAL / "attendance.html").read_text(encoding="utf-8")


@app.get("/certificate")
def certificate():
    return (PORTAL / "certificate.html").read_text(encoding="utf-8")


@app.post("/certificate")
def submit_certificate():
    global next_reference
    reference = next_reference
    next_reference += 1
    html = (PORTAL / "confirmation.html").read_text(encoding="utf-8")
    html = html.replace("CERT-1001", f"CERT-{reference}", 1)
    return html


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
