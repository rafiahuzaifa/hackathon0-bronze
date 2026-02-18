"""
WhatsApp Watcher — Monitors WhatsApp Web via Playwright for new messages.
Writes urgent/keyword-matched messages to /Needs_Action as .md files.
"""

import os
import re
import json
import logging
import time
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

import yaml

logger = logging.getLogger("whatsapp_watcher")

# Paths
VAULT_DIR = Path("d:/hackathon0/hackathon/AI_Employee_Vault")
NEEDS_ACTION_DIR = VAULT_DIR / "Needs_Action"
WA_SESSION_DIR = VAULT_DIR / ".wa_session"
WA_PROCESSED_FILE = VAULT_DIR / "wa_processed_ids.txt"

# Keywords that trigger action (Company Handbook Rule #1: be polite on WhatsApp)
URGENT_KEYWORDS = ["urgent", "asap", "emergency", "critical", "deadline", "payment", "invoice"]

NEEDS_ACTION_DIR.mkdir(parents=True, exist_ok=True)
WA_SESSION_DIR.mkdir(parents=True, exist_ok=True)


def load_processed_ids() -> set:
    if not WA_PROCESSED_FILE.exists():
        return set()
    return set(WA_PROCESSED_FILE.read_text(encoding="utf-8").splitlines())


def save_processed_id(msg_id: str):
    with open(WA_PROCESSED_FILE, "a", encoding="utf-8") as f:
        f.write(msg_id + "\n")


def detect_keywords(text: str) -> list:
    """Check message text for urgent keywords."""
    text_lower = text.lower()
    return [kw for kw in URGENT_KEYWORDS if kw in text_lower]


def determine_priority(text: str) -> str:
    keywords = detect_keywords(text)
    if any(k in ["urgent", "emergency", "critical", "asap"] for k in keywords):
        return "urgent"
    if any(k in ["payment", "invoice"] for k in keywords):
        return "high"
    return "normal"


def create_markdown_file(msg_data: dict):
    """Write a WhatsApp message as a markdown file in /Needs_Action."""
    file_name = f"wa_{msg_data['id']}.md"
    file_path = NEEDS_ACTION_DIR / file_name

    if file_path.exists():
        return None

    priority = determine_priority(msg_data.get("text", ""))
    keywords = detect_keywords(msg_data.get("text", ""))

    frontmatter = {
        "type": "whatsapp",
        "from": msg_data.get("sender", "Unknown"),
        "chat": msg_data.get("chat_name", "Unknown"),
        "priority": priority,
        "keywords": keywords if keywords else ["none"],
        "timestamp": msg_data.get("timestamp", datetime.now().isoformat()),
    }

    content = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{msg_data.get('text', '')}"

    file_path.write_text(content, encoding="utf-8")
    logger.info(f"Created WhatsApp markdown: {file_path.name} (priority={priority}, keywords={keywords})")
    return file_path


def scrape_whatsapp_messages(page) -> list:
    """Scrape visible messages from the currently open WhatsApp Web chat."""
    messages = []
    try:
        msg_elements = page.query_selector_all("div.message-in")
        for el in msg_elements:
            try:
                text_el = el.query_selector("span.selectable-text")
                meta_el = el.query_selector("div[data-pre-plain-text]")

                text = text_el.inner_text() if text_el else ""
                meta = meta_el.get_attribute("data-pre-plain-text") if meta_el else ""

                # Parse meta: "[HH:MM, DD/MM/YYYY] Sender Name: "
                sender = "Unknown"
                timestamp = datetime.now().isoformat()
                if meta:
                    match = re.match(r"\[(.+?)\]\s*(.+?):\s*$", meta)
                    if match:
                        timestamp = match.group(1)
                        sender = match.group(2)

                msg_id = f"{hash(f'{sender}_{timestamp}_{text[:50]}')}"

                messages.append({
                    "id": msg_id,
                    "sender": sender,
                    "text": text,
                    "timestamp": timestamp,
                    "chat_name": "Active Chat",
                })
            except Exception:
                continue
    except Exception as e:
        logger.error(f"Error scraping messages: {e}")

    return messages


def run_whatsapp_watcher() -> dict:
    """
    Main entry point for the WhatsApp watcher.
    Returns a status dict with counts.
    """
    if sync_playwright is None:
        logger.warning("Playwright not installed — WhatsApp watcher disabled")
        return {"status": "disabled", "reason": "playwright not installed", "new_messages": 0}

    stats = {"status": "ok", "new_messages": 0, "urgent": 0, "errors": []}
    processed_ids = load_processed_ids()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(WA_SESSION_DIR),
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto("https://web.whatsapp.com", timeout=60000)

            # Wait for WhatsApp to load (QR scan on first run)
            logger.info("Waiting for WhatsApp Web to load (scan QR if first time)...")
            try:
                page.wait_for_selector("div#pane-side", timeout=90000)
            except Exception:
                logger.warning("WhatsApp Web did not load in time — may need QR scan")
                browser.close()
                stats["status"] = "needs_qr_scan"
                return stats

            logger.info("WhatsApp Web loaded. Scraping messages...")

            # Scrape messages from the currently visible chat
            messages = scrape_whatsapp_messages(page)

            for msg in messages:
                msg_id = str(msg["id"])
                if msg_id in processed_ids:
                    continue

                keywords = detect_keywords(msg.get("text", ""))
                if not keywords:
                    continue  # Only process messages with actionable keywords

                result = create_markdown_file(msg)
                if result:
                    save_processed_id(msg_id)
                    stats["new_messages"] += 1
                    if determine_priority(msg.get("text", "")) == "urgent":
                        stats["urgent"] += 1

            browser.close()

    except Exception as e:
        logger.error(f"WhatsApp watcher error: {e}")
        stats["status"] = "error"
        stats["errors"].append(str(e))

    return stats


def simulate_whatsapp_messages() -> dict:
    """
    Simulate WhatsApp messages for testing without a real browser.
    Creates test .md files in /Needs_Action.
    """
    stats = {"status": "simulated", "new_messages": 0, "urgent": 0, "errors": []}
    processed_ids = load_processed_ids()

    test_messages = [
        {
            "id": "wa_sim_001",
            "sender": "Boss",
            "chat_name": "Work Group",
            "text": "URGENT: Need the Q1 report by end of day! This is critical.",
            "timestamp": datetime.now().isoformat(),
        },
        {
            "id": "wa_sim_002",
            "sender": "Vendor Ali",
            "chat_name": "Vendor Ali",
            "text": "Hi, sending the invoice for payment of Rs. 75,000. Please process ASAP.",
            "timestamp": datetime.now().isoformat(),
        },
        {
            "id": "wa_sim_003",
            "sender": "Team Lead",
            "chat_name": "Project Alpha",
            "text": "Deadline for milestone 3 is tomorrow. Please update status.",
            "timestamp": datetime.now().isoformat(),
        },
    ]

    for msg in test_messages:
        msg_id = str(msg["id"])
        if msg_id in processed_ids:
            continue

        result = create_markdown_file(msg)
        if result:
            save_processed_id(msg_id)
            stats["new_messages"] += 1
            if determine_priority(msg.get("text", "")) == "urgent":
                stats["urgent"] += 1

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    print("Running WhatsApp watcher simulation...")
    result = simulate_whatsapp_messages()
    print(f"Result: {json.dumps(result, indent=2)}")
