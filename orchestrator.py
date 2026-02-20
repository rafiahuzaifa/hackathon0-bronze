"""
Orchestrator.py — AI Employee Central Nervous System

Manages multiple watchers (Gmail, WhatsApp), polls every 60s,
triggers Claude AI for new files in /Needs_Action, handles cron
scheduling, and supports PM2 daemonization.

Usage:
    python orchestrator.py              # Run full orchestrator
    python orchestrator.py --simulate   # Run with simulated data (no Gmail/WhatsApp auth needed)
    python orchestrator.py --once       # Run a single cycle then exit

PM2:
    pm2 start ecosystem.config.js
"""

import os
import sys
import re
import json
import time
import signal
import logging
import argparse
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
import schedule

# Error handling & audit logging
from audit_logger import AuditLogger, ErrorCategory
from retry_handler import ErrorHandler, retry, classify_error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VAULT_DIR = Path("d:/hackathon0/hackathon/AI_Employee_Vault")
NEEDS_ACTION_DIR = VAULT_DIR / "Needs_Action"
DONE_DIR = VAULT_DIR / "Done"
PLANS_DIR = VAULT_DIR / "Plans"
PLAN_FILE = VAULT_DIR / "Plan.md"
DASHBOARD_FILE = VAULT_DIR / "Dashboard.md"
HANDBOOK_FILE = VAULT_DIR / "Company_Handbook.md"
LOG_FILE = VAULT_DIR / "orchestrator.log"
STATE_FILE = VAULT_DIR / ".orchestrator_state.json"

POLL_INTERVAL_SECONDS = 60
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

# Ensure directories exist
for d in [NEEDS_ACTION_DIR, DONE_DIR, PLANS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

logger = logging.getLogger("orchestrator")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Suppress noisy libs
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Error handling
error_handler = ErrorHandler(component="orchestrator")
audit = AuditLogger(component="orchestrator")


# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------
class OrchestratorState:
    """Persistent state across restarts."""

    def __init__(self):
        self.processed_files: set = set()
        self.cycle_count: int = 0
        self.last_run: Optional[str] = None
        self.errors: list = []
        self._load()

    def _load(self):
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.processed_files = set(data.get("processed_files", []))
                self.cycle_count = data.get("cycle_count", 0)
                self.last_run = data.get("last_run")
            except Exception:
                pass

    def save(self):
        data = {
            "processed_files": list(self.processed_files),
            "cycle_count": self.cycle_count,
            "last_run": self.last_run,
        }
        STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def mark_processed(self, filename: str):
        self.processed_files.add(filename)
        self.save()


# ---------------------------------------------------------------------------
# Company Handbook Rules Engine
# ---------------------------------------------------------------------------
def load_handbook_rules() -> list:
    """Parse Company_Handbook.md for rules."""
    rules = []
    if HANDBOOK_FILE.exists():
        content = HANDBOOK_FILE.read_text(encoding="utf-8")
        for line in content.splitlines():
            match = re.match(r"^\d+\.\s+(.+)$", line.strip())
            if match:
                rules.append(match.group(1))
    return rules


def apply_rules(text: str, rules: list) -> list:
    """Check text against handbook rules, return violations/flags."""
    flags = []
    text_lower = text.lower()

    for rule in rules:
        # Rule: Flag payments greater than $500
        if "flag payments" in rule.lower() and "$" in rule:
            amounts = re.findall(r"\$[\d,]+(?:\.\d{2})?", text)
            rs_amounts = re.findall(r"Rs\.?\s*[\d,]+", text, re.IGNORECASE)
            for amt in amounts:
                val = float(amt.replace("$", "").replace(",", ""))
                if val > 500:
                    flags.append(f"FLAG: Payment ${val:,.0f} exceeds $500 threshold (Handbook Rule)")

        # Rule: Always be polite on WhatsApp
        if "polite" in rule.lower() and "whatsapp" in rule.lower():
            flags.append("REMINDER: Maintain polite tone on WhatsApp (Handbook Rule)")

    return flags


# ---------------------------------------------------------------------------
# Claude AI Trigger
# ---------------------------------------------------------------------------
def trigger_claude_analysis(new_files: list, handbook_rules: list) -> Optional[str]:
    """
    Send new files to Claude for analysis and action plan generation.
    Returns the generated plan text, or None on failure.
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping Claude analysis")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping Claude analysis")
        return _generate_local_plan(new_files, handbook_rules)

    # Build context from files
    file_contents = []
    for fpath in new_files:
        try:
            content = Path(fpath).read_text(encoding="utf-8")
            file_contents.append(f"### File: {Path(fpath).name}\n```\n{content}\n```")
        except Exception as e:
            file_contents.append(f"### File: {Path(fpath).name}\nError reading: {e}")

    rules_text = "\n".join(f"- {r}" for r in handbook_rules) if handbook_rules else "No rules loaded."

    prompt = f"""You are an AI Employee managing an Obsidian vault. Analyze these new files from /Needs_Action and generate action items.

## Company Handbook Rules
{rules_text}

## New Files to Process
{chr(10).join(file_contents)}

## Instructions
1. For each file, extract: sender, subject/topic, priority, and key action items.
2. Apply company handbook rules (flag payments > $500, maintain polite tone on WhatsApp).
3. Detect urgent keywords: urgent, asap, emergency, critical, deadline, payment, invoice.
4. Output a structured action plan with checkboxes in Markdown format.
5. Group by category: Orders, WhatsApp Messages, Emails, Promotions.
"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        plan_text = response.content[0].text
        logger.info("Claude analysis complete")
        return plan_text
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return _generate_local_plan(new_files, handbook_rules)


def _generate_local_plan(new_files: list, handbook_rules: list) -> str:
    """Fallback: generate plan locally without Claude API."""
    lines = [f"## New Actions ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"]

    for fpath in new_files:
        try:
            content = Path(fpath).read_text(encoding="utf-8")
            fname = Path(fpath).name

            # Parse YAML frontmatter
            meta = {}
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        meta = yaml.safe_load(parts[1]) or {}
                    except Exception:
                        pass
                    body = parts[2].strip()
                else:
                    body = content
            else:
                body = content

            msg_type = meta.get("type", "unknown")
            sender = meta.get("from", meta.get("sender", "Unknown"))
            subject = meta.get("subject", meta.get("chat", fname))
            priority = meta.get("priority", "normal")

            # Apply handbook rules
            flags = apply_rules(body, handbook_rules)
            for fm_val in [str(meta.get("subject", "")), str(meta.get("from", ""))]:
                flags.extend(apply_rules(fm_val, handbook_rules))
            flags = list(set(flags))  # deduplicate

            # Detect keywords
            urgent_keywords = ["urgent", "asap", "emergency", "critical", "deadline"]
            is_urgent = any(kw in body.lower() or kw in str(subject).lower() for kw in urgent_keywords)
            if is_urgent:
                priority = "urgent"

            icon = {"urgent": "🔴", "high": "🟠", "normal": "🟢"}.get(priority, "⚪")

            lines.append(f"### {icon} {subject}")
            lines.append(f"**From:** {sender} | **Type:** {msg_type} | **Priority:** {priority}")

            if flags:
                for flag in flags:
                    lines.append(f"- [x] **{flag}**")

            lines.append(f"- [ ] Review and respond to {sender}")
            if is_urgent:
                lines.append("- [ ] **URGENT**: Handle immediately")
            if "payment" in body.lower() or "invoice" in body.lower():
                lines.append("- [ ] Process payment / review invoice")
            lines.append(f"- [ ] Move `{fname}` to `/Done` when complete")
            lines.append("")

        except Exception as e:
            lines.append(f"### Error processing {Path(fpath).name}: {e}\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Plan.md & Dashboard.md Writers
# ---------------------------------------------------------------------------
def update_plan_md(new_plan_section: str, cycle: int):
    """Append new actions to Plan.md."""
    existing = ""
    if PLAN_FILE.exists():
        existing = PLAN_FILE.read_text(encoding="utf-8")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    separator = f"\n\n---\n\n## Orchestrator Cycle #{cycle} — {timestamp}\n\n"

    updated = existing.rstrip() + separator + new_plan_section.strip() + "\n"
    PLAN_FILE.write_text(updated, encoding="utf-8")
    logger.info(f"Plan.md updated (cycle #{cycle})")


def update_dashboard(stats: dict, cycle: int):
    """Update Dashboard.md with latest orchestrator status."""
    if not DASHBOARD_FILE.exists():
        return

    existing = DASHBOARD_FILE.read_text(encoding="utf-8")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    new_entry = (
        f"- **{timestamp} (cycle #{cycle})**: "
        f"Gmail: {stats.get('gmail_new', 0)} new | "
        f"WhatsApp: {stats.get('wa_new', 0)} new ({stats.get('wa_urgent', 0)} urgent) | "
        f"Needs_Action: {stats.get('total_files', 0)} | "
        f"HITL: {stats.get('hitl_executed', 0)} exec, {stats.get('hitl_pending', 0)} pending | "
        f"Claude: {stats.get('claude_status', 'skipped')}"
    )

    # Insert after "## Status Update" line
    if "## Status Update" in existing:
        existing = existing.replace(
            "## Status Update\n",
            f"## Status Update\n{new_entry}\n",
        )
    else:
        existing = existing.rstrip() + f"\n\n## Status Update\n{new_entry}\n"

    DASHBOARD_FILE.write_text(existing, encoding="utf-8")
    logger.info(f"Dashboard.md updated (cycle #{cycle})")


# ---------------------------------------------------------------------------
# Gmail Watcher Integration
# ---------------------------------------------------------------------------
def run_gmail_watcher() -> dict:
    """Run the existing gmail_watcher.py with retry + circuit breaker."""
    stats = {"new": 0, "status": "ok"}

    def _fetch():
        before = set(f.name for f in NEEDS_ACTION_DIR.iterdir() if f.suffix == ".md")
        sys.path.insert(0, str(VAULT_DIR))
        import gmail_watcher
        gmail_watcher.fetch_unread_emails()
        after = set(f.name for f in NEEDS_ACTION_DIR.iterdir() if f.suffix == ".md")
        return after - before

    def _queue_fallback(e):
        audit.transient(f"Gmail API down, queueing: {e}", event="gmail_queued")
        error_handler.enqueue_task("gmail_fetch", "gmail", {}, reason=str(e))
        return set()

    ok, new_files, err = error_handler.safe_execute(
        fn=_fetch,
        fallback=_queue_fallback,
        max_retries=3,
        circuit_name="gmail_api",
    )

    if ok and new_files:
        stats["new"] = len(new_files)
        audit.info(f"Gmail: {len(new_files)} new emails", event="gmail_fetch_ok")
    elif err:
        stats["status"] = "error"
        stats["error"] = str(err)
        audit.error(f"Gmail watcher failed: {err}", event="gmail_fetch_fail",
                    category=classify_error(err))

    return stats


# ---------------------------------------------------------------------------
# WhatsApp Watcher Integration
# ---------------------------------------------------------------------------
def run_whatsapp_watcher(simulate: bool = False) -> dict:
    """Run the WhatsApp watcher with retry + graceful degradation."""
    def _run_wa():
        from whatsapp_watcher import run_whatsapp_watcher as wa_run, simulate_whatsapp_messages
        if simulate:
            return simulate_whatsapp_messages()
        return wa_run()

    def _queue_fallback(e):
        audit.transient(f"WhatsApp down, queueing: {e}", event="wa_queued")
        error_handler.enqueue_task("wa_fetch", "whatsapp", {"simulate": simulate}, reason=str(e))
        return {"status": "error", "new_messages": 0, "urgent": 0, "errors": [str(e)]}

    ok, result, err = error_handler.safe_execute(
        fn=_run_wa,
        fallback=_queue_fallback,
        max_retries=2,
        circuit_name="whatsapp",
    )

    if ok:
        audit.info(f"WhatsApp: {result.get('new_messages', 0)} msgs", event="wa_fetch_ok")
        return result
    return result if result else {"status": "error", "new_messages": 0, "urgent": 0, "errors": [str(err)]}


# ---------------------------------------------------------------------------
# Needs_Action Scanner
# ---------------------------------------------------------------------------
def scan_needs_action(state: OrchestratorState) -> list:
    """Scan /Needs_Action for unprocessed .md files."""
    new_files = []
    for f in sorted(NEEDS_ACTION_DIR.iterdir()):
        if f.suffix == ".md" and f.name not in state.processed_files:
            new_files.append(str(f))
    return new_files


# ---------------------------------------------------------------------------
# Cron / Scheduled Tasks
# ---------------------------------------------------------------------------
def daily_summary_task():
    """Daily summary — runs at 9:00 AM via schedule."""
    logger.info("Running daily summary task...")
    total = len(list(NEEDS_ACTION_DIR.glob("*.md")))
    done = len(list(DONE_DIR.glob("*.md")))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    summary = f"\n\n---\n## Daily Summary — {timestamp}\n"
    summary += f"- Pending items: {total}\n"
    summary += f"- Completed items: {done}\n"
    summary += f"- Orchestrator running: ✅\n"

    if DASHBOARD_FILE.exists():
        existing = DASHBOARD_FILE.read_text(encoding="utf-8")
        DASHBOARD_FILE.write_text(existing.rstrip() + summary, encoding="utf-8")
        logger.info("Daily summary written to Dashboard.md")


def setup_scheduled_tasks():
    """Configure recurring tasks."""
    schedule.every().day.at("09:00").do(daily_summary_task)
    schedule.every().day.at("17:00").do(daily_summary_task)
    logger.info("Scheduled tasks configured: daily summary at 09:00 and 17:00")


# ---------------------------------------------------------------------------
# Main Orchestration Cycle
# ---------------------------------------------------------------------------
def run_cycle(state: OrchestratorState, simulate: bool = False) -> dict:
    """Execute one full orchestrator cycle."""
    state.cycle_count += 1
    cycle = state.cycle_count
    state.last_run = datetime.now().isoformat()
    logger.info(f"{'='*60}")
    logger.info(f"CYCLE #{cycle} START — {state.last_run}")
    logger.info(f"{'='*60}")

    stats = {
        "cycle": cycle,
        "gmail_new": 0,
        "wa_new": 0,
        "wa_urgent": 0,
        "new_files_processed": 0,
        "total_files": 0,
        "claude_status": "skipped",
        "hitl_executed": 0,
        "hitl_expired": 0,
        "hitl_pending": 0,
        "errors": [],
    }

    # Step 1: Run Gmail Watcher
    logger.info("[1/6] Running Gmail watcher...")
    if simulate:
        logger.info("  (simulated — skipping Gmail)")
        stats["gmail_new"] = 0
    else:
        gmail_result = run_gmail_watcher()
        stats["gmail_new"] = gmail_result.get("new", 0)
        if gmail_result.get("status") != "ok":
            stats["errors"].append(f"Gmail: {gmail_result.get('error', 'unknown')}")

    # Step 2: Run WhatsApp Watcher
    logger.info("[2/6] Running WhatsApp watcher...")
    wa_result = run_whatsapp_watcher(simulate=simulate)
    stats["wa_new"] = wa_result.get("new_messages", 0)
    stats["wa_urgent"] = wa_result.get("urgent", 0)
    if wa_result.get("status") == "error":
        stats["errors"].append(f"WhatsApp: {'; '.join(wa_result.get('errors', []))}")

    # Step 3: Scan /Needs_Action for unprocessed files
    logger.info("[3/6] Scanning /Needs_Action...")
    new_files = scan_needs_action(state)
    stats["total_files"] = len(list(NEEDS_ACTION_DIR.glob("*.md")))
    stats["new_files_processed"] = len(new_files)
    logger.info(f"  Found {len(new_files)} new files, {stats['total_files']} total")

    # Step 4: Trigger Claude / generate plan for new files
    if new_files:
        logger.info(f"[4/6] Processing {len(new_files)} new files...")
        handbook_rules = load_handbook_rules()
        plan_section = trigger_claude_analysis(new_files, handbook_rules)

        if plan_section:
            update_plan_md(plan_section, cycle)
            stats["claude_status"] = "generated"
        else:
            stats["claude_status"] = "failed"

        # Mark files as processed
        for f in new_files:
            state.mark_processed(Path(f).name)
    else:
        logger.info("[4/6] No new files — skipping analysis")

    # Step 5: HITL Watcher — process approved actions, expire stale
    logger.info("[5/6] Running HITL watcher...")
    try:
        from hitl_watcher import HITLWatcher
        hitl = HITLWatcher()
        hitl_stats = hitl.scan_and_process()
        stats["hitl_executed"] = hitl_stats.get("executed", 0)
        stats["hitl_expired"] = hitl_stats.get("expired", 0)
        stats["hitl_pending"] = hitl_stats.get("pending", 0)
        if hitl_stats.get("errors"):
            stats["errors"].extend(hitl_stats["errors"])
        logger.info(f"  HITL: executed={stats['hitl_executed']}, expired={stats['hitl_expired']}, pending={stats['hitl_pending']}")
    except Exception as e:
        logger.error(f"HITL watcher error: {e}")
        stats["errors"].append(f"HITL: {e}")

    # Step 6: Update Dashboard
    logger.info("[6/6] Updating Dashboard.md...")
    update_dashboard(stats, cycle)

    # Step 6b: Process queued tasks (graceful degradation recovery)
    queue_stats = error_handler.process_queued(lambda t: logger.info(f"  Re-processing queued task: {t['id']}"))
    if queue_stats["processed"] > 0:
        logger.info(f"  Queue: {queue_stats['processed']} recovered, {queue_stats['dead_letter']} dead-lettered")
        audit.info(f"Queue drain: {queue_stats}", event="queue_processed", data=queue_stats)

    # Run any pending scheduled tasks
    schedule.run_pending()

    # Save state
    state.save()

    # Audit trail for cycle
    audit.audit(
        f"Cycle #{cycle} complete",
        event="cycle_complete",
        data={k: v for k, v in stats.items() if k != "errors"},
    )

    logger.info(f"CYCLE #{cycle} COMPLETE — "
                f"Gmail: +{stats['gmail_new']} | "
                f"WA: +{stats['wa_new']} ({stats['wa_urgent']} urgent) | "
                f"Processed: {stats['new_files_processed']} | "
                f"Total: {stats['total_files']} | "
                f"HITL: {stats['hitl_executed']} exec/{stats['hitl_pending']} pending | "
                f"Claude: {stats['claude_status']}")

    if stats["errors"]:
        logger.warning(f"Errors: {stats['errors']}")

    return stats


# ---------------------------------------------------------------------------
# Signal Handling (for PM2 graceful shutdown)
# ---------------------------------------------------------------------------
_shutdown = False


def handle_shutdown(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum} — shutting down gracefully...")
    _shutdown = True


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="AI Employee Orchestrator")
    parser.add_argument("--simulate", action="store_true", help="Use simulated data (no auth needed)")
    parser.add_argument("--once", action="store_true", help="Run a single cycle then exit")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL_SECONDS, help="Poll interval in seconds")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("AI EMPLOYEE ORCHESTRATOR STARTING")
    logger.info(f"  Vault: {VAULT_DIR}")
    logger.info(f"  Mode: {'simulate' if args.simulate else 'live'}")
    logger.info(f"  Poll interval: {args.interval}s")
    logger.info(f"  Single run: {args.once}")
    logger.info("=" * 60)

    state = OrchestratorState()
    setup_scheduled_tasks()

    if args.once:
        stats = run_cycle(state, simulate=args.simulate)
        print(json.dumps(stats, indent=2))
        return

    # Main loop (Ralph Wiggum iteration: keep going until clean)
    consecutive_clean = 0
    while not _shutdown:
        try:
            stats = run_cycle(state, simulate=args.simulate)

            if not stats["errors"]:
                consecutive_clean += 1
            else:
                consecutive_clean = 0

            if consecutive_clean >= 1 and args.simulate:
                logger.info(f"Ralph Wiggum check: {consecutive_clean} clean cycle(s) — system stable")

        except Exception as e:
            logger.error(f"CYCLE CRASH: {e}", exc_info=True)
            consecutive_clean = 0

        if _shutdown:
            break

        logger.info(f"Sleeping {args.interval}s until next cycle...")
        # Sleep in small increments for responsive shutdown
        for _ in range(args.interval):
            if _shutdown:
                break
            time.sleep(1)

    logger.info("Orchestrator shut down cleanly.")


if __name__ == "__main__":
    main()
