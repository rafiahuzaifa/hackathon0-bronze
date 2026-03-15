"""
orchestrator.py — AI Employee Master Process Manager
Gold Tier — Panaversity AI Employee Hackathon 2026

Manages all watcher subprocesses, processes vault tasks with Claude,
monitors the Approved/ queue, and runs scheduled briefings.

Usage:
    python orchestrator.py              # Start all services
    python orchestrator.py --dry-run    # DRY_RUN mode (default if .env not set)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.resolve()
VAULT_PATH = Path(os.environ.get("VAULT_PATH", str(BASE_DIR / "vault")))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MAX_ACTIONS_PER_HOUR = int(os.environ.get("MAX_ACTIONS_PER_HOUR", "10"))
POLL_INTERVAL = 15  # seconds between vault scans

NEEDS_ACTION_DIR = VAULT_PATH / "Needs_Action"
PENDING_APPROVAL_DIR = VAULT_PATH / "Pending_Approval"
APPROVED_DIR = VAULT_PATH / "Approved"
DONE_DIR = VAULT_PATH / "Done"
LOGS_DIR = VAULT_PATH / "Logs"
PIDS_DIR = VAULT_PATH / "pids"

CLAUDE_MODEL = "claude-opus-4-6"

REQUIRED_DIRS = [
    NEEDS_ACTION_DIR, PENDING_APPROVAL_DIR, APPROVED_DIR,
    DONE_DIR, LOGS_DIR, PIDS_DIR,
    VAULT_PATH / "Rejected", VAULT_PATH / "sessions",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("orchestrator")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def audit_log(event: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "message": message,
        "dry_run": DRY_RUN,
        **(extra or {}),
    }
    log_path = LOGS_DIR / "orchestrator.jsonl"
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    logger.info("[%s] %s", event, message)


# ---------------------------------------------------------------------------
# Vault helpers
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> Dict[str, Any]:
    """Extract YAML-like frontmatter between --- markers."""
    meta: Dict[str, Any] = {}
    if not text.startswith("---"):
        return meta
    parts = text.split("---", 2)
    if len(parts) < 3:
        return meta
    for line in parts[1].splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"')
    return meta


def ensure_dirs() -> None:
    for d in REQUIRED_DIRS:
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Claude task processor
# ---------------------------------------------------------------------------

class TaskProcessor:
    """Processes vault/Needs_Action/ files using Claude."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run
        self._client = None
        self._hourly_actions: List[float] = []

    def _get_client(self):
        if self._client:
            return self._client
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        import anthropic
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        return self._client

    def _check_rate_limit(self) -> bool:
        now = time.time()
        self._hourly_actions = [t for t in self._hourly_actions if now - t < 3600]
        if len(self._hourly_actions) >= MAX_ACTIONS_PER_HOUR:
            logger.warning("Rate limit reached: %d actions/hour", MAX_ACTIONS_PER_HOUR)
            return False
        return True

    def process_file(self, filepath: Path) -> bool:
        """
        Analyse a Needs_Action file with Claude and dispatch the result.

        Returns True if processed successfully.
        """
        if not self._check_rate_limit():
            return False

        try:
            content = filepath.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Could not read %s: %s", filepath, exc)
            return False

        meta = parse_frontmatter(content)
        source = meta.get("source", "unknown")
        risk = meta.get("risk", "low")

        logger.info("Processing: %s (source=%s, risk=%s)", filepath.name, source, risk)

        if self.dry_run:
            # In DRY_RUN, just move to Pending_Approval
            dest = PENDING_APPROVAL_DIR / filepath.name
            filepath.rename(dest)
            audit_log("TASK_DRY_RUN", f"Moved to Pending_Approval: {filepath.name}",
                      {"source": source, "risk": risk})
            return True

        # Call Claude
        prompt = self._build_prompt(content, meta)
        try:
            client = self._get_client()
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            analysis = response.content[0].text
            self._hourly_actions.append(time.time())
        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            return False

        # Parse Claude's decision
        action = self._parse_action(analysis)
        self._dispatch_action(filepath, content, meta, analysis, action)
        return True

    def _build_prompt(self, content: str, meta: Dict[str, Any]) -> str:
        handbook_path = VAULT_PATH / "Company_Handbook.md"
        handbook = ""
        if handbook_path.exists():
            handbook = handbook_path.read_text(encoding="utf-8")[:3000]

        return f"""You are an AI Employee assistant. Analyse this task and decide what action to take.

COMPANY HANDBOOK (excerpt):
{handbook}

TASK FILE:
{content[:4000]}

METADATA:
{json.dumps(meta, indent=2)}

Respond with a JSON object:
{{
  "action": "reply_email" | "post_social" | "approve_payment" | "schedule_meeting" | "flag_for_human" | "done",
  "priority": "high" | "medium" | "low",
  "draft_response": "string or null",
  "reason": "brief explanation",
  "requires_approval": true | false
}}

Rules:
- Any payment action ALWAYS requires_approval = true
- High risk items ALWAYS require_approval = true
- Unknown senders should be flagged
- Keep draft_response under 500 characters
"""

    def _parse_action(self, analysis: str) -> Dict[str, Any]:
        """Extract JSON from Claude's response."""
        try:
            match = re.search(r'\{[^{}]*"action"[^{}]*\}', analysis, re.DOTALL)
            if match:
                return json.loads(match.group())
        except (json.JSONDecodeError, AttributeError):
            pass
        return {"action": "flag_for_human", "requires_approval": True, "reason": "Could not parse"}

    def _dispatch_action(
        self, filepath: Path, content: str, meta: Dict[str, Any],
        analysis: str, action: Dict[str, Any]
    ) -> None:
        """Route processed file to appropriate vault directory."""
        requires_approval = action.get("requires_approval", True)
        action_type = action.get("action", "flag_for_human")
        draft = action.get("draft_response", "")

        # Append analysis to content
        enriched = (
            content + f"\n\n---\n## AI Analysis\n\n"
            f"**Action:** {action_type}\n"
            f"**Priority:** {action.get('priority', 'medium')}\n"
            f"**Reason:** {action.get('reason', '')}\n"
            + (f"\n**Draft Response:**\n\n{draft}\n" if draft else "")
        )

        if requires_approval or action_type == "flag_for_human":
            dest = PENDING_APPROVAL_DIR / filepath.name
            dest.write_text(enriched, encoding="utf-8")
            filepath.unlink(missing_ok=True)
            audit_log("TASK_PENDING", f"Pending approval: {filepath.name}", action)
        else:
            dest = DONE_DIR / filepath.name
            dest.write_text(enriched, encoding="utf-8")
            filepath.unlink(missing_ok=True)
            audit_log("TASK_DONE", f"Auto-resolved: {filepath.name}", action)


# ---------------------------------------------------------------------------
# Approval watcher
# ---------------------------------------------------------------------------

class ApprovalWatcher:
    """Watches Approved/ directory and dispatches MCP actions."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run
        self._processed: set[str] = set()

    def check(self) -> None:
        if not APPROVED_DIR.exists():
            return
        for filepath in APPROVED_DIR.glob("*.md"):
            if str(filepath) in self._processed:
                continue
            self._execute_approved(filepath)
            self._processed.add(str(filepath))

    def _execute_approved(self, filepath: Path) -> None:
        """Execute the action described in an approved file."""
        try:
            content = filepath.read_text(encoding="utf-8")
        except OSError:
            return

        meta = parse_frontmatter(content)
        source = meta.get("source", "unknown")
        action_type = meta.get("type", "unknown")

        logger.info("Executing approved action: %s (source=%s)", filepath.name, source)

        if self.dry_run:
            audit_log("APPROVED_DRY_RUN", f"Would execute: {filepath.name}", {"source": source})
        else:
            audit_log("APPROVED_EXECUTING", f"Executing: {filepath.name}", {"source": source})
            # Dispatch to appropriate MCP server based on source
            self._dispatch_mcp(source, action_type, content, meta)

        # Move to Done
        dest = DONE_DIR / filepath.name
        try:
            filepath.rename(dest)
        except OSError:
            pass
        audit_log("ACTION_DONE", f"Completed: {filepath.name}", {"source": source})

    def _dispatch_mcp(self, source: str, action_type: str, content: str, meta: dict) -> None:
        """Route to the appropriate MCP server."""
        from mcp_servers.email_mcp import EmailMCP
        from mcp_servers.social_mcp import SocialMCP

        if source == "gmail" and action_type == "reply_email":
            mcp = EmailMCP(VAULT_PATH, dry_run=False)
            to = meta.get("from", "")
            subject = "Re: " + meta.get("subject", "")
            body = meta.get("draft_response", "")
            if to and body:
                mcp.send_email(to=to, subject=subject, body=body)

        elif source in ("twitter", "linkedin", "facebook", "instagram"):
            mcp = SocialMCP(VAULT_PATH, dry_run=False)
            body = meta.get("content", content[:500])
            if source == "twitter":
                mcp.post_twitter(body)
            elif source == "linkedin":
                mcp.post_linkedin(body)
            elif source == "facebook":
                mcp.post_facebook(body)


# ---------------------------------------------------------------------------
# Cron scheduler
# ---------------------------------------------------------------------------

class CronScheduler:
    """Runs periodic scheduled jobs."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run
        self._jobs: List[Dict[str, Any]] = []
        self._last_run: Dict[str, float] = {}

    def add_job(self, name: str, interval_seconds: int, func) -> None:
        self._jobs.append({"name": name, "interval": interval_seconds, "func": func})

    def tick(self) -> None:
        now = time.time()
        for job in self._jobs:
            last = self._last_run.get(job["name"], 0)
            if now - last >= job["interval"]:
                try:
                    job["func"]()
                    self._last_run[job["name"]] = now
                except Exception as exc:
                    logger.error("Cron job %s failed: %s", job["name"], exc)

    def morning_briefing(self) -> None:
        """Generate daily morning briefing."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        pending = list(PENDING_APPROVAL_DIR.glob("*.md")) if PENDING_APPROVAL_DIR.exists() else []
        needs = list(NEEDS_ACTION_DIR.glob("*.md")) if NEEDS_ACTION_DIR.exists() else []
        content = (
            f"# Morning Briefing — {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"**Generated:** {ts}\n\n"
            f"## Queue Status\n\n"
            f"- Needs Action: {len(needs)} items\n"
            f"- Pending Approval: {len(pending)} items\n\n"
            f"## Action Required\n\n"
            + ("\n".join(f"- {f.name}" for f in pending[:10]) or "_None pending_")
        )
        NEEDS_ACTION_DIR.mkdir(parents=True, exist_ok=True)
        (NEEDS_ACTION_DIR / f"BRIEFING_{ts}.md").write_text(content, encoding="utf-8")
        audit_log("MORNING_BRIEFING", "Morning briefing generated", {"pending": len(pending)})


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """Master process that coordinates all AI Employee components."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run
        self.task_processor = TaskProcessor(dry_run=dry_run)
        self.approval_watcher = ApprovalWatcher(dry_run=dry_run)
        self.scheduler = CronScheduler(dry_run=dry_run)
        self._running = False

        # Schedule morning briefing every 24h
        self.scheduler.add_job("morning_briefing", 86400, self.scheduler.morning_briefing)

    def start(self) -> None:
        ensure_dirs()
        self._running = True
        mode = "DRY_RUN" if self.dry_run else "LIVE"
        logger.info("=" * 60)
        logger.info("AI Employee Orchestrator starting [%s mode]", mode)
        logger.info("Vault: %s", VAULT_PATH)
        logger.info("=" * 60)
        audit_log("ORCHESTRATOR_START", f"Orchestrator started [{mode}]",
                  {"vault": str(VAULT_PATH), "dry_run": self.dry_run})

        # Start FastAPI server in background thread
        api_thread = threading.Thread(target=self._start_api_server, daemon=True)
        api_thread.start()

        # Main loop
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error("Orchestrator tick error: %s", exc, exc_info=True)
            time.sleep(POLL_INTERVAL)

    def stop(self) -> None:
        self._running = False
        logger.info("Orchestrator stopping…")
        audit_log("ORCHESTRATOR_STOP", "Orchestrator stopped", {})

    def _tick(self) -> None:
        """One cycle: process new tasks, check approvals, run cron."""
        # Process new Needs_Action files
        if NEEDS_ACTION_DIR.exists():
            for filepath in list(NEEDS_ACTION_DIR.glob("*.md"))[:5]:  # max 5 per tick
                if not filepath.name.startswith("BRIEFING_"):
                    self.task_processor.process_file(filepath)

        # Check approved actions
        self.approval_watcher.check()

        # Run scheduled jobs
        self.scheduler.tick()

    def _start_api_server(self) -> None:
        """Start the FastAPI server in a daemon thread."""
        try:
            import uvicorn
            from api.server import app
            host = os.environ.get("API_HOST", "127.0.0.1")
            port = int(os.environ.get("API_PORT", "8000"))
            logger.info("Starting FastAPI server on %s:%d", host, port)
            uvicorn.run(app, host=host, port=port, log_level="warning")
        except ImportError:
            logger.warning("FastAPI/uvicorn not installed — API server disabled")
        except Exception as exc:
            logger.error("API server error: %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AI Employee Orchestrator")
    parser.add_argument("--dry-run", action="store_true", default=DRY_RUN,
                        help="Enable DRY_RUN mode (no real actions)")
    parser.add_argument("--vault", type=str, default=str(VAULT_PATH),
                        help="Path to Obsidian vault")
    args = parser.parse_args()

    # Allow vault override from CLI
    global VAULT_PATH, NEEDS_ACTION_DIR, PENDING_APPROVAL_DIR, APPROVED_DIR, DONE_DIR
    if args.vault != str(VAULT_PATH):
        VAULT_PATH = Path(args.vault)
        NEEDS_ACTION_DIR = VAULT_PATH / "Needs_Action"
        PENDING_APPROVAL_DIR = VAULT_PATH / "Pending_Approval"
        APPROVED_DIR = VAULT_PATH / "Approved"
        DONE_DIR = VAULT_PATH / "Done"

    orchestrator = Orchestrator(dry_run=args.dry_run)
    try:
        orchestrator.start()
    except KeyboardInterrupt:
        orchestrator.stop()


if __name__ == "__main__":
    main()
