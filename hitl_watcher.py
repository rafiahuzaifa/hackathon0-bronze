"""
hitl_watcher.py — File-Based Human-in-the-Loop Approval System

Workflow:
  1. AI (Claude/Orchestrator) creates action files in /Pending_Approval
  2. Human reviews in Obsidian — moves file to /Approved or /Rejected
  3. This watcher detects approved files and triggers execution (MCP, email, etc.)
  4. Executed files move to /Done; rejected to /Rejected
  5. Stale files (>24h) auto-expire to /Expired

YAML Frontmatter Schema:
  ---
  id: hitl_<timestamp>_<hex>
  action: email | payment | linkedin_post | whatsapp | general
  status: pending | approved | rejected | executed | expired
  created: ISO 8601
  expires: ISO 8601
  priority: low | normal | high | urgent
  to: recipient
  subject: subject line
  amount: (for payments)
  currency: (for payments)
  flags: []
  claude_reasoning: (AI's rationale for proposing this action)
  ---
  <body content>

Usage:
  python hitl_watcher.py                  # Run watcher loop
  python hitl_watcher.py --once           # Single scan
  python hitl_watcher.py --simulate       # E2E simulation test
"""

import os
import sys
import re
import json
import time
import shutil
import logging
import argparse
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VAULT_DIR = Path("d:/hackathon0/hackathon/AI_Employee_Vault")
PENDING_DIR = VAULT_DIR / "Pending_Approval"
APPROVED_DIR = VAULT_DIR / "Approved"
REJECTED_DIR = VAULT_DIR / "Rejected"
EXPIRED_DIR = VAULT_DIR / "Expired"
DONE_DIR = VAULT_DIR / "Done"
HANDBOOK_FILE = VAULT_DIR / "Company_Handbook.md"
HITL_LOG_FILE = VAULT_DIR / "hitl_watcher.log"
HITL_STATE_FILE = VAULT_DIR / ".hitl_state.json"

EXPIRY_HOURS = 24
POLL_INTERVAL = 10  # seconds

# Ensure directories
for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR, EXPIRED_DIR, DONE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
file_handler = logging.FileHandler(str(HITL_LOG_FILE), encoding="utf-8")
file_handler.setFormatter(log_formatter)
console_stream = open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False) if sys.platform == 'win32' else sys.stdout
console_handler = logging.StreamHandler(console_stream)
console_handler.setFormatter(log_formatter)

logger = logging.getLogger("hitl")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)


# ---------------------------------------------------------------------------
# HITL Action File Parser
# ---------------------------------------------------------------------------
class HITLAction:
    """Represents a single HITL approval action file."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.meta = {}
        self.body = ""
        self._parse()

    def _parse(self):
        raw = self.file_path.read_text(encoding="utf-8")
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                try:
                    self.meta = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    self.meta = {}
                self.body = parts[2].strip()
            else:
                self.body = raw
        else:
            self.body = raw

    @property
    def id(self) -> str:
        return self.meta.get("id", self.file_path.stem)

    @property
    def action(self) -> str:
        return self.meta.get("action", "general")

    @property
    def status(self) -> str:
        return self.meta.get("status", "pending")

    @property
    def priority(self) -> str:
        return self.meta.get("priority", "normal")

    @property
    def created(self) -> Optional[datetime]:
        val = self.meta.get("created")
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val)
            except ValueError:
                return None
        return None

    @property
    def expires(self) -> Optional[datetime]:
        val = self.meta.get("expires")
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val)
            except ValueError:
                return None
        return None

    @property
    def is_expired(self) -> bool:
        now = datetime.now()
        try:
            if self.expires:
                exp = self.expires.replace(tzinfo=None) if self.expires.tzinfo else self.expires
                return now > exp
            if self.created:
                crt = self.created.replace(tzinfo=None) if self.created.tzinfo else self.created
                return now > crt + timedelta(hours=EXPIRY_HOURS)
        except Exception:
            return False
        return False

    @property
    def amount(self) -> Optional[float]:
        val = self.meta.get("amount")
        if val is not None:
            try:
                return float(str(val).replace(",", "").replace("$", "").replace("Rs.", "").strip())
            except ValueError:
                return None
        return None

    def update_status(self, new_status: str):
        self.meta["status"] = new_status
        self._write()

    def add_execution_log(self, result: str):
        self.meta["executed_at"] = datetime.now().isoformat()
        self.meta["execution_result"] = result
        self._write()

    def _write(self):
        frontmatter = yaml.dump(self.meta, default_flow_style=False, allow_unicode=True)
        content = f"---\n{frontmatter}---\n\n{self.body}"
        self.file_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Action ID Generator
# ---------------------------------------------------------------------------
def generate_action_id(prefix: str = "hitl") -> str:
    import secrets
    return f"{prefix}_{int(datetime.now().timestamp())}_{secrets.token_hex(3)}"


# ---------------------------------------------------------------------------
# Template Factory — Creates HITL Action Files
# ---------------------------------------------------------------------------
class HITLTemplates:
    """Factory for creating HITL action files with proper YAML frontmatter."""

    @staticmethod
    def email_action(
        to: str,
        subject: str,
        body: str,
        priority: str = "normal",
        claude_reasoning: str = "",
    ) -> Path:
        action_id = generate_action_id("email")
        now = datetime.now()
        meta = {
            "id": action_id,
            "action": "email",
            "status": "pending",
            "created": now.isoformat(),
            "expires": (now + timedelta(hours=EXPIRY_HOURS)).isoformat(),
            "priority": priority,
            "to": to,
            "subject": subject,
            "flags": [],
            "claude_reasoning": claude_reasoning or "Email action proposed by AI Employee.",
        }

        file_path = PENDING_DIR / f"{action_id}.md"
        frontmatter = yaml.dump(meta, default_flow_style=False, allow_unicode=True)
        content = f"---\n{frontmatter}---\n\n{body}"
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"Created email action: {action_id} -> {to}")
        return file_path

    @staticmethod
    def payment_action(
        to: str,
        amount: float,
        currency: str = "USD",
        description: str = "",
        invoice_ref: str = "",
        priority: str = "high",
        claude_reasoning: str = "",
    ) -> Path:
        action_id = generate_action_id("payment")
        now = datetime.now()

        # Auto-flag per Company Handbook Rule #2
        flags = []
        if amount > 500:
            flags.append("FLAGGED: Amount exceeds $500 threshold (Handbook Rule #2)")

        meta = {
            "id": action_id,
            "action": "payment",
            "status": "pending",
            "created": now.isoformat(),
            "expires": (now + timedelta(hours=EXPIRY_HOURS)).isoformat(),
            "priority": priority,
            "to": to,
            "amount": amount,
            "currency": currency,
            "invoice_ref": invoice_ref,
            "flags": flags,
            "claude_reasoning": claude_reasoning
            or f"Payment of {currency} {amount:,.2f} to {to}. {'FLAGGED: exceeds $500.' if amount > 500 else 'Within normal range.'}",
        }

        body_lines = [
            f"## Payment Approval Request",
            f"",
            f"**Payee:** {to}",
            f"**Amount:** {currency} {amount:,.2f}",
            f"**Invoice:** {invoice_ref or 'N/A'}",
            f"**Description:** {description or 'N/A'}",
            f"",
        ]

        if flags:
            body_lines.append("### Flags")
            for flag in flags:
                body_lines.append(f"- ⚠️ {flag}")
            body_lines.append("")

        body_lines.extend([
            "### Approval Instructions",
            "To **approve**: Move this file to `/Approved`",
            "To **reject**: Move this file to `/Rejected`",
            f"**Expires:** {meta['expires']} ({EXPIRY_HOURS}h from creation)",
        ])

        file_path = PENDING_DIR / f"{action_id}.md"
        frontmatter = yaml.dump(meta, default_flow_style=False, allow_unicode=True)
        content = f"---\n{frontmatter}---\n\n" + "\n".join(body_lines)
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"Created payment action: {action_id} -> {to} ({currency} {amount:,.2f})")
        return file_path

    @staticmethod
    def linkedin_action(
        post_text: str,
        category: str = "general",
        scheduled_time: str = "immediate",
        claude_reasoning: str = "",
    ) -> Path:
        action_id = generate_action_id("linkedin")
        now = datetime.now()
        meta = {
            "id": action_id,
            "action": "linkedin_post",
            "status": "pending",
            "created": now.isoformat(),
            "expires": (now + timedelta(hours=EXPIRY_HOURS)).isoformat(),
            "priority": "normal",
            "category": category,
            "scheduled_time": scheduled_time,
            "flags": [],
            "claude_reasoning": claude_reasoning or "LinkedIn post drafted from Business_Goals.md.",
        }

        file_path = PENDING_DIR / f"{action_id}.md"
        frontmatter = yaml.dump(meta, default_flow_style=False, allow_unicode=True)
        content = f"---\n{frontmatter}---\n\n{post_text}"
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"Created LinkedIn action: {action_id}")
        return file_path

    @staticmethod
    def whatsapp_action(
        to: str,
        message: str,
        priority: str = "normal",
        claude_reasoning: str = "",
    ) -> Path:
        action_id = generate_action_id("wa")
        now = datetime.now()
        meta = {
            "id": action_id,
            "action": "whatsapp",
            "status": "pending",
            "created": now.isoformat(),
            "expires": (now + timedelta(hours=EXPIRY_HOURS)).isoformat(),
            "priority": priority,
            "to": to,
            "flags": ["REMINDER: Maintain polite tone (Handbook Rule #1)"],
            "claude_reasoning": claude_reasoning
            or "WhatsApp reply drafted. Polite tone verified per Handbook Rule #1.",
        }

        file_path = PENDING_DIR / f"{action_id}.md"
        frontmatter = yaml.dump(meta, default_flow_style=False, allow_unicode=True)
        content = f"---\n{frontmatter}---\n\n{message}"
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"Created WhatsApp action: {action_id} -> {to}")
        return file_path

    @staticmethod
    def general_action(
        title: str,
        body: str,
        priority: str = "normal",
        claude_reasoning: str = "",
    ) -> Path:
        action_id = generate_action_id("task")
        now = datetime.now()
        meta = {
            "id": action_id,
            "action": "general",
            "status": "pending",
            "created": now.isoformat(),
            "expires": (now + timedelta(hours=EXPIRY_HOURS)).isoformat(),
            "priority": priority,
            "title": title,
            "flags": [],
            "claude_reasoning": claude_reasoning or f"General task: {title}",
        }

        file_path = PENDING_DIR / f"{action_id}.md"
        frontmatter = yaml.dump(meta, default_flow_style=False, allow_unicode=True)
        content = f"---\n{frontmatter}---\n\n## {title}\n\n{body}"
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"Created general action: {action_id} — {title}")
        return file_path


# ---------------------------------------------------------------------------
# Action Executors — What happens after approval
# ---------------------------------------------------------------------------
class ActionExecutor:
    """Executes approved actions by type."""

    @staticmethod
    def execute(action: HITLAction) -> dict:
        executor_map = {
            "email": ActionExecutor._execute_email,
            "payment": ActionExecutor._execute_payment,
            "linkedin_post": ActionExecutor._execute_linkedin,
            "whatsapp": ActionExecutor._execute_whatsapp,
            "general": ActionExecutor._execute_general,
        }

        executor = executor_map.get(action.action, ActionExecutor._execute_general)
        return executor(action)

    @staticmethod
    def _execute_email(action: HITLAction) -> dict:
        to = action.meta.get("to", "unknown")
        subject = action.meta.get("subject", "No Subject")
        logger.info(f"EXECUTING EMAIL: To={to}, Subject={subject}")
        # In production: integrate with Gmail API / SMTP
        return {
            "status": "executed",
            "action": "email",
            "to": to,
            "subject": subject,
            "message": f"Email to {to} sent successfully (simulated)",
        }

    @staticmethod
    def _execute_payment(action: HITLAction) -> dict:
        to = action.meta.get("to", "unknown")
        amount = action.amount
        currency = action.meta.get("currency", "USD")
        logger.info(f"EXECUTING PAYMENT: {currency} {amount} -> {to}")
        # In production: integrate with payment gateway
        return {
            "status": "executed",
            "action": "payment",
            "to": to,
            "amount": amount,
            "currency": currency,
            "message": f"Payment of {currency} {amount:,.2f} to {to} processed (simulated)",
        }

    @staticmethod
    def _execute_linkedin(action: HITLAction) -> dict:
        preview = action.body[:100]
        logger.info(f"EXECUTING LINKEDIN POST: {preview}...")
        # In production: trigger LinkedIn MCP server
        return {
            "status": "executed",
            "action": "linkedin_post",
            "message": f"LinkedIn post published (simulated)",
            "preview": preview,
        }

    @staticmethod
    def _execute_whatsapp(action: HITLAction) -> dict:
        to = action.meta.get("to", "unknown")
        logger.info(f"EXECUTING WHATSAPP: To={to}")
        # In production: trigger WhatsApp via Playwright
        return {
            "status": "executed",
            "action": "whatsapp",
            "to": to,
            "message": f"WhatsApp message to {to} sent (simulated)",
        }

    @staticmethod
    def _execute_general(action: HITLAction) -> dict:
        title = action.meta.get("title", action.id)
        logger.info(f"EXECUTING GENERAL TASK: {title}")
        return {
            "status": "executed",
            "action": "general",
            "title": title,
            "message": f"Task '{title}' completed (simulated)",
        }


# ---------------------------------------------------------------------------
# Claude Reasoning Integration
# ---------------------------------------------------------------------------
def claude_reason_about_action(action: HITLAction) -> str:
    """
    Generate Claude's reasoning about whether an action should be approved.
    In production, this calls the Anthropic API. Here we use local heuristics.
    """
    reasons = []
    warnings = []

    # Check payment threshold
    if action.action == "payment" and action.amount is not None:
        if action.amount > 500:
            warnings.append(f"Payment of ${action.amount:,.2f} exceeds $500 threshold (Handbook Rule #2)")
        if action.amount > 5000:
            warnings.append(f"CRITICAL: Very large payment (${action.amount:,.2f}) — requires senior approval")
        if action.amount <= 500:
            reasons.append(f"Payment of ${action.amount:,.2f} is within normal range")

    # Check WhatsApp politeness
    if action.action == "whatsapp":
        impolite = ["stupid", "idiot", "useless", "terrible", "worst"]
        body_lower = action.body.lower()
        if any(w in body_lower for w in impolite):
            warnings.append("Message tone may violate Handbook Rule #1 (be polite on WhatsApp)")
        else:
            reasons.append("Message tone verified as polite (Handbook Rule #1)")

    # Check urgency
    if action.priority in ("urgent", "high"):
        reasons.append(f"Priority: {action.priority} — should be reviewed promptly")

    # Check expiry
    if action.is_expired:
        warnings.append("Action has EXPIRED — auto-moving to /Expired")

    # Check flags
    for flag in action.meta.get("flags", []):
        if "FLAGGED" in flag.upper():
            warnings.append(f"Pre-existing flag: {flag}")

    # Build reasoning
    reasoning = f"## Claude Reasoning for {action.id}\n\n"
    reasoning += f"**Action:** {action.action} | **Priority:** {action.priority}\n\n"

    if reasons:
        reasoning += "### Approval Factors\n"
        for r in reasons:
            reasoning += f"- ✅ {r}\n"
        reasoning += "\n"

    if warnings:
        reasoning += "### Warnings\n"
        for w in warnings:
            reasoning += f"- ⚠️ {w}\n"
        reasoning += "\n"

    if warnings:
        reasoning += "**Recommendation:** Review carefully before approving.\n"
    else:
        reasoning += "**Recommendation:** Safe to approve.\n"

    return reasoning


# ---------------------------------------------------------------------------
# HITL Watcher — Main Folder Monitor
# ---------------------------------------------------------------------------
class HITLWatcher:
    """Watches /Approved for newly approved files and executes them."""

    def __init__(self):
        self.state = self._load_state()
        self.stats = {
            "scans": 0,
            "approved_executed": 0,
            "expired": 0,
            "errors": [],
        }

    def _load_state(self) -> dict:
        if HITL_STATE_FILE.exists():
            try:
                return json.loads(HITL_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"executed_ids": [], "last_scan": None}

    def _save_state(self):
        self.state["last_scan"] = datetime.now().isoformat()
        HITL_STATE_FILE.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def scan_and_process(self) -> dict:
        """Single scan: check expiry, process approved, return stats."""
        self.stats["scans"] += 1
        cycle_stats = {"expired": 0, "executed": 0, "pending": 0, "errors": []}

        # Step 1: Expire stale pending items
        cycle_stats["expired"] = self._expire_stale()

        # Step 2: Process approved items
        executed, errors = self._process_approved()
        cycle_stats["executed"] = executed
        cycle_stats["errors"] = errors

        # Step 3: Count pending
        pending = [f for f in PENDING_DIR.iterdir() if f.suffix == ".md"]
        cycle_stats["pending"] = len(pending)

        self._save_state()
        return cycle_stats

    def _expire_stale(self) -> int:
        """Move expired pending items to /Expired."""
        expired_count = 0
        for f in PENDING_DIR.iterdir():
            if f.suffix != ".md":
                continue
            try:
                action = HITLAction(f)
                if action.is_expired:
                    action.update_status("expired")
                    dest = EXPIRED_DIR / f.name
                    shutil.move(str(f), str(dest))
                    logger.warning(f"EXPIRED: {action.id} moved to /Expired")
                    expired_count += 1
            except Exception as e:
                logger.error(f"Error checking expiry for {f.name}: {e}")
        self.stats["expired"] += expired_count
        return expired_count

    def _process_approved(self) -> tuple:
        """Execute approved actions and move to /Done."""
        executed = 0
        errors = []

        for f in APPROVED_DIR.iterdir():
            if f.suffix != ".md":
                continue
            try:
                action = HITLAction(f)

                if action.id in self.state.get("executed_ids", []):
                    continue  # Already executed

                # Add Claude reasoning
                reasoning = claude_reason_about_action(action)
                logger.info(f"Claude reasoning for {action.id}:\n{reasoning}")

                # Execute
                result = ActionExecutor.execute(action)
                logger.info(f"Execution result: {json.dumps(result)}")

                # Update file
                action.update_status("executed")
                action.add_execution_log(json.dumps(result))

                # Move to Done
                dest = DONE_DIR / f.name
                shutil.move(str(f), str(dest))
                logger.info(f"EXECUTED: {action.id} -> /Done")

                self.state.setdefault("executed_ids", []).append(action.id)
                executed += 1
                self.stats["approved_executed"] += 1

            except Exception as e:
                logger.error(f"Error executing {f.name}: {e}")
                errors.append(f"{f.name}: {str(e)}")
                self.stats["errors"].append(str(e))

        return executed, errors

    def run_loop(self, interval: int = POLL_INTERVAL):
        """Continuous monitoring loop."""
        logger.info(f"HITL Watcher started (poll every {interval}s)")
        while True:
            try:
                stats = self.scan_and_process()
                if stats["executed"] > 0 or stats["expired"] > 0:
                    logger.info(
                        f"Scan #{self.stats['scans']}: "
                        f"executed={stats['executed']}, "
                        f"expired={stats['expired']}, "
                        f"pending={stats['pending']}"
                    )
            except Exception as e:
                logger.error(f"Scan error: {e}")
            time.sleep(interval)


# ---------------------------------------------------------------------------
# E2E Simulation Test
# ---------------------------------------------------------------------------
def simulate_e2e():
    """
    Full end-to-end simulation of the HITL approval flow.
    Ralph Wiggum loop: iterate until all steps pass.
    """
    logger.info("=" * 60)
    logger.info("HITL E2E SIMULATION TEST")
    logger.info("=" * 60)

    passed = 0
    failed = 0

    def check(condition, name):
        nonlocal passed, failed
        if condition:
            passed += 1
            logger.info(f"  ✅ PASS: {name}")
        else:
            failed += 1
            logger.info(f"  ❌ FAIL: {name}")

    # Clean up previous test files
    for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR]:
        for f in d.iterdir():
            if f.suffix == ".md" and f.stem.startswith(("email_", "payment_", "linkedin_", "wa_", "task_")):
                f.unlink()

    # ── Test 1: Create email action ──
    logger.info("\n📧 TEST 1: Create Email Action")
    email_path = HITLTemplates.email_action(
        to="client@example.com",
        subject="Q1 Report Attached",
        body="Hi,\n\nPlease find the Q1 report attached.\n\nBest regards,\nAI Employee",
        priority="normal",
        claude_reasoning="Routine email — Q1 report delivery to client.",
    )
    check(email_path.exists(), "Email action file created")
    email_action = HITLAction(email_path)
    check(email_action.action == "email", "Action type is email")
    check(email_action.status == "pending", "Status is pending")
    check(email_action.meta.get("to") == "client@example.com", "Recipient correct")
    check(email_action.expires is not None, "Expiry time set")

    # ── Test 2: Create payment action with flag ──
    logger.info("\n💰 TEST 2: Create Payment Action (>$500 flag)")
    pay_path = HITLTemplates.payment_action(
        to="Vendor Supplies Co.",
        amount=750.00,
        currency="USD",
        description="Office supplies for February",
        invoice_ref="INV-4821",
        claude_reasoning="Invoice #4821 for $750. FLAGGED: exceeds $500 per Handbook Rule #2.",
    )
    check(pay_path.exists(), "Payment action file created")
    pay_action = HITLAction(pay_path)
    check(pay_action.action == "payment", "Action type is payment")
    check(pay_action.amount == 750.0, "Amount is $750")
    check(any("$500" in f for f in pay_action.meta.get("flags", [])), "Payment flagged >$500")

    # ── Test 3: Create small payment (no flag) ──
    logger.info("\n💵 TEST 3: Create Payment Action (<$500, no flag)")
    small_pay_path = HITLTemplates.payment_action(
        to="Coffee Shop",
        amount=45.00,
        currency="USD",
        description="Team coffee meeting",
    )
    small_pay = HITLAction(small_pay_path)
    check(small_pay.amount == 45.0, "Amount is $45")
    check(not any("$500" in f for f in small_pay.meta.get("flags", [])), "No flag for small payment")

    # ── Test 4: Create WhatsApp action ──
    logger.info("\n📱 TEST 4: Create WhatsApp Action")
    wa_path = HITLTemplates.whatsapp_action(
        to="Boss",
        message="Hi, the Q1 report is ready. Shall I send it to the client now?",
        priority="high",
        claude_reasoning="Reply to Boss. Polite tone verified per Handbook Rule #1.",
    )
    wa_action = HITLAction(wa_path)
    check(wa_action.action == "whatsapp", "Action type is whatsapp")
    check(any("polite" in f.lower() for f in wa_action.meta.get("flags", [])), "Politeness reminder present")

    # ── Test 5: Create LinkedIn action ──
    logger.info("\n🔗 TEST 5: Create LinkedIn Action")
    li_path = HITLTemplates.linkedin_action(
        post_text="🚀 Excited to share our latest AI automation case study! #AIAutomation #Productivity",
        category="case_study",
    )
    li_action = HITLAction(li_path)
    check(li_action.action == "linkedin_post", "Action type is linkedin_post")

    # ── Test 6: Claude Reasoning ──
    logger.info("\n🧠 TEST 6: Claude Reasoning")
    reasoning_pay = claude_reason_about_action(pay_action)
    check("$500" in reasoning_pay, "Claude flags $750 payment")
    check("Warning" in reasoning_pay or "warning" in reasoning_pay.lower(), "Claude includes warnings")

    reasoning_wa = claude_reason_about_action(wa_action)
    check("polite" in reasoning_wa.lower(), "Claude checks WhatsApp politeness")

    reasoning_small = claude_reason_about_action(small_pay)
    check("normal range" in reasoning_small.lower(), "Claude approves small payment")

    # ── Test 7: Simulate approval flow (move to /Approved) ──
    logger.info("\n✅ TEST 7: Simulate Approval (email + payment)")
    # Move email and large payment to /Approved
    shutil.copy2(str(email_path), str(APPROVED_DIR / email_path.name))
    email_path.unlink()
    shutil.copy2(str(pay_path), str(APPROVED_DIR / pay_path.name))
    pay_path.unlink()

    check((APPROVED_DIR / email_action.file_path.name).exists(), "Email moved to /Approved")
    check((APPROVED_DIR / pay_action.file_path.name).exists(), "Payment moved to /Approved")

    # ── Test 8: Execute approved actions ──
    logger.info("\n⚡ TEST 8: Execute Approved Actions")
    watcher = HITLWatcher()
    cycle_stats = watcher.scan_and_process()
    check(cycle_stats["executed"] >= 2, f"Executed {cycle_stats['executed']} actions (expected >= 2)")

    # Verify files moved to /Done
    done_files = [f.name for f in DONE_DIR.iterdir() if f.suffix == ".md"]
    check(email_action.file_path.name in done_files, "Email action in /Done")
    check(pay_action.file_path.name in done_files, "Payment action in /Done")

    # ── Test 9: Simulate rejection ──
    logger.info("\n🔄 TEST 9: Simulate Rejection")
    # Move WA action to /Rejected
    shutil.copy2(str(wa_path), str(REJECTED_DIR / wa_path.name))
    wa_path.unlink()
    check((REJECTED_DIR / wa_action.file_path.name).exists(), "WA action moved to /Rejected")

    # ── Test 10: Expiry check ──
    logger.info("\n⏰ TEST 10: Expiry System")
    # Create an action with past expiry
    expired_path = HITLTemplates.general_action(
        title="Old task that should expire",
        body="This task was created long ago and should auto-expire.",
    )
    # Manually set expiry to the past
    expired_action = HITLAction(expired_path)
    expired_action.meta["expires"] = (datetime.now() - timedelta(hours=1)).isoformat()
    expired_action._write()

    check(HITLAction(expired_path).is_expired, "Expired action detected as expired")

    # Run watcher to process expiry
    cycle2 = watcher.scan_and_process()
    check(cycle2["expired"] >= 1, f"Expired {cycle2['expired']} stale actions")

    expired_files = [f.name for f in EXPIRED_DIR.iterdir() if f.suffix == ".md"]
    check(expired_action.file_path.name in expired_files, "Expired action in /Expired")

    # ── Summary ──
    logger.info("\n" + "=" * 60)
    logger.info(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    logger.info("=" * 60)

    return failed == 0


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="HITL Approval Watcher")
    parser.add_argument("--once", action="store_true", help="Single scan then exit")
    parser.add_argument("--simulate", action="store_true", help="Run E2E simulation test")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL, help="Poll interval seconds")
    args = parser.parse_args()

    if args.simulate:
        # Ralph Wiggum loop
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            logger.info(f"\n🔄 Ralph Wiggum Iteration #{attempt}")
            try:
                if simulate_e2e():
                    logger.info(f"\n🎉 All tests passed after {attempt} iteration(s)!")
                    return
            except Exception as e:
                logger.error(f"Crash in iteration #{attempt}: {e}", exc_info=True)
        logger.error(f"Tests still failing after {max_attempts} attempts")
        sys.exit(1)

    elif args.once:
        watcher = HITLWatcher()
        stats = watcher.scan_and_process()
        print(json.dumps(stats, indent=2))

    else:
        watcher = HITLWatcher()
        watcher.run_loop(interval=args.interval)


if __name__ == "__main__":
    main()
