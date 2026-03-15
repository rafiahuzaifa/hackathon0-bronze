"""
whatsapp_mcp.py — WhatsApp MCP Action Server
Sends WhatsApp messages via Playwright browser session.
DRY_RUN mode supported — no messages sent unless dry_run=False.
"""

from __future__ import annotations
import os
import logging
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_MSG_LENGTH = 4096


@dataclass
class WhatsAppResult:
    ok: bool
    action: str   # "sent" | "dry_run" | "error"
    recipient: str
    message_preview: str
    error: Optional[str] = None
    dry_run: bool = False


class WhatsAppMCP:
    """WhatsApp messaging via Playwright browser automation."""

    def __init__(self, vault_path: Path, dry_run: bool = True):
        self.vault_path = vault_path
        self.dry_run = dry_run
        self._session_path = Path(os.environ.get(
            "WHATSAPP_SESSION_PATH", str(vault_path / "sessions" / "whatsapp")
        ))
        self._browser = None
        self._page = None

    def _get_page(self):
        """Lazy-init Playwright browser with persistent session."""
        if self._page is not None:
            return self._page
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self._session_path),
            headless=os.environ.get("WHATSAPP_HEADLESS", "true").lower() == "true",
            args=["--no-sandbox"],
        )
        self._page = self._browser.new_page()
        self._page.goto("https://web.whatsapp.com")
        # Wait for the app to load (QR scan may be needed first run)
        self._page.wait_for_selector("div[data-testid='chat-list']", timeout=60000)
        return self._page

    def send_message(self, recipient: str, message: str) -> WhatsAppResult:
        """
        Send a WhatsApp message to a contact or group.

        Args:
            recipient: Contact name or phone number (with country code).
            message:   Message text (max 4096 chars).
        """
        preview = message[:80] + ("…" if len(message) > 80 else "")
        if len(message) > MAX_MSG_LENGTH:
            message = message[:MAX_MSG_LENGTH]

        if self.dry_run:
            logger.info("[DRY RUN] Would send WhatsApp to %s: %s", recipient, preview)
            return WhatsAppResult(ok=True, action="dry_run", recipient=recipient,
                                  message_preview=preview, dry_run=True)
        try:
            page = self._get_page()
            # Search for contact
            search = page.locator("div[data-testid='search']")
            search.click()
            search.type(recipient, delay=50)
            time.sleep(1.5)
            # Click first result
            page.locator("div[data-testid='cell-frame-container']").first.click()
            time.sleep(0.8)
            # Type and send message
            msg_box = page.locator("div[data-testid='conversation-compose-box-input']")
            msg_box.click()
            msg_box.type(message, delay=20)
            page.keyboard.press("Enter")
            time.sleep(0.5)
            logger.info("WhatsApp message sent to %s", recipient)
            return WhatsAppResult(ok=True, action="sent", recipient=recipient, message_preview=preview)
        except Exception as exc:
            logger.error("WhatsApp send failed: %s", exc)
            return WhatsAppResult(ok=False, action="error", recipient=recipient,
                                  message_preview=preview, error=str(exc))

    def send_template(self, recipient: str, template_key: str, context: dict) -> WhatsAppResult:
        """Send a pre-defined template message."""
        templates = {
            "pricing": (
                "Hi {name}! Thanks for your interest in our services.\n"
                "Our pricing starts from PKR {price}.\n"
                "Would you like a detailed proposal?"
            ),
            "partnership": (
                "Hi {name}! Thank you for reaching out about a partnership.\n"
                "We'd love to explore this opportunity.\n"
                "Can we schedule a call this week?"
            ),
            "complaint": (
                "Hi {name}, we sincerely apologise for the inconvenience.\n"
                "Our team is looking into this right away.\n"
                "We'll update you within 24 hours."
            ),
            "general": (
                "Hi {name}! Thanks for contacting us.\n"
                "A team member will get back to you shortly."
            ),
        }
        template = templates.get(template_key, templates["general"])
        message = template.format(**{**{"name": recipient, "price": "5,000"}, **context})
        return self.send_message(recipient, message)

    def close(self):
        """Close the Playwright browser session."""
        try:
            if self._browser:
                self._browser.close()
            if hasattr(self, "_pw") and self._pw:
                self._pw.stop()
        except Exception:
            pass
