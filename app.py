"""
app.py — AI Employee Vault Web UI
Flask interface for Dashboard, HITL Approvals, and manual Orchestrator trigger.

Usage:
    python app.py                  # Run on localhost:5000
    python app.py --test           # Run Ralph Wiggum test suite then exit

Environment (.env or shell):
    UI_PASSWORD=<secret>           # Login password (default: admin)
    SECRET_KEY=<flask-secret>      # Flask session key (default: dev-secret)
    VAULT_DIR=<path>               # Override vault path
"""

import os
import sys
import json
import shutil
import logging
import argparse
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from functools import wraps

# ---------------------------------------------------------------------------
# Encoding fix for Windows consoles
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import markdown as md_lib
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
VAULT_DIR       = Path(os.environ.get("VAULT_DIR", "d:/hackathon0/hackathon/AI_Employee_Vault"))
PENDING_DIR     = VAULT_DIR / "Pending_Approval"
APPROVED_DIR    = VAULT_DIR / "Approved"
REJECTED_DIR    = VAULT_DIR / "Rejected"
DASHBOARD_MD    = VAULT_DIR / "Dashboard.md"
ORCHESTRATOR_PY = VAULT_DIR / "orchestrator.py"
LOGS_DIR        = VAULT_DIR / "Logs"
LOG_FILE        = VAULT_DIR / "ui.log"

for d in (PENDING_DIR, APPROVED_DIR, REJECTED_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ui] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("ui")

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")

UI_PASSWORD = os.environ.get("UI_PASSWORD", "admin")

# ---------------------------------------------------------------------------
# In-memory audit log for the UI (last 50 events)
# ---------------------------------------------------------------------------
_ui_events: list[dict] = []
_ui_events_lock = threading.Lock()

def record_event(action: str, detail: str = "", success: bool = True):
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "detail": detail,
        "success": success,
    }
    with _ui_events_lock:
        _ui_events.append(entry)
        if len(_ui_events) > 50:
            _ui_events.pop(0)
    level = logging.INFO if success else logging.WARNING
    logger.log(level, "%s: %s", action, detail)


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_yaml_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from markdown text (--- block)."""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    import re
    meta = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^(\w[\w_-]*):\s*(.*)$", line.strip())
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta


def load_pending_files() -> list[dict]:
    """Return list of dicts describing each file in /Pending_Approval."""
    files = []
    for p in sorted(PENDING_DIR.glob("*.md")):
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("Could not read %s: %s", p.name, e)
            raw = ""
        meta = parse_yaml_frontmatter(raw)
        # Strip frontmatter to get body
        body = raw
        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end != -1:
                body = raw[end + 3:].strip()
        files.append({
            "filename": p.name,
            "stem":     p.stem,
            "meta":     meta,
            "body":     body[:300] + ("…" if len(body) > 300 else ""),
            "category": meta.get("type") or meta.get("category") or "item",
            "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return files


def move_file(filename: str, dest_dir: Path) -> tuple[bool, str]:
    """Move a file from Pending_Approval to dest_dir."""
    src = PENDING_DIR / filename
    if not src.exists():
        return False, f"File not found: {filename}"
    if ".." in filename or "/" in filename or "\\" in filename:
        return False, "Invalid filename"
    dst = dest_dir / filename
    try:
        shutil.move(str(src), str(dst))
        return True, f"Moved {filename} to {dest_dir.name}"
    except Exception as e:
        return False, str(e)


def render_dashboard_md() -> str:
    """Read Dashboard.md and convert to HTML."""
    try:
        raw = DASHBOARD_MD.read_text(encoding="utf-8", errors="replace")
        html = md_lib.markdown(raw, extensions=["tables", "fenced_code", "nl2br"])
        return html
    except FileNotFoundError:
        return "<p><em>Dashboard.md not found.</em></p>"
    except Exception as e:
        logger.error("Dashboard render error: %s", e)
        return f"<p class='error'>Error rendering dashboard: {e}</p>"


def run_orchestrator_once() -> tuple[bool, str]:
    """Spawn orchestrator --simulate --once in background, return immediately."""
    try:
        proc = subprocess.Popen(
            [sys.executable, str(ORCHESTRATOR_PY), "--simulate", "--once"],
            cwd=str(VAULT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # Wait up to 30 s
        try:
            out, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            out = "(timed out after 30s)"
        rc = proc.returncode
        lines = [l for l in out.splitlines() if l.strip()][-10:]  # last 10 lines
        summary = "\n".join(lines)
        return (rc == 0), summary
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next", url_for("dashboard"))
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == UI_PASSWORD:
            session["logged_in"] = True
            record_event("login", "Successful login")
            return redirect(next_url)
        else:
            record_event("login_fail", "Bad password", success=False)
            flash("Incorrect password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    record_event("logout", "User logged out")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    dashboard_html = render_dashboard_md()
    pending = load_pending_files()
    with _ui_events_lock:
        events = list(reversed(_ui_events[-10:]))
    return render_template(
        "dashboard.html",
        dashboard_html=dashboard_html,
        pending=pending,
        events=events,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/approve/<filename>", methods=["POST"])
@login_required
def approve(filename):
    ok, msg = move_file(filename, APPROVED_DIR)
    record_event("approve", msg, success=ok)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": ok, "msg": msg})
    flash(msg, "success" if ok else "error")
    return redirect(url_for("dashboard"))


@app.route("/reject/<filename>", methods=["POST"])
@login_required
def reject(filename):
    ok, msg = move_file(filename, REJECTED_DIR)
    record_event("reject", msg, success=ok)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": ok, "msg": msg})
    flash(msg, "success" if ok else "error")
    return redirect(url_for("dashboard"))


@app.route("/audit", methods=["POST"])
@login_required
def trigger_audit():
    record_event("audit_trigger", "Manual orchestrator run requested")
    ok, output = run_orchestrator_once()
    record_event("audit_result", output[:200], success=ok)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": ok, "output": output})
    flash(("Audit completed:\n" if ok else "Audit failed:\n") + output, "success" if ok else "error")
    return redirect(url_for("dashboard"))


@app.route("/api/events")
@login_required
def api_events():
    with _ui_events_lock:
        return jsonify(list(reversed(_ui_events)))


@app.route("/api/pending")
@login_required
def api_pending():
    return jsonify(load_pending_files())


@app.route("/health")
def health():
    return jsonify({"status": "ok", "vault": str(VAULT_DIR), "ts": datetime.now().isoformat()})


# ---------------------------------------------------------------------------
# Error pages
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, msg="Page not found."), 404


@app.errorhandler(500)
def server_error(e):
    logger.error("500 error: %s", e)
    return render_template("error.html", code=500, msg="Internal server error."), 500


# ---------------------------------------------------------------------------
# Ralph Wiggum test suite
# ---------------------------------------------------------------------------

def run_tests() -> bool:
    """
    Ralph Wiggum test loop — simulate full UI approval flow.
    Returns True if all tests pass.
    """
    import tempfile, traceback

    PASS = "[PASS]"
    FAIL = "[FAIL]"
    results = []

    def check(name, cond, detail=""):
        ok = bool(cond)
        tag = PASS if ok else FAIL
        msg = f"  {tag} {name}" + (f": {detail}" if detail else "")
        results.append((ok, msg))
        print(msg)
        return ok

    print("\n=== AI Employee UI — Ralph Wiggum Test Loop ===\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Set up temp vault dirs
        t_pending  = tmp_path / "Pending_Approval"; t_pending.mkdir()
        t_approved = tmp_path / "Approved";         t_approved.mkdir()
        t_rejected = tmp_path / "Rejected";         t_rejected.mkdir()
        t_dash     = tmp_path / "Dashboard.md"
        t_logs     = tmp_path / "Logs";             t_logs.mkdir()

        # ---- TEST 1: Dashboard.md rendering ----
        print("[1] Dashboard markdown rendering")
        t_dash.write_text("# Test Dashboard\n\n| Col | Val |\n|---|---|\n| Balance | $1000 |\n", encoding="utf-8")
        html = md_lib.markdown(
            t_dash.read_text(encoding="utf-8"),
            extensions=["tables", "fenced_code", "nl2br"]
        )
        check("H1 tag rendered",   "<h1>" in html)
        check("Table rendered",    "<table>" in html)
        check("Balance in output", "Balance" in html)

        # ---- TEST 2: YAML frontmatter parser ----
        print("\n[2] YAML frontmatter parser")
        sample = "---\ntype: payment\namount: 750\nstatus: pending\n---\n\nBody text here."
        meta = parse_yaml_frontmatter(sample)
        check("type extracted",   meta.get("type") == "payment")
        check("amount extracted", meta.get("amount") == "750")
        check("status extracted", meta.get("status") == "pending")
        check("no-frontmatter",   parse_yaml_frontmatter("No YAML here.") == {})

        # ---- TEST 3: load_pending_files ----
        print("\n[3] load_pending_files")
        # Create 3 test files
        (t_pending / "task_invoice.md").write_text(
            "---\ntype: payment\namount: 750\nstatus: pending\n---\n\nPay invoice #001.", encoding="utf-8"
        )
        (t_pending / "task_linkedin.md").write_text(
            "---\ntype: linkedin_post\nplatform: LinkedIn\nstatus: pending\n---\n\nPost about AI.", encoding="utf-8"
        )
        (t_pending / "task_social.md").write_text(
            "---\ntype: social_post\nplatform: Twitter\nstatus: pending\n---\n\nTweet this.", encoding="utf-8"
        )

        # Monkey-patch PENDING_DIR for test
        orig_pending = app.config.get("_test_pending", None)
        import unittest.mock as mock

        files = []
        with mock.patch("__main__.PENDING_DIR", t_pending):
            files = load_pending_files()

        check("3 files loaded",        len(files) == 3)
        check("filenames present",     all("filename" in f for f in files))
        check("meta parsed",           files[0]["meta"].get("type") in ("payment", "linkedin_post", "social_post"))
        check("body truncated ok",     all("body" in f for f in files))
        check("modified timestamp",    all("modified" in f for f in files))

        # ---- TEST 4: move_file approve ----
        print("\n[4] move_file — approve")
        with mock.patch("__main__.PENDING_DIR", t_pending), \
             mock.patch("__main__.APPROVED_DIR", t_approved):
            ok, msg = move_file("task_invoice.md", t_approved)
        check("move succeeded",        ok, msg)
        check("file in approved dir",  (t_approved / "task_invoice.md").exists())
        check("file gone from pending",(t_pending  / "task_invoice.md").exists() == False)

        # ---- TEST 5: move_file reject ----
        print("\n[5] move_file — reject")
        with mock.patch("__main__.PENDING_DIR", t_pending), \
             mock.patch("__main__.REJECTED_DIR", t_rejected):
            ok, msg = move_file("task_linkedin.md", t_rejected)
        check("reject succeeded",      ok, msg)
        check("file in rejected dir",  (t_rejected / "task_linkedin.md").exists())

        # ---- TEST 6: move_file — file not found ----
        print("\n[6] move_file — error handling")
        with mock.patch("__main__.PENDING_DIR", t_pending):
            ok, msg = move_file("nonexistent.md", t_approved)
        check("returns False",         not ok)
        check("error message",         "not found" in msg.lower() or "nonexistent" in msg.lower())

        # ---- TEST 7: path traversal protection ----
        print("\n[7] Security — path traversal blocked")
        with mock.patch("__main__.PENDING_DIR", t_pending):
            ok, msg = move_file("../../../etc/passwd", t_approved)
        check("traversal blocked",     not ok)

        # ---- TEST 8: record_event ----
        print("\n[8] record_event audit trail")
        before = len(_ui_events)
        record_event("test_approve", "task_invoice.md approved", success=True)
        record_event("test_reject",  "task_linkedin.md rejected", success=True)
        check("events appended",     len(_ui_events) >= before + 2)
        check("action field set",    any(e["action"] == "test_approve" for e in _ui_events))
        check("success field set",   all("success" in e for e in _ui_events))
        check("ts field present",    all("ts" in e for e in _ui_events))

        # ---- TEST 9: Flask routes with test client ----
        print("\n[9] Flask route tests (test client)")
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        client = app.test_client()

        # Health endpoint — no auth needed
        r = client.get("/health")
        check("GET /health 200",      r.status_code == 200)
        data = json.loads(r.data)
        check("health status ok",     data.get("status") == "ok")

        # Unauthenticated redirect
        r = client.get("/")
        check("GET / → redirect to login", r.status_code in (301, 302))

        # Login with wrong password
        r = client.post("/login", data={"password": "wrong"})
        check("bad password → 200 (re-show form)", r.status_code == 200)

        # Login with correct password
        r = client.post("/login", data={"password": UI_PASSWORD}, follow_redirects=True)
        check("good password → 200",  r.status_code == 200)

        # Dashboard renders after login
        with client.session_transaction() as sess:
            sess["logged_in"] = True
        r = client.get("/")
        check("GET / after login 200", r.status_code == 200)
        check("dashboard in body",    b"Dashboard" in r.data or b"dashboard" in r.data.lower())

        # API endpoints
        r = client.get("/api/events")
        check("GET /api/events 200", r.status_code == 200)
        events_data = json.loads(r.data)
        check("events is list",      isinstance(events_data, list))

        r = client.get("/api/pending")
        check("GET /api/pending 200", r.status_code == 200)
        pending_data = json.loads(r.data)
        check("pending is list",     isinstance(pending_data, list))

        # Approve via POST (AJAX style)
        # Put a file in real pending dir first
        test_file = PENDING_DIR / "_test_approval.md"
        test_file.write_text("---\ntype: test\n---\n\nTest file.", encoding="utf-8")
        r = client.post(
            f"/approve/_test_approval.md",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        check("POST /approve 200",  r.status_code == 200)
        resp = json.loads(r.data)
        check("approve ok=true",    resp.get("ok") == True)
        check("file moved",         (APPROVED_DIR / "_test_approval.md").exists())
        # Cleanup
        (APPROVED_DIR / "_test_approval.md").unlink(missing_ok=True)

        # Reject via POST (AJAX)
        test_file2 = PENDING_DIR / "_test_reject.md"
        test_file2.write_text("---\ntype: test\n---\n\nTest reject.", encoding="utf-8")
        r = client.post(
            f"/reject/_test_reject.md",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        check("POST /reject 200",   r.status_code == 200)
        resp2 = json.loads(r.data)
        check("reject ok=true",     resp2.get("ok") == True)
        check("file in rejected",   (REJECTED_DIR / "_test_reject.md").exists())
        (REJECTED_DIR / "_test_reject.md").unlink(missing_ok=True)

        # 404 handler
        r = client.get("/nonexistent-page-xyz")
        check("404 handler works",  r.status_code == 404)

        # Logout
        r = client.get("/logout", follow_redirects=False)
        check("logout redirects",   r.status_code in (301, 302))

        # ---- TEST 10: Full approval flow simulation ----
        print("\n[10] Full approval flow simulation (Ralph Wiggum loop)")
        # Create 3 pending files, approve 2, reject 1, verify counts
        for i in range(3):
            (PENDING_DIR / f"_sim_{i}.md").write_text(
                f"---\ntype: sim\nid: {i}\n---\n\nSimulated task {i}.", encoding="utf-8"
            )
        with client.session_transaction() as sess:
            sess["logged_in"] = True

        start_pending = len(list(PENDING_DIR.glob("_sim_*.md")))
        check("3 sim files created", start_pending == 3)

        # Approve 0 and 1
        for i in [0, 1]:
            r = client.post(f"/approve/_sim_{i}.md",
                            headers={"X-Requested-With": "XMLHttpRequest"})
            resp = json.loads(r.data)
            check(f"approve sim_{i}", resp.get("ok"))

        # Reject 2
        r = client.post("/reject/_sim_2.md",
                        headers={"X-Requested-With": "XMLHttpRequest"})
        resp = json.loads(r.data)
        check("reject sim_2", resp.get("ok"))

        # Verify all moved
        remaining = list(PENDING_DIR.glob("_sim_*.md"))
        approved  = list(APPROVED_DIR.glob("_sim_*.md"))
        rejected  = list(REJECTED_DIR.glob("_sim_*.md"))

        check("0 sim files remain pending",  len(remaining) == 0)
        check("2 sim files approved",        len(approved)  == 2)
        check("1 sim file rejected",         len(rejected)  == 1)

        # Cleanup
        for f in APPROVED_DIR.glob("_sim_*.md"): f.unlink(missing_ok=True)
        for f in REJECTED_DIR.glob("_sim_*.md"): f.unlink(missing_ok=True)

    # ---- Summary ----
    total  = len(results)
    passed = sum(1 for ok, _ in results if ok)
    failed = total - passed
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed", ("ALL PASS" if failed == 0 else f"{failed} FAILED"))
    print(f"{'='*50}\n")
    return failed == 0


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Employee Vault UI")
    parser.add_argument("--test",   action="store_true", help="Run Ralph Wiggum tests then exit")
    parser.add_argument("--port",   type=int, default=5000, help="Port (default 5000)")
    parser.add_argument("--host",   default="127.0.0.1", help="Host (default 127.0.0.1)")
    parser.add_argument("--debug",  action="store_true", help="Flask debug mode")
    args = parser.parse_args()

    if args.test:
        MAX_ITER = 3
        for attempt in range(1, MAX_ITER + 1):
            print(f"\n--- Attempt {attempt}/{MAX_ITER} ---")
            if run_tests():
                print("Ralph says: I passed! I passed!\n")
                sys.exit(0)
            print(f"Attempt {attempt} had failures, retrying...\n")
        print("Ralph loop exhausted — tests still failing.")
        sys.exit(1)

    logger.info("Starting AI Employee Vault UI on http://%s:%d", args.host, args.port)
    logger.info("Vault: %s", VAULT_DIR)
    logger.info("Password: set via UI_PASSWORD env var (current: %s)", "*" * len(UI_PASSWORD))
    app.run(host=args.host, port=args.port, debug=args.debug)
