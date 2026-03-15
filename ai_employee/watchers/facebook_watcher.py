"""
facebook_watcher.py — Facebook Page Watcher via Graph API
Monitors page mentions, comments, Messenger messages, and page DMs.
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

POLL_INTERVAL = 180
GRAPH_API_BASE = "https://graph.facebook.com/v19.0"

INTENT_KEYWORDS = {
    "sales": ["price", "cost", "buy", "order", "how much", "purchase", "services"],
    "support": ["help", "issue", "problem", "not working", "broken", "complaint"],
    "inquiry": ["available", "info", "details", "more info", "question", "ask"],
    "partnership": ["partner", "collab", "collaboration", "business", "opportunity"],
}

BUSINESS_OPPORTUNITY_INTENTS = frozenset(["sales", "partnership"])


class FacebookWatcher(BaseWatcher):
    """Monitors a Facebook Page for comments, DMs, and mentions."""

    def __init__(
        self,
        vault_path: str | Path,
        page_id: str,
        page_access_token: str,
        dry_run: bool = False,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.page_id = page_id
        self.page_access_token = page_access_token
        self.poll_interval = poll_interval
        self._session = self._build_session()
        self._processed_ids: set[str] = set()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        return session

    def _graph_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p: Dict[str, Any] = {"access_token": self.page_access_token}
        if params:
            p.update(params)
        url = f"{GRAPH_API_BASE}/{path.lstrip('/')}"
        resp = self._session.get(url, params=p, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _graph_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload["access_token"] = self.page_access_token
        url = f"{GRAPH_API_BASE}/{path.lstrip('/')}"
        resp = self._session.post(url, data=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def start(self) -> None:
        self._running = True
        logger.info("FacebookWatcher started (interval=%ds)", self.poll_interval)
        self.log_event("WATCHER_START", "FacebookWatcher started", {"page_id": self.page_id})
        attempt = 0
        while self._running:
            try:
                self.poll()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("Facebook poll error (attempt %d): %s", attempt, exc)
                attempt += 1
                time.sleep(wait)
                continue
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("FacebookWatcher stopping…")

    def poll(self) -> None:
        self._check_post_comments()
        self._check_messenger()

    def _check_post_comments(self) -> None:
        try:
            posts = self._graph_get(f"{self.page_id}/posts", params={"limit": 5})
            for post in posts.get("data", []):
                post_id = post.get("id", "")
                comments = self._graph_get(
                    f"{post_id}/comments",
                    params={"fields": "from,message,created_time"},
                )
                for comment in comments.get("data", []):
                    cid = comment.get("id", "")
                    if cid in self._processed_ids:
                        continue
                    self._process_comment(comment, post_id)
                    self._processed_ids.add(cid)
        except Exception as exc:
            logger.error("FB comments fetch failed: %s", exc)

    def _process_comment(self, comment: Dict[str, Any], post_id: str) -> None:
        from_user = comment.get("from", {}).get("name", "unknown")
        message = comment.get("message", "")
        created = comment.get("created_time", "")
        intent = self._detect_intent(message)
        risk = self.classify_risk(message)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        metadata: Dict[str, Any] = {
            "source": "facebook",
            "type": "comment",
            "post_id": post_id,
            "from": from_user,
            "intent": intent,
            "risk": risk,
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action",
        }
        content = (
            f"# Facebook Comment on Post\n\n"
            f"**From:** {from_user}\n"
            f"**Post ID:** {post_id}\n"
            f"**Intent:** {intent}\n"
            f"**Risk:** {risk}\n\n"
            f"## Comment\n\n{message}\n"
        )
        safe_u = re.sub(r"[^\w]", "_", from_user)[:20]
        filename = f"FB_COMMENT_{safe_u}_{ts_str}.md"
        self.create_needs_action_file(filename, content, metadata)
        self.log_event("FB_COMMENT", f"Comment by {from_user}", {"intent": intent, "risk": risk})

    def _check_messenger(self) -> None:
        try:
            data = self._graph_get(
                f"{self.page_id}/conversations",
                params={"fields": "participants,messages{message,from,created_time}"},
            )
            for conv in data.get("data", []):
                for msg in conv.get("messages", {}).get("data", []):
                    mid = msg.get("id", "")
                    if mid in self._processed_ids:
                        continue
                    self._process_messenger_message(msg)
                    self._processed_ids.add(mid)
        except Exception as exc:
            logger.error("FB Messenger fetch failed: %s", exc)

    def _process_messenger_message(self, msg: Dict[str, Any]) -> None:
        text = msg.get("message", "")
        from_u = msg.get("from", {}).get("name", "unknown")
        created = msg.get("created_time", "")
        intent = self._detect_intent(text)
        risk = self.classify_risk(text)
        is_biz = intent in BUSINESS_OPPORTUNITY_INTENTS
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        metadata: Dict[str, Any] = {
            "source": "facebook_messenger",
            "from": from_u,
            "intent": intent,
            "risk": risk,
            "business_opportunity": is_biz,
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action",
        }
        content = (
            f"# Messenger Message from {from_u}\n\n"
            f"**From:** {from_u}\n"
            f"**Intent:** {intent}\n"
            + ("**Business Opportunity: YES**\n" if is_biz else "")
            + f"\n## Message\n\n{text}\n"
        )
        safe_u = re.sub(r"[^\w]", "_", from_u)[:20]
        filename = f"FB_MSG_{safe_u}_{ts_str}.md"
        self.create_needs_action_file(filename, content, metadata)
        self.log_event("FB_MESSENGER", f"Messenger from {from_u}", {"intent": intent})

    def draft_post(self, content: str, image_url: Optional[str] = None) -> Path:
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        metadata: Dict[str, Any] = {
            "source": "facebook",
            "type": "draft_post",
            "image_url": image_url,
            "status": "pending_approval",
        }
        body = (
            f"# Facebook Draft Post\n\n"
            + (f"**Image:** {image_url}\n\n" if image_url else "")
            + f"## Content\n\n{content}\n\n---\n_Approve to publish._\n"
        )
        filename = f"FB_DRAFT_{ts_str}.md"
        return self.create_pending_approval_file(filename, body, metadata)

    def _detect_intent(self, text: str) -> str:
        lower = text.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return intent
        return "general"
