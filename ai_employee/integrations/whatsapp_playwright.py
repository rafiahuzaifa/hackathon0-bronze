"""
integrations/whatsapp_playwright.py — WhatsApp Web Automation
Gold Tier — Panaversity AI Employee Hackathon 2026

Uses Playwright (Chromium) to automate WhatsApp Web.
Persistent session stored in WHATSAPP_SESSION_PATH.
Run `playwright install chromium` before first use.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("integrations.whatsapp")

SESSION_PATH  = Path(os.environ.get("WHATSAPP_SESSION_PATH", "./sessions/whatsapp"))
HEADLESS      = os.environ.get("WHATSAPP_HEADLESS", "true").lower() == "true"
DRY_RUN       = os.environ.get("DRY_RUN", "true").lower() == "true"
WA_URL        = "https://web.whatsapp.com"
MAX_MSG_LEN   = 4096


class WhatsAppClient:
    """
    Playwright-based WhatsApp Web client.

    Usage (async):
        client = WhatsAppClient()
        await client.start()          # opens browser, loads session
        await client.send_message("+923001234567", "Hello!")
        msgs = await client.get_unread_messages()
        await client.stop()

    Usage (sync wrapper):
        client = WhatsAppClient()
        client.start_sync()
        client.send_sync("+923001234567", "Hello!")
    """

    def __init__(self) -> None:
        self._browser  = None
        self._context  = None
        self._page     = None
        self._started  = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Launch Chromium and load WhatsApp Web session."""
        from playwright.async_api import async_playwright

        SESSION_PATH.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            user_data_dir=str(SESSION_PATH),
            viewport={"width": 1280, "height": 900},
        )
        self._page = await self._context.new_page()
        await self._page.goto(WA_URL, wait_until="domcontentloaded")

        # Wait for QR or main app
        try:
            await self._page.wait_for_selector(
                'canvas[aria-label="Scan this QR code to link a device"],'
                '[data-testid="default-user"]',
                timeout=30_000,
            )
        except Exception:
            pass  # Already logged in or page loaded differently

        if await self._is_logged_in():
            logger.info("WhatsApp Web: session restored")
        else:
            logger.warning("WhatsApp Web: QR code displayed — scan with phone")
            # Wait up to 120 seconds for QR scan
            await self._page.wait_for_selector(
                '[data-testid="default-user"]', timeout=120_000
            )
            logger.info("WhatsApp Web: authenticated via QR")

        self._started = True

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_pw") and self._pw:
            await self._pw.stop()
        self._started = False

    async def _is_logged_in(self) -> bool:
        try:
            el = await self._page.query_selector('[data-testid="default-user"]')
            return el is not None
        except Exception:
            return False

    # ── Send ──────────────────────────────────────────────────────────────────

    async def send_message(self, phone_or_name: str, text: str) -> bool:
        """Send a message to a contact by phone number or display name."""
        if DRY_RUN:
            logger.info("[DRY_RUN] WhatsApp send to %s: %s", phone_or_name, text[:80])
            return True

        if not self._started:
            await self.start()

        text = text[:MAX_MSG_LEN]

        try:
            # Use new-chat URL for phone numbers
            if phone_or_name.startswith("+") or phone_or_name.replace(" ", "").isdigit():
                number = phone_or_name.replace("+", "").replace(" ", "").replace("-", "")
                await self._page.goto(f"{WA_URL}/send?phone={number}&text=", wait_until="networkidle")
            else:
                # Search by name
                search = await self._page.query_selector('[data-testid="chat-list-search"]')
                if search:
                    await search.click()
                    await search.fill(phone_or_name)
                    await self._page.wait_for_timeout(1500)
                    first = await self._page.query_selector('[data-testid="cell-frame-container"]')
                    if first:
                        await first.click()

            # Type message
            await self._page.wait_for_selector('[data-testid="conversation-compose-box-input"]',
                                               timeout=10_000)
            box = await self._page.query_selector('[data-testid="conversation-compose-box-input"]')
            if box:
                await box.click()
                await box.fill(text)
                await self._page.keyboard.press("Enter")
                await self._page.wait_for_timeout(1000)
                logger.info("WhatsApp message sent to %s", phone_or_name)
                return True
        except Exception as exc:
            logger.error("WhatsApp send_message failed: %s", exc)

        return False

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_unread_messages(self) -> List[Dict[str, Any]]:
        """Scrape unread message badges from the chat list."""
        if not self._started:
            await self.start()

        messages = []
        try:
            # Find all chat items with unread badges
            await self._page.wait_for_selector('[data-testid="chat-list"]', timeout=10_000)
            chats = await self._page.query_selector_all('[data-testid="cell-frame-container"]')

            for chat in chats[:20]:
                try:
                    badge = await chat.query_selector('[data-testid="icon-unread-count"]')
                    if not badge:
                        continue
                    count_el = await chat.query_selector('[aria-label*="unread"]')
                    name_el  = await chat.query_selector('[data-testid="cell-frame-title"]')
                    last_el  = await chat.query_selector('[data-testid="last-msg-status"]')

                    name    = await name_el.inner_text()  if name_el  else "Unknown"
                    last    = await last_el.inner_text()  if last_el  else ""
                    count   = await count_el.inner_text() if count_el else "1"

                    messages.append({
                        "contact": name.strip(),
                        "last_message": last.strip(),
                        "unread_count": int(count.strip()) if count.strip().isdigit() else 1,
                        "timestamp": time.time(),
                    })
                except Exception:
                    continue

        except Exception as exc:
            logger.warning("get_unread_messages failed: %s", exc)

        return messages

    async def get_messages_from(self, contact_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Open a chat and scrape the last N messages."""
        if not self._started:
            await self.start()

        try:
            # Search for contact
            search = await self._page.query_selector('[data-testid="chat-list-search"]')
            if search:
                await search.click()
                await search.fill(contact_name)
                await self._page.wait_for_timeout(1500)
                first = await self._page.query_selector('[data-testid="cell-frame-container"]')
                if first:
                    await first.click()
                    await self._page.wait_for_timeout(1000)

            # Scrape messages
            msgs = await self._page.query_selector_all('[data-testid="msg-container"]')
            results = []
            for msg in msgs[-limit:]:
                try:
                    text_el = await msg.query_selector('[data-testid="msg-text"]')
                    text    = await text_el.inner_text() if text_el else ""
                    # Determine direction
                    class_list = await msg.get_attribute("class") or ""
                    from_me = "message-out" in class_list
                    results.append({
                        "text": text.strip(),
                        "from": "me" if from_me else contact_name,
                        "timestamp": time.time(),
                    })
                except Exception:
                    continue
            return results

        except Exception as exc:
            logger.warning("get_messages_from failed: %s", exc)
            return []

    # ── Sync wrappers ─────────────────────────────────────────────────────────

    def start_sync(self) -> None:
        asyncio.run(self.start())

    def send_sync(self, phone_or_name: str, text: str) -> bool:
        return asyncio.run(self.send_message(phone_or_name, text))

    def get_unread_sync(self) -> List[Dict[str, Any]]:
        return asyncio.run(self.get_unread_messages())


# ── Install helper ────────────────────────────────────────────────────────────

def ensure_playwright_installed() -> bool:
    """Install Playwright Chromium if not present. Call once at startup."""
    import subprocess, sys
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        logger.info("Installing Playwright Chromium...")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info("Playwright Chromium installed")
            return True
        logger.error("Playwright install failed: %s", result.stderr)
        return False


# ── Singleton ─────────────────────────────────────────────────────────────────

_whatsapp: Optional[WhatsAppClient] = None

def get_whatsapp() -> WhatsAppClient:
    global _whatsapp
    if _whatsapp is None:
        _whatsapp = WhatsAppClient()
    return _whatsapp
