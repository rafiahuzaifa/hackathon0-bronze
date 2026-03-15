"""
instagram_watcher.py — Instagram Business Watcher via Graph API
Polls for DMs, post comments, story replies, and hashtag matches.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base_watcher import BaseWatcher

logger = logging.getLogger(__name__)

POLL_INTERVAL = 300
GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
MAX_CAPTION_LENGTH = 2200

INTENT_KEYWORDS = {
    "sales": ["price", "cost", "how much", "buy", "order", "dm", "direct"],
    "collab": ["collab", "collaboration", "partnership", "feature", "promote"],
    "support": ["help", "issue", "broken", "problem", "not working"],
    "opportunity": ["brand deal", "sponsorship", "paid", "promote my"],
    "inquiry": ["available", "shipping", "stock", "custom", "info", "details"],
}

BUSINESS_OPPORTUNITY_INTENTS = frozenset(["sales", "collab", "opportunity"])


class InstagramWatcher(BaseWatcher):
    """Monitors Instagram Business Account for DMs, comments, and story replies."""

    def __init__(
        self,
        vault_path: str | Path,
        ig_user_id: str,
        page_access_token: str,
        monitored_hashtags: Optional[List[str]] = None,
        dry_run: bool = False,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.ig_user_id = ig_user_id
        self.page_access_token = page_access_token
        self.monitored_hashtags = monitored_hashtags or []
        self.poll_interval = poll_interval
        self._session = self._build_session()
        self._processed_comment_ids: set[str] = set()
        self._processed_dm_ids: set[str] = set()

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
        resp = self._session.get(f"{GRAPH_API_BASE}/{path.lstrip('/')}", params=p, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _graph_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload["access_token"] = self.page_access_token
        resp = self._session.post(f"{GRAPH_API_BASE}/{path.lstrip('/')}", data=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def start(self) -> None:
        self._running = True
        logger.info("InstagramWatcher started (interval=%ds)", self.poll_interval)
        self.log_event("WATCHER_START", "InstagramWatcher started", {"ig_user_id": self.ig_user_id})
        attempt = 0
        while self._running:
            try:
                self.poll()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("Instagram poll error (attempt %d): %s", attempt, exc)
                attempt += 1
                time.sleep(wait)
                continue
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("InstagramWatcher stopping…")

    def poll(self) -> None:
        self._check_post_comments()
        if self.monitored_hashtags:
            self._check_hashtags()

    def _check_post_comments(self) -> None:
        try:
            media = self._graph_get(
                f"{self.ig_user_id}/media",
                params={"fields": "id,caption", "limit": 10},
            )
            for post in media.get("data", []):
                post_id = post.get("id", "")
                comments = self._graph_get(
                    f"{post_id}/comments",
                    params={"fields": "text,username,timestamp"},
                )
                for comment in comments.get("data", []):
                    cid = comment.get("id", "")
                    if cid in self._processed_comment_ids:
                        continue
                    self._process_comment(comment, post_id)
                    self._processed_comment_ids.add(cid)
        except Exception as exc:
            logger.error("IG comments fetch failed: %s", exc)

    def _process_comment(self, comment: Dict[str, Any], post_id: str) -> None:
        text = comment.get("text", "")
        username = comment.get("username", "unknown")
        intent = self._detect_intent(text)
        risk = self.classify_risk(text)
        is_biz = intent in BUSINESS_OPPORTUNITY_INTENTS
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        metadata: Dict[str, Any] = {
            "source": "instagram",
            "type": "comment",
            "post_id": post_id,
            "username": username,
            "intent": intent,
            "risk": risk,
            "business_opportunity": is_biz,
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action",
        }
        content = (
            f"# Instagram Comment by @{username}\n\n"
            f"**Post ID:** {post_id}\n"
            f"**Username:** @{username}\n"
            f"**Intent:** {intent}\n"
            + ("**Business Opportunity: YES**\n" if is_biz else "")
            + f"\n## Comment\n\n{text}\n"
        )
        safe_u = re.sub(r"[^\w]", "_", username)[:20]
        filename = f"IG_COMMENT_{safe_u}_{ts_str}.md"
        self.create_needs_action_file(filename, content, metadata)
        self.log_event("IG_COMMENT", f"Comment by @{username}", {"intent": intent, "biz": is_biz})

    def _check_hashtags(self) -> None:
        for hashtag in self.monitored_hashtags:
            try:
                ht_data = self._graph_get(
                    "ig_hashtag_search",
                    params={"user_id": self.ig_user_id, "q": hashtag},
                )
                ht_ids = ht_data.get("data", [])
                if not ht_ids:
                    continue
                ht_id = ht_ids[0].get("id", "")
                media = self._graph_get(
                    f"{ht_id}/recent_media",
                    params={"user_id": self.ig_user_id, "fields": "id,caption,permalink,timestamp"},
                )
                for item in media.get("data", []):
                    caption = item.get("caption", "")
                    intent = self._detect_intent(caption)
                    if intent in BUSINESS_OPPORTUNITY_INTENTS:
                        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        metadata: Dict[str, Any] = {
                            "source": "instagram",
                            "type": "hashtag_match",
                            "hashtag": f"#{hashtag}",
                            "permalink": item.get("permalink", ""),
                            "intent": intent,
                            "status": "needs_action",
                        }
                        content = (
                            f"# Instagram Hashtag Match — #{hashtag}\n\n"
                            f"**Intent:** {intent}\n"
                            f"**Post:** {item.get('permalink', '')}\n\n"
                            f"## Caption\n\n{caption}\n"
                        )
                        filename = f"IG_HT_{hashtag[:15]}_{ts_str}.md"
                        self.create_needs_action_file(filename, content, metadata)
                        self.log_event("IG_HASHTAG", f"#{hashtag} match", {"intent": intent})
            except Exception as exc:
                logger.error("IG hashtag search #%s failed: %s", hashtag, exc)

    def draft_post(self, caption: str, image_url: str) -> Path:
        if len(caption) > MAX_CAPTION_LENGTH:
            caption = caption[:MAX_CAPTION_LENGTH]
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        metadata: Dict[str, Any] = {
            "source": "instagram",
            "type": "draft_post",
            "image_url": image_url,
            "status": "pending_approval",
        }
        content = (
            f"# Instagram Draft Post\n\n"
            f"**Image URL:** {image_url}\n\n"
            f"## Caption ({len(caption)}/2200 chars)\n\n{caption}\n\n"
            f"---\n_Approve to publish._\n"
        )
        filename = f"IG_DRAFT_{ts_str}.md"
        return self.create_pending_approval_file(filename, content, metadata)

    def publish_post(self, caption: str, image_url: str) -> Optional[str]:
        if self.check_dry_run("publish_instagram_post"):
            return None
        container = self._graph_post(
            f"{self.ig_user_id}/media",
            {"image_url": image_url, "caption": caption},
        )
        container_id = container.get("id")
        if not container_id:
            raise RuntimeError("Failed to create Instagram media container.")
        result = self._graph_post(
            f"{self.ig_user_id}/media_publish",
            {"creation_id": container_id},
        )
        media_id = result.get("id", "unknown")
        self.log_event("IG_POST_PUBLISHED", f"Post published: {media_id}", {})
        return media_id

    def _detect_intent(self, text: str) -> str:
        lower = text.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return intent
        return "general"
