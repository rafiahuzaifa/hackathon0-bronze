"""
facebook_watcher.py — Facebook Page Real Integration (Graph API v19.0)
Gold Tier — Panaversity AI Employee Hackathon 2026

Watches Messenger, post comments, mentions, page likes.
Posts text, image, video. Replies to comments. Supports scheduling.
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

INTENT_KEYWORDS = {
    "sales": ["price", "cost", "buy", "order", "how much", "purchase", "services", "invoice"],
    "support": ["help", "issue", "problem", "not working", "broken", "complaint"],
    "inquiry": ["available", "info", "details", "more info", "question", "ask"],
    "partnership": ["partner", "collab", "collaboration", "business", "opportunity"],
    "payment": ["invoice", "payment", "bill", "charge", "refund"],
}

WATCH_KEYWORDS = ["invoice", "payment", "price", "order", "help", "complaint", "urgent"]


class FacebookWatcher(BaseWatcher):
    """
    Full Facebook Page integration using Graph API v19.0.
    Requires a Page Access Token with pages_manage_posts, pages_read_engagement,
    pages_messaging, pages_show_list permissions.
    """

    def __init__(
        self,
        vault_path: str | Path,
        page_id: str = "",
        page_access_token: str = "",
        app_id: str = "",
        app_secret: str = "",
        dry_run: bool = True,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.page_id = page_id or os.environ.get("FACEBOOK_PAGE_ID", "")
        self.page_access_token = (
            page_access_token or os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
        )
        self.app_id = app_id or os.environ.get("FACEBOOK_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("FACEBOOK_APP_SECRET", "")
        self.poll_interval = poll_interval
        self._session = self._build_session()
        self._processed_ids: set[str] = set()
        self._last_checked: Optional[str] = None
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

    def _post(self, path: str, data: Optional[Dict] = None, files=None) -> Dict[str, Any]:
        d = {"access_token": self.page_access_token}
        if data:
            d.update(data)
        resp = self._session.post(
            f"{BASE_URL}/{path.lstrip('/')}",
            data=d if not files else None,
            json=d if files is None and not any(isinstance(v, bytes) for v in (data or {}).values()) else None,
            files=files,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # 1. authenticate()
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """
        Verify Page Access Token.
        Exchanges for long-lived token if needed (60-day expiry).
        """
        if not self.page_access_token:
            logger.error("Facebook: FACEBOOK_PAGE_ACCESS_TOKEN not set")
            return False
        try:
            resp = self._get("me", params={"fields": "id,name"})
            logger.info("Facebook Page authenticated: %s (id=%s)", resp.get("name"), resp.get("id"))

            # Check token expiry
            if self.app_id and self.app_secret:
                debug = self._get(
                    "debug_token",
                    params={
                        "input_token": self.page_access_token,
                        "access_token": f"{self.app_id}|{self.app_secret}",
                    },
                )
                data = debug.get("data", {})
                if not data.get("is_valid"):
                    logger.warning("Facebook token invalid — exchanging for long-lived…")
                    self._exchange_long_lived_token()
            return True
        except Exception as exc:
            logger.error("Facebook auth failed: %s", exc)
            return False

    def _exchange_long_lived_token(self) -> None:
        """Exchange short-lived token for a 60-day long-lived token."""
        try:
            resp = self._session.get(
                f"{BASE_URL}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "fb_exchange_token": self.page_access_token,
                },
                timeout=15,
            )
            resp.raise_for_status()
            new_token = resp.json().get("access_token", "")
            if new_token:
                self.page_access_token = new_token
                os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = new_token
                logger.info("Facebook long-lived token obtained")
        except Exception as exc:
            logger.error("Facebook token exchange failed: %s", exc)

    # ------------------------------------------------------------------
    # 2. check_for_updates() / poll()
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        if not self.authenticate():
            logger.error("Facebook auth failed — watcher will not start")
            return
        logger.info("FacebookWatcher started (interval=%ds)", self.poll_interval)
        self.log_event("WATCHER_START", "FacebookWatcher started", {"page_id": self.page_id})
        attempt = 0
        while self._running:
            try:
                self.poll()
                self._last_checked = datetime.now(timezone.utc).isoformat()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("Facebook poll error (attempt %d): %s — retry in %.1fs", attempt, exc, wait)
                attempt += 1
                time.sleep(wait)
                continue
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("FacebookWatcher stopping…")

    def poll(self) -> None:
        self._check_messenger()
        self._check_post_comments()
        self._check_page_mentions()

    def _check_messenger(self) -> None:
        """Fetch new Messenger conversations."""
        try:
            data = self._get(
                f"{self.page_id}/conversations",
                params={"fields": "messages{message,from,created_time}", "limit": 10},
            )
            for conv in data.get("data", []):
                for msg in conv.get("messages", {}).get("data", []):
                    mid = msg.get("id", "")
                    if mid in self._processed_ids:
                        continue
                    text = msg.get("message", "")
                    from_u = msg.get("from", {}).get("name", "unknown")
                    if self._has_watch_keyword(text):
                        self._write_vault_item("messenger", mid, from_u, text)
                    self._processed_ids.add(mid)
        except Exception as exc:
            logger.error("FB Messenger check failed: %s", exc)

    def _check_post_comments(self) -> None:
        """Fetch new comments on recent page posts."""
        try:
            feed = self._get(
                f"{self.page_id}/feed",
                params={"fields": "id,message,comments{message,from,created_time}", "limit": 5},
            )
            for post in feed.get("data", []):
                for comment in post.get("comments", {}).get("data", []):
                    cid = comment.get("id", "")
                    if cid in self._processed_ids:
                        continue
                    text = comment.get("message", "")
                    from_u = comment.get("from", {}).get("name", "unknown")
                    self._write_vault_item("comment", cid, from_u, text)
                    self._processed_ids.add(cid)
        except Exception as exc:
            logger.error("FB comments check failed: %s", exc)

    def _check_page_mentions(self) -> None:
        """Fetch page mention tags."""
        try:
            data = self._get(
                f"{self.page_id}/tagged",
                params={"fields": "message,from,created_time", "limit": 5},
            )
            for item in data.get("data", []):
                iid = item.get("id", "")
                if iid in self._processed_ids:
                    continue
                text = item.get("message", "")
                from_u = item.get("from", {}).get("name", "unknown")
                self._write_vault_item("mention", iid, from_u, text)
                self._processed_ids.add(iid)
        except Exception as exc:
            logger.debug("FB mentions check: %s", exc)

    def _write_vault_item(
        self, item_type: str, item_id: str, from_user: str, text: str
    ) -> None:
        intent = self._detect_intent(text)
        risk = self.classify_risk(text)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_u = re.sub(r"[^\w]", "_", from_user)[:20]
        filename = f"FACEBOOK_{item_type}_{safe_u}_{ts_str}.md"
        metadata = {
            "source": "facebook",
            "type": item_type,
            "item_id": item_id,
            "from": from_user,
            "intent": intent,
            "risk": risk,
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action",
        }
        content = (
            f"# Facebook {item_type.title()} from {from_user}\n\n"
            f"**From:** {from_user}\n"
            f"**Intent:** {intent}\n"
            f"**Risk:** {risk}\n\n"
            f"## Message\n\n{text}\n"
        )
        self.create_needs_action_file(filename, content, metadata)
        self.log_event(f"FB_{item_type.upper()}", f"{item_type} from {from_user}", {"intent": intent})

    # ------------------------------------------------------------------
    # 3. post_text()
    # ------------------------------------------------------------------

    def post_text(self, message: str, link: Optional[str] = None) -> Optional[str]:
        """POST /{PAGE_ID}/feed — publish a text post."""
        if not self._check_rate_limit():
            return None
        if self.check_dry_run("facebook_post_text"):
            return None
        try:
            data: Dict[str, Any] = {"message": message}
            if link:
                data["link"] = link
            resp = self._post(f"{self.page_id}/feed", data=data)
            post_id = resp.get("id", "unknown")
            self._hourly_posts.append(time.time())
            self.log_event("FB_POST_TEXT", f"Posted: {message[:80]}", {"post_id": post_id})
            return post_id
        except Exception as exc:
            self._save_failed(message, "facebook", str(exc))
            logger.error("FB post_text failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 4. post_with_image()
    # ------------------------------------------------------------------

    def post_with_image(self, message: str, image_path: str) -> Optional[Dict[str, str]]:
        """Upload photo and publish with caption."""
        if not self._check_rate_limit():
            return None
        if self.check_dry_run("facebook_post_with_image"):
            return None
        img = self._resize_image(Path(image_path), (1200, 630))
        try:
            with img.open("rb") as f:
                resp = self._session.post(
                    f"{BASE_URL}/{self.page_id}/photos",
                    data={"caption": message, "published": "true",
                          "access_token": self.page_access_token},
                    files={"source": f},
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
                photo_id = data.get("id", "unknown")
                post_id = data.get("post_id", "")
                self._hourly_posts.append(time.time())
                self.log_event("FB_POST_IMAGE", f"Image post: {message[:60]}", {"photo_id": photo_id})
                return {"photo_id": photo_id, "post_id": post_id}
        except Exception as exc:
            self._save_failed(message, "facebook", str(exc))
            logger.error("FB post_with_image failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 5. post_with_video()
    # ------------------------------------------------------------------

    def post_with_video(self, message: str, video_path: str) -> Optional[str]:
        """Upload video to Facebook Page."""
        if not self._check_rate_limit():
            return None
        if self.check_dry_run("facebook_post_with_video"):
            return None
        try:
            with Path(video_path).open("rb") as f:
                resp = self._session.post(
                    f"{BASE_URL}/{self.page_id}/videos",
                    data={
                        "description": message,
                        "title": message[:50],
                        "access_token": self.page_access_token,
                    },
                    files={"source": f},
                    timeout=300,
                )
                resp.raise_for_status()
                video_id = resp.json().get("id", "unknown")
                self._hourly_posts.append(time.time())
                self.log_event("FB_POST_VIDEO", f"Video post: {message[:60]}", {"video_id": video_id})
                return video_id
        except Exception as exc:
            self._save_failed(message, "facebook", str(exc))
            logger.error("FB post_with_video failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 6. reply_to_comment()
    # ------------------------------------------------------------------

    def reply_to_comment(self, comment_id: str, reply_text: str) -> Optional[str]:
        """POST /{comment_id}/comments — reply to a comment."""
        if self.check_dry_run("facebook_reply_to_comment"):
            return None
        try:
            resp = self._post(f"{comment_id}/comments", data={"message": reply_text})
            reply_id = resp.get("id", "unknown")
            self.log_event("FB_REPLY", f"Reply to {comment_id}: {reply_text[:60]}", {})
            return reply_id
        except Exception as exc:
            logger.error("FB reply_to_comment failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 7. get_post_insights()
    # ------------------------------------------------------------------

    def get_post_insights(self, post_id: str) -> Dict[str, Any]:
        """GET /{post_id}/insights — post engagement metrics."""
        try:
            resp = self._get(
                f"{post_id}/insights",
                params={"metric": "post_impressions,post_engaged_users,post_reactions_by_type_total"},
            )
            result: Dict[str, Any] = {"post_id": post_id}
            for item in resp.get("data", []):
                name = item.get("name", "")
                values = item.get("values", [{}])
                result[name] = values[-1].get("value", 0) if values else 0
            return result
        except Exception as exc:
            logger.error("FB get_post_insights failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # 8. schedule_post()
    # ------------------------------------------------------------------

    def schedule_post(
        self,
        message: str,
        scheduled_time: datetime,
        image_path: Optional[str] = None,
    ) -> Path:
        """Save to vault/Scheduled/FACEBOOK_{ts}.md"""
        self._scheduled_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        unix_ts = int(scheduled_time.timestamp())
        filename = f"FACEBOOK_{ts_str}.md"
        metadata = {
            "platform": "facebook",
            "scheduled_time": scheduled_time.isoformat(),
            "unix_timestamp": unix_ts,
            "content": message,
            "image_path": image_path or "",
            "recurring": "none",
            "status": "pending",
            "approved_by": "human",
        }
        body = (
            f"# Scheduled Facebook Post\n\n"
            f"**Scheduled:** {scheduled_time.isoformat()}\n\n"
            f"## Content\n\n{message}\n"
        )
        path = self._scheduled_dir / filename
        frontmatter = self._build_frontmatter(metadata)
        path.write_text(f"{frontmatter}\n\n{body}", encoding="utf-8")
        self.log_event("FB_SCHEDULED", f"Scheduled for {scheduled_time.isoformat()}", {})
        return path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _has_watch_keyword(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in WATCH_KEYWORDS)

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
            logger.warning("Facebook rate limit reached: %d posts/hour", RATE_LIMIT_PER_HOUR)
            return False
        return True

    def _resize_image(self, img_path: Path, size: Tuple[int, int]) -> Path:
        try:
            from PIL import Image
            img = Image.open(img_path).convert("RGB")
            img.thumbnail(size, Image.LANCZOS)
            bg = Image.new("RGB", size, (255, 255, 255))
            bg.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
            out = img_path.parent / f"fb_{img_path.name}"
            bg.save(out, "JPEG", quality=90)
            return out
        except Exception:
            return img_path

    def _save_failed(self, content: str, platform: str, error: str) -> None:
        failed_dir = self.vault_path / "Failed"
        failed_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        entry = {"ts": ts_str, "platform": platform, "content": content[:500], "error": error}
        with (failed_dir / f"failed_{platform}_{ts_str}.json").open("w") as f:
            json.dump(entry, f, indent=2)
