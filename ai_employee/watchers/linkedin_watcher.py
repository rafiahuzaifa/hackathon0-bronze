"""
linkedin_watcher.py — LinkedIn Notifications Watcher
Polls LinkedIn API for new messages, connection requests, and post mentions.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base_watcher import BaseWatcher

logger = logging.getLogger(__name__)

POLL_INTERVAL = 300
LI_API_BASE = "https://api.linkedin.com/v2"

INTENT_KEYWORDS = {
    "hiring": ["job", "position", "role", "opportunity", "career", "hiring", "recruit"],
    "partnership": ["partner", "collab", "collaboration", "business", "proposal"],
    "sales": ["services", "pricing", "quote", "offer", "solution", "product"],
    "networking": ["connect", "network", "linkedin", "profile", "follow"],
}


class LinkedInWatcher(BaseWatcher):
    """Monitors LinkedIn for messages and connection requests."""

    def __init__(
        self,
        vault_path: str | Path,
        access_token: str,
        dry_run: bool = False,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.access_token = access_token
        self.poll_interval = poll_interval
        self._processed_ids: set[str] = set()
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        })
        return session

    def start(self) -> None:
        self._running = True
        logger.info("LinkedInWatcher started (interval=%ds)", self.poll_interval)
        self.log_event("WATCHER_START", "LinkedInWatcher started", {})
        attempt = 0
        while self._running:
            try:
                self.poll()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("LinkedIn poll error (attempt %d): %s", attempt, exc)
                attempt += 1
                time.sleep(wait)
                continue
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("LinkedInWatcher stopping…")

    def poll(self) -> None:
        self._check_messages()
        self._check_connection_requests()

    def _check_messages(self) -> None:
        """Fetch recent LinkedIn messages."""
        try:
            resp = self._session.get(
                f"{LI_API_BASE}/messages",
                params={"q": "recipients", "count": 20},
                timeout=15,
            )
            if resp.status_code == 200:
                for msg in resp.json().get("elements", []):
                    mid = msg.get("entityUrn", str(hash(str(msg))))
                    if mid in self._processed_ids:
                        continue
                    self._process_message(msg)
                    self._processed_ids.add(mid)
        except Exception as exc:
            logger.error("LinkedIn messages fetch failed: %s", exc)

    def _process_message(self, msg: dict) -> None:
        text = msg.get("body", {}).get("text", "")
        sender = msg.get("sender", {}).get("miniProfile", {}).get("firstName", "Unknown")
        intent = self._detect_intent(text)
        risk = self.classify_risk(text)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        metadata: Dict[str, Any] = {
            "source": "linkedin",
            "type": "message",
            "from": sender,
            "intent": intent,
            "risk": risk,
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action",
        }
        content = (
            f"# LinkedIn Message from {sender}\n\n"
            f"**From:** {sender}\n"
            f"**Intent:** {intent}\n"
            f"**Risk:** {risk}\n\n"
            f"## Message\n\n{text}\n"
        )
        safe_name = re.sub(r"[^\w]", "_", sender)[:20]
        filename = f"LI_MSG_{safe_name}_{ts_str}.md"
        self.create_needs_action_file(filename, content, metadata)
        self.log_event("LI_MESSAGE", f"LinkedIn message from {sender}", {"intent": intent})

    def _check_connection_requests(self) -> None:
        """Fetch pending connection requests."""
        try:
            resp = self._session.get(
                f"{LI_API_BASE}/invitations",
                params={"q": "invitationType", "invitationType": "CONNECTION", "count": 10},
                timeout=15,
            )
            if resp.status_code == 200:
                for inv in resp.json().get("elements", []):
                    inv_id = inv.get("entityUrn", str(hash(str(inv))))
                    if inv_id in self._processed_ids:
                        continue
                    self._process_connection_request(inv)
                    self._processed_ids.add(inv_id)
        except Exception as exc:
            logger.debug("LinkedIn invitations fetch: %s", exc)

    def _process_connection_request(self, inv: dict) -> None:
        from_name = inv.get("fromMember", {}).get("miniProfile", {}).get("firstName", "Unknown")
        message = inv.get("message", "")
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        metadata: Dict[str, Any] = {
            "source": "linkedin",
            "type": "connection_request",
            "from": from_name,
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action",
        }
        content = (
            f"# LinkedIn Connection Request from {from_name}\n\n"
            f"**From:** {from_name}\n"
            + (f"**Note:** {message}\n" if message else "")
            + f"\n---\nAccept or ignore?\n"
        )
        safe_name = re.sub(r"[^\w]", "_", from_name)[:20]
        filename = f"LI_CONNECT_{safe_name}_{ts_str}.md"
        self.create_needs_action_file(filename, content, metadata)
        self.log_event("LI_CONNECTION_REQUEST", f"Connection request from {from_name}", {})

    def _detect_intent(self, text: str) -> str:
        lower = text.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return intent
        return "general"
