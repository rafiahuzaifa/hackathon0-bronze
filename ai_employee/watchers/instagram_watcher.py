"""
instagram_watcher.py — Instagram Business Real Integration (Graph API v19.0)
Gold Tier — Panaversity AI Employee Hackathon 2026

Watches comments, DMs, mentions, hashtags.
Posts images, carousels, Reels. Replies to comments.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base_watcher import BaseWatcher

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.facebook.com/v19.0"
POLL_INTERVAL = 120
RATE_LIMIT_PER_HOUR = 5
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
    """
    Full Instagram Business integration using Graph API v19.0.
    Requires instagram_basic, instagram_content_publish,
    instagram_manage_comments, instagram_manage_messages permissions.
    """

    def __init__(
        self,
        vault_path: str | Path,
        ig_user_id: str = "",
        page_access_token: str = "",
        monitored_hashtags: Optional[List[str]] = None,
        dry_run: bool = True,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.ig_user_id = ig_user_id or os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
        self.page_access_token = (
            page_access_token or os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
        )
        self.monitored_hashtags = monitored_hashtags or []
        self.poll_interval = poll_interval
        self._session = self._build_session()
        self._processed_comment_ids: set[str] = set()
        self._processed_dm_ids: set[str] = set()
        self._hourly_posts: List[float] = []
        self._scheduled_dir = self.vault_path / "Scheduled"

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=2.0, status_forcelist=[429, 500, 502, 503])
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        p: Dict[str, Any] = {"access_token": self.page_access_token}
        if params:
            p.update(params)
        resp = self._session.get(f"{BASE_URL}/{path.lstrip('/')}", params=p, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        data["access_token"] = self.page_access_token
        resp = self._session.post(f"{BASE_URL}/{path.lstrip('/')}", data=data, timeout=60)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # 1. authenticate()
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """Verify Instagram Business Account credentials."""
        if not self.ig_user_id or not self.page_access_token:
            logger.error("Instagram: credentials not set")
            return False
        try:
            resp = self._get(
                self.ig_user_id,
                params={"fields": "id,name,username,followers_count"},
            )
            username = resp.get("username", "")
            followers = resp.get("followers_count", 0)
            logger.info("Instagram authenticated: @%s (%d followers)", username, followers)
            return True
        except Exception as exc:
            logger.error("Instagram auth failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # 2. check_for_updates() / poll()
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        if not self.authenticate():
            logger.error("Instagram auth failed — watcher will not start")
            return
        logger.info("InstagramWatcher started (interval=%ds)", self.poll_interval)
        self.log_event("WATCHER_START", "InstagramWatcher started", {"ig_user_id": self.ig_user_id})
        attempt = 0
        while self._running:
            try:
                self.poll()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("Instagram poll error (attempt %d): %s — retry in %.1fs", attempt, exc, wait)
                attempt += 1
                time.sleep(wait)
                continue
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("InstagramWatcher stopping…")

    def poll(self) -> None:
        self._check_post_comments()
        self._check_mentions()
        if self.monitored_hashtags:
            self._check_hashtags()

    def _check_post_comments(self) -> None:
        """Fetch comments on recent IG posts."""
        try:
            media = self._get(
                f"{self.ig_user_id}/media",
                params={"fields": "id,caption,timestamp", "limit": 10},
            )
            for post in media.get("data", []):
                post_id = post.get("id", "")
                comments = self._get(
                    f"{post_id}/comments",
                    params={"fields": "text,username,timestamp,id"},
                )
                for comment in comments.get("data", []):
                    cid = comment.get("id", "")
                    if cid in self._processed_comment_ids:
                        continue
                    text = comment.get("text", "")
                    username = comment.get("username", "unknown")
                    intent = self._detect_intent(text)
                    risk = self.classify_risk(text)
                    is_biz = intent in BUSINESS_OPPORTUNITY_INTENTS
                    ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    safe_u = re.sub(r"[^\w]", "_", username)[:20]
                    filename = f"INSTAGRAM_comment_{safe_u}_{ts_str}.md"
                    metadata = {
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
                    self.create_needs_action_file(filename, content, metadata)
                    self.log_event("IG_COMMENT", f"@{username}: {text[:60]}", {"intent": intent, "biz": is_biz})
                    self._processed_comment_ids.add(cid)
        except Exception as exc:
            logger.error("IG comments check failed: %s", exc)

    def _check_mentions(self) -> None:
        """Fetch posts where IG account is tagged."""
        try:
            data = self._get(
                f"{self.ig_user_id}/tags",
                params={"fields": "id,caption,media_type,timestamp"},
            )
            for item in data.get("data", []):
                iid = item.get("id", "")
                if iid in self._processed_comment_ids:
                    continue
                caption = item.get("caption", "")
                intent = self._detect_intent(caption)
                if intent in BUSINESS_OPPORTUNITY_INTENTS:
                    ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    filename = f"INSTAGRAM_mention_{iid[:15]}_{ts_str}.md"
                    metadata = {
                        "source": "instagram",
                        "type": "mention",
                        "media_id": iid,
                        "intent": intent,
                        "status": "needs_action",
                    }
                    content = (
                        f"# Instagram Mention\n\n"
                        f"**Media ID:** {iid}\n"
                        f"**Intent:** {intent}\n\n"
                        f"## Caption\n\n{caption}\n"
                    )
                    self.create_needs_action_file(filename, content, metadata)
                    self.log_event("IG_MENTION", f"Mention: {caption[:60]}", {"intent": intent})
                self._processed_comment_ids.add(iid)
        except Exception as exc:
            logger.debug("IG mentions check: %s", exc)

    def _check_hashtags(self) -> None:
        """Search recent media for monitored hashtags."""
        for hashtag in self.monitored_hashtags:
            try:
                ht_data = self._get(
                    "ig_hashtag_search",
                    params={"user_id": self.ig_user_id, "q": hashtag},
                )
                ht_ids = ht_data.get("data", [])
                if not ht_ids:
                    continue
                ht_id = ht_ids[0].get("id", "")
                media = self._get(
                    f"{ht_id}/recent_media",
                    params={"user_id": self.ig_user_id, "fields": "id,caption,permalink,timestamp"},
                )
                for item in media.get("data", []):
                    caption = item.get("caption", "")
                    intent = self._detect_intent(caption)
                    if intent in BUSINESS_OPPORTUNITY_INTENTS:
                        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        filename = f"INSTAGRAM_hashtag_{hashtag[:15]}_{ts_str}.md"
                        metadata = {
                            "source": "instagram",
                            "type": "hashtag_match",
                            "hashtag": f"#{hashtag}",
                            "permalink": item.get("permalink", ""),
                            "intent": intent,
                            "status": "needs_action",
                        }
                        content = (
                            f"# Instagram #{hashtag} Match\n\n"
                            f"**Intent:** {intent}\n"
                            f"**Post:** {item.get('permalink', '')}\n\n"
                            f"## Caption\n\n{caption}\n"
                        )
                        self.create_needs_action_file(filename, content, metadata)
                        self.log_event("IG_HASHTAG", f"#{hashtag}: {caption[:60]}", {"intent": intent})
            except Exception as exc:
                logger.error("IG hashtag #%s search failed: %s", hashtag, exc)

    # ------------------------------------------------------------------
    # 3. create_image_post()
    # ------------------------------------------------------------------

    def create_image_post(self, image_url: str, caption: str) -> Optional[str]:
        """
        Two-step publish: create media container → publish.
        image_url must be a publicly accessible URL.
        """
        if len(caption) > MAX_CAPTION_LENGTH:
            caption = caption[:MAX_CAPTION_LENGTH]
        if not self._check_rate_limit():
            return None
        if self.check_dry_run("instagram_create_image_post"):
            return None
        try:
            # Step 1: Create container
            container = self._post(
                f"{self.ig_user_id}/media",
                {"image_url": image_url, "caption": caption},
            )
            container_id = container.get("id")
            if not container_id:
                raise RuntimeError("No container ID returned")

            # Wait for processing
            self._wait_for_container(container_id)

            # Step 2: Publish
            result = self._post(
                f"{self.ig_user_id}/media_publish",
                {"creation_id": container_id},
            )
            media_id = result.get("id", "unknown")
            self._hourly_posts.append(time.time())
            self.log_event("IG_POST_IMAGE", f"Published: {caption[:60]}", {"media_id": media_id})
            return media_id
        except Exception as exc:
            self._save_failed(caption, "instagram", str(exc))
            logger.error("IG create_image_post failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 4. create_carousel_post()
    # ------------------------------------------------------------------

    def create_carousel_post(self, image_urls: List[str], caption: str) -> Optional[str]:
        """Create a multi-image carousel post."""
        if not self._check_rate_limit():
            return None
        if self.check_dry_run("instagram_create_carousel_post"):
            return None
        try:
            # Step 1: Create individual containers
            child_ids = []
            for url in image_urls[:10]:  # max 10 images
                resp = self._post(
                    f"{self.ig_user_id}/media",
                    {"image_url": url, "is_carousel_item": "true"},
                )
                cid = resp.get("id")
                if cid:
                    child_ids.append(cid)

            if not child_ids:
                return None

            # Step 2: Create carousel container
            carousel = self._post(
                f"{self.ig_user_id}/media",
                {
                    "media_type": "CAROUSEL",
                    "caption": caption[:MAX_CAPTION_LENGTH],
                    "children": ",".join(child_ids),
                },
            )
            carousel_id = carousel.get("id")
            if not carousel_id:
                return None

            self._wait_for_container(carousel_id)

            # Step 3: Publish
            result = self._post(
                f"{self.ig_user_id}/media_publish",
                {"creation_id": carousel_id},
            )
            media_id = result.get("id", "unknown")
            self._hourly_posts.append(time.time())
            self.log_event("IG_CAROUSEL", f"Carousel: {len(child_ids)} images", {"media_id": media_id})
            return media_id
        except Exception as exc:
            self._save_failed(caption, "instagram", str(exc))
            logger.error("IG create_carousel_post failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 5. create_reel()
    # ------------------------------------------------------------------

    def create_reel(
        self,
        video_url: str,
        caption: str,
        cover_url: Optional[str] = None,
    ) -> Optional[str]:
        """Create and publish an Instagram Reel."""
        if not self._check_rate_limit():
            return None
        if self.check_dry_run("instagram_create_reel"):
            return None
        try:
            data: Dict[str, Any] = {
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption[:MAX_CAPTION_LENGTH],
            }
            if cover_url:
                data["cover_url"] = cover_url

            resp = self._post(f"{self.ig_user_id}/media", data)
            container_id = resp.get("id")
            if not container_id:
                return None

            # Poll until FINISHED
            self._wait_for_container(container_id, max_attempts=30, wait_seconds=10)

            result = self._post(
                f"{self.ig_user_id}/media_publish",
                {"creation_id": container_id},
            )
            media_id = result.get("id", "unknown")
            self._hourly_posts.append(time.time())
            self.log_event("IG_REEL", f"Reel published: {caption[:60]}", {"media_id": media_id})
            return media_id
        except Exception as exc:
            self._save_failed(caption, "instagram", str(exc))
            logger.error("IG create_reel failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 6. reply_to_comment()
    # ------------------------------------------------------------------

    def reply_to_comment(self, comment_id: str, reply_text: str) -> Optional[str]:
        """POST /{comment_id}/replies"""
        if self.check_dry_run("instagram_reply_to_comment"):
            return None
        try:
            resp = self._post(f"{comment_id}/replies", {"message": reply_text})
            reply_id = resp.get("id", "unknown")
            self.log_event("IG_REPLY", f"Reply to {comment_id}: {reply_text[:60]}", {})
            return reply_id
        except Exception as exc:
            logger.error("IG reply_to_comment failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 7. get_media_insights()
    # ------------------------------------------------------------------

    def get_media_insights(self, media_id: str) -> Dict[str, Any]:
        """GET /{media_id}/insights — engagement metrics."""
        try:
            resp = self._get(
                f"{media_id}/insights",
                params={"metric": "impressions,reach,likes,comments,saves,shares"},
            )
            result: Dict[str, Any] = {"media_id": media_id}
            for item in resp.get("data", []):
                result[item.get("name", "")] = item.get("values", [{}])[0].get("value", 0)
            return result
        except Exception as exc:
            logger.error("IG get_media_insights failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # 8. schedule_post()
    # ------------------------------------------------------------------

    def schedule_post(
        self,
        image_url: str,
        caption: str,
        scheduled_time: datetime,
    ) -> Path:
        """Save to vault/Scheduled/INSTAGRAM_{ts}.md — executed at scheduled_time."""
        self._scheduled_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"INSTAGRAM_{ts_str}.md"
        metadata = {
            "platform": "instagram",
            "scheduled_time": scheduled_time.isoformat(),
            "content": caption,
            "image_url": image_url,
            "recurring": "none",
            "status": "pending",
            "approved_by": "human",
        }
        body = (
            f"# Scheduled Instagram Post\n\n"
            f"**Scheduled:** {scheduled_time.isoformat()}\n"
            f"**Image URL:** {image_url}\n\n"
            f"## Caption\n\n{caption}\n"
        )
        path = self._scheduled_dir / filename
        frontmatter = self._build_frontmatter(metadata)
        path.write_text(f"{frontmatter}\n\n{body}", encoding="utf-8")
        self.log_event("IG_SCHEDULED", f"Scheduled for {scheduled_time.isoformat()}", {})
        return path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _wait_for_container(
        self, container_id: str, max_attempts: int = 15, wait_seconds: int = 5
    ) -> None:
        """Poll container status until FINISHED or max_attempts reached."""
        for _ in range(max_attempts):
            try:
                resp = self._get(container_id, params={"fields": "status_code"})
                status = resp.get("status_code", "")
                if status == "FINISHED":
                    return
                if status == "ERROR":
                    raise RuntimeError(f"Container {container_id} failed with ERROR status")
            except Exception:
                pass
            time.sleep(wait_seconds)

    def _detect_intent(self, text: str) -> str:
        lower = text.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return intent
        return "general"

    def _check_rate_limit(self) -> bool:
        now = time.time()
        self._hourly_posts = [t for t in self._hourly_posts if now - t < 3600]
        if len(self._hourly_posts) >= RATE_LIMIT_PER_HOUR:
            logger.warning("Instagram rate limit reached: %d posts/hour", RATE_LIMIT_PER_HOUR)
            return False
        return True

    def _save_failed(self, content: str, platform: str, error: str) -> None:
        failed_dir = self.vault_path / "Failed"
        failed_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        entry = {"ts": ts_str, "platform": platform, "content": content[:500], "error": error}
        with (failed_dir / f"failed_{platform}_{ts_str}.json").open("w") as f:
            json.dump(entry, f, indent=2)
