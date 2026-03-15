"""
whatsapp_watcher.py — WhatsApp Business Watcher via Playwright
Monitors WhatsApp Web for new messages and creates vault files.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .base_watcher import BaseWatcher

logger = logging.getLogger(__name__)

POLL_INTERVAL = 30

INTENT_KEYWORDS = {
    "pricing": ["price", "cost", "how much", "rate", "charges", "fee", "package"],
    "partnership": ["partner", "collab", "collaboration", "joint venture", "together"],
    "complaint": ["complaint", "unhappy", "refund", "broken", "not working", "problem", "issue"],
    "urgent": ["urgent", "asap", "emergency", "immediately", "right now", "deadline"],
    "inquiry": ["info", "information", "details", "available", "services", "offer"],
}


class WhatsAppWatcher(BaseWatcher):
    """
    Monitors WhatsApp Web via Playwright browser automation.
    Requires an active WhatsApp session (QR scan on first run).
    """

    def __init__(
        self,
        vault_path: str | Path,
        session_path: str,
        dry_run: bool = False,
        headless: bool = True,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.session_path = session_path
        self.headless = headless
        self.poll_interval = poll_interval
        self._page = None
        self._browser = None
        self._pw = None
        self._processed_keys: set[str] = set()

    def _init_browser(self) -> None:
        """Launch Playwright with persistent WhatsApp session."""
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.session_path,
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._page = self._browser.new_page()
        self._page.goto("https://web.whatsapp.com")
        logger.info("Waiting for WhatsApp Web to load…")
        self._page.wait_for_selector("div[data-testid='chat-list']", timeout=90000)
        logger.info("WhatsApp Web loaded.")

    def start(self) -> None:
        self._running = True
        logger.info("WhatsAppWatcher started")
        self.log_event("WATCHER_START", "WhatsAppWatcher started", {})
        try:
            self._init_browser()
        except Exception as exc:
            logger.error("Failed to init WhatsApp browser: %s", exc)
            self._running = False
            return

        attempt = 0
        while self._running:
            try:
                self.poll()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("WhatsApp poll error (attempt %d): %s", attempt, exc)
                attempt += 1
                time.sleep(wait)
                continue
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def poll(self) -> None:
        """Scan unread chat previews and process new messages."""
        if not self._page:
            return
        # Find unread chats (badge with unread count)
        unread_chats = self._page.locator("span[data-testid='icon-unread-count']")
        count = unread_chats.count()
        for i in range(count):
            try:
                chat = unread_chats.nth(i)
                # Click parent chat
                chat.locator("xpath=ancestor::div[@data-testid='cell-frame-container']").click()
                time.sleep(0.5)
                self._process_current_chat()
            except Exception as exc:
                logger.debug("Error processing chat %d: %s", i, exc)

    def _process_current_chat(self) -> None:
        """Extract messages from the open chat and create vault files."""
        if not self._page:
            return
        # Get contact name
        try:
            name = self._page.locator("header span[data-testid='conversation-info-header-chat-title']").text_content(timeout=3000) or "Unknown"
        except Exception:
            name = "Unknown"

        # Get last few messages
        msgs = self._page.locator("div.message-in span.selectable-text")
        count = msgs.count()
        for i in range(max(0, count - 3), count):
            try:
                text = msgs.nth(i).text_content(timeout=2000) or ""
                key = f"{name}:{hash(text)}"
                if key in self._processed_keys:
                    continue
                self._create_vault_entry(name, text)
                self._processed_keys.add(key)
            except Exception:
                pass

    def _create_vault_entry(self, sender: str, text: str) -> None:
        """Create a Needs_Action vault file for a WhatsApp message."""
        intent = self._detect_intent(text)
        risk = self.classify_risk(text)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        metadata: Dict[str, Any] = {
            "source": "whatsapp",
            "from": sender,
            "intent": intent,
            "risk": risk,
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action",
        }
        content = (
            f"# WhatsApp Message from {sender}\n\n"
            f"**From:** {sender}\n"
            f"**Intent:** {intent}\n"
            f"**Risk:** {risk}\n\n"
            f"## Message\n\n{text}\n"
        )
        safe_name = re.sub(r"[^\w]", "_", sender)[:20]
        filename = f"WA_{safe_name}_{ts_str}.md"
        self.create_needs_action_file(filename, content, metadata)
        self.log_event("WA_MESSAGE", f"WhatsApp from {sender}", {"intent": intent, "risk": risk})

    def _detect_intent(self, text: str) -> str:
        lower = text.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return intent
        return "general"
