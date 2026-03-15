"""
gmail_watcher.py — Gmail Inbox Watcher
Polls for new emails every 60 seconds using Gmail API.
Creates Needs_Action vault files for each unread email.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_watcher import BaseWatcher

logger = logging.getLogger(__name__)

POLL_INTERVAL = 60
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

WHITELIST_DOMAINS = [
    "gmail.com", "outlook.com", "yahoo.com",
]


class GmailWatcher(BaseWatcher):
    """
    Monitors Gmail inbox for new emails.

    Requires OAuth2 credentials. On first run, a browser window opens for
    authentication. Token is cached at GMAIL_TOKEN_PATH.
    """

    def __init__(
        self,
        vault_path: str | Path,
        credentials_path: str,
        token_path: str,
        dry_run: bool = False,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.poll_interval = poll_interval
        self._service = None
        self._processed_ids: set[str] = set()

    def _get_service(self):
        """Lazy-init Gmail API service with token caching."""
        if self._service:
            return self._service
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        token_path = Path(self.token_path)
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def start(self) -> None:
        self._running = True
        logger.info("GmailWatcher started (interval=%ds)", self.poll_interval)
        self.log_event("WATCHER_START", "GmailWatcher started", {})
        attempt = 0
        while self._running:
            try:
                self.poll()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("Gmail poll error (attempt %d): %s — retrying in %.1fs", attempt, exc, wait)
                self.log_event("POLL_ERROR", str(exc), {"attempt": attempt})
                attempt += 1
                time.sleep(wait)
                continue
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("GmailWatcher stopping…")

    def poll(self) -> None:
        """Fetch unread emails and process new ones."""
        service = self._get_service()
        result = service.users().messages().list(
            userId="me", q="is:unread", maxResults=20
        ).execute()
        messages = result.get("messages", [])
        for msg_ref in messages:
            mid = msg_ref["id"]
            if mid in self._processed_ids:
                continue
            self._process_message(service, mid)
            self._processed_ids.add(mid)

    def _process_message(self, service, msg_id: str) -> None:
        """Fetch full message, extract fields, create vault file."""
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "unknown@example.com")
        date_str = headers.get("Date", "")
        body = self._extract_body(msg.get("payload", {}))
        risk = self.classify_risk(f"{subject} {body}")
        sender_domain = sender.split("@")[-1].rstrip(">") if "@" in sender else "unknown"
        is_known = any(d in sender_domain for d in WHITELIST_DOMAINS)

        metadata: Dict[str, Any] = {
            "source": "gmail",
            "msg_id": msg_id,
            "from": sender,
            "subject": subject,
            "date": date_str,
            "risk": risk,
            "known_sender": is_known,
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action",
        }
        content = (
            f"# Email: {subject}\n\n"
            f"**From:** {sender}\n"
            f"**Date:** {date_str}\n"
            f"**Risk:** {risk}\n\n"
            f"## Body\n\n{body[:3000]}\n"
        )
        safe_subject = "".join(c if c.isalnum() else "_" for c in subject[:30])
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"EMAIL_{ts_str}_{safe_subject}.md"
        self.create_needs_action_file(filename, content, metadata)
        self.log_event("EMAIL_RECEIVED", f"Email from {sender}: {subject}", {"risk": risk})

        # Mark as read
        if not self.dry_run:
            try:
                service.users().messages().modify(
                    userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
                ).execute()
            except Exception:
                pass

    @staticmethod
    def _extract_body(payload: dict) -> str:
        """Recursively extract plain text body from Gmail payload."""
        mime = payload.get("mimeType", "")
        if mime == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            result = GmailWatcher._extract_body(part)
            if result:
                return result
        return ""
