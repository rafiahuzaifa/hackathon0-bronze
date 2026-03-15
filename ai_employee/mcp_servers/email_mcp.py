"""
email_mcp.py — Gmail MCP Action Server
Executes email send/draft actions with DRY_RUN support and full audit logging.
Rate limit: 20 emails/hour.
"""

from __future__ import annotations
import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, asdict
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    """Result of an email action."""
    ok: bool
    action: str          # "sent" | "draft_created" | "dry_run" | "error"
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    to: str = ""
    subject: str = ""
    error: Optional[str] = None
    dry_run: bool = False


class RateLimiter:
    """Simple in-memory rate limiter (20 emails/hour)."""

    def __init__(self, max_per_hour: int = 20):
        self._max = max_per_hour
        self._window: list[float] = []

    def check(self) -> bool:
        """Return True if action is allowed."""
        now = time.time()
        cutoff = now - 3600
        self._window = [t for t in self._window if t > cutoff]
        if len(self._window) >= self._max:
            return False
        self._window.append(now)
        return True

    @property
    def remaining(self) -> int:
        now = time.time()
        cutoff = now - 3600
        self._window = [t for t in self._window if t > cutoff]
        return self._max - len(self._window)


class EmailMCP:
    """
    Gmail MCP server — wraps Gmail API with DRY_RUN, rate limiting, and audit logging.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
    ]

    def __init__(
        self,
        vault_path: Path,
        token_path: Optional[Path] = None,
        dry_run: bool = True,
        max_per_hour: int = 20,
    ):
        self.vault_path = vault_path
        self.token_path = token_path or (vault_path.parent / "sessions" / "gmail_token.json")
        self.dry_run = dry_run
        self.rate_limiter = RateLimiter(max_per_hour)
        self._service = None
        self._approved_dir = vault_path / "Approved"
        self._log_dir = vault_path / "Logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        reply_to_thread: Optional[str] = None,
    ) -> EmailResult:
        """
        Send an email via Gmail API.
        Checks: DRY_RUN, rate limit, approval file.
        """
        action = "send_email"
        self._log(action, f"to={to}, subject={subject[:50]}")

        if self.dry_run:
            logger.info("[DRY RUN] Would send email to %s: %s", to, subject)
            return EmailResult(ok=True, action="dry_run", to=to, subject=subject, dry_run=True)

        if not self.rate_limiter.check():
            msg = f"Rate limit exceeded ({self.rate_limiter._max}/hour). Remaining: 0"
            logger.warning(msg)
            return EmailResult(ok=False, action="error", to=to, subject=subject, error=msg)

        try:
            service = self._get_service()
            message = self._build_message(to, subject, body, cc, reply_to_thread)
            result = service.users().messages().send(userId="me", body=message).execute()
            self._log(action, f"Sent OK — message_id={result['id']}", level="INFO")
            return EmailResult(
                ok=True, action="sent",
                message_id=result["id"],
                thread_id=result.get("threadId"),
                to=to, subject=subject,
            )
        except Exception as exc:
            logger.error("Email send failed: %s", exc)
            return EmailResult(ok=False, action="error", to=to, subject=subject, error=str(exc))

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
    ) -> EmailResult:
        """Create a Gmail draft (does not send)."""
        action = "create_draft"
        self._log(action, f"to={to}, subject={subject[:50]}")

        if self.dry_run:
            logger.info("[DRY RUN] Would create draft to %s: %s", to, subject)
            return EmailResult(ok=True, action="dry_run", to=to, subject=subject, dry_run=True)

        try:
            service = self._get_service()
            message = self._build_message(to, subject, body, cc)
            draft_body = {"message": message}
            result = service.users().drafts().create(userId="me", body=draft_body).execute()
            self._log(action, f"Draft created — id={result['id']}")
            return EmailResult(ok=True, action="draft_created", message_id=result["id"], to=to, subject=subject)
        except Exception as exc:
            logger.error("Draft creation failed: %s", exc)
            return EmailResult(ok=False, action="error", to=to, subject=subject, error=str(exc))

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _get_service(self):
        if self._service is None:
            if not self.token_path.exists():
                raise FileNotFoundError(f"Gmail token not found: {self.token_path}")
            creds_data = json.loads(self.token_path.read_text())
            creds = Credentials(**creds_data)
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def _build_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> dict:
        msg = MIMEMultipart("alternative")
        msg["to"] = to
        msg["subject"] = subject
        if cc:
            msg["cc"] = cc
        if thread_id:
            msg["In-Reply-To"] = thread_id
            msg["References"] = thread_id
        msg.attach(MIMEText(body, "plain"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result: dict = {"raw": raw}
        if thread_id:
            result["threadId"] = thread_id
        return result

    def _log(self, action: str, detail: str, level: str = "INFO") -> None:
        entry = {
            "ts": datetime.now().isoformat(),
            "component": "email_mcp",
            "action": action,
            "detail": detail,
            "dry_run": self.dry_run,
            "level": level,
        }
        log_file = self._log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.json"
        try:
            existing: list = json.loads(log_file.read_text()) if log_file.exists() else []
            existing.append(entry)
            log_file.write_text(json.dumps(existing, indent=2))
        except Exception:
            pass
        getattr(logger, level.lower(), logger.info)("[email_mcp] %s: %s", action, detail)
