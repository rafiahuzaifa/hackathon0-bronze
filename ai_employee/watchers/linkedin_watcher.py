"""
linkedin_watcher.py — LinkedIn Real Integration (API v2, OAuth 2.0)
Gold Tier — Panaversity AI Employee Hackathon 2026

Watches inbox, connection requests, post reactions.
Posts text & image content. Supports scheduling.
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

LI_API_BASE = "https://api.linkedin.com/v2"
POLL_INTERVAL = 300
RATE_LIMIT_PER_HOUR = 5

BUSINESS_KEYWORDS = [
    "invoice", "partnership", "pricing", "collaboration",
    "urgent", "proposal", "contract", "payment", "quote",
    "hire", "opportunity", "business",
]

INTENT_KEYWORDS = {
    "hiring": ["job", "position", "role", "opportunity", "career", "hiring", "recruit"],
    "partnership": ["partner", "collab", "collaboration", "business", "proposal"],
    "sales": ["services", "pricing", "quote", "offer", "solution", "product", "invoice"],
    "urgent": ["urgent", "asap", "immediately", "deadline", "emergency"],
    "networking": ["connect", "network", "follow", "profile", "linkedin"],
}


class LinkedInWatcher(BaseWatcher):
    """
    Full LinkedIn integration using API v2 with OAuth 2.0.
    Watches messages, connection requests, post activity.
    Posts text and image content with DRY_RUN guard.
    """

    def __init__(
        self,
        vault_path: str | Path,
        access_token: str = "",
        client_id: str = "",
        client_secret: str = "",
        refresh_token: str = "",
        person_urn: str = "",
        dry_run: bool = True,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.access_token = access_token or os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
        self.client_id = client_id or os.environ.get("LINKEDIN_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("LINKEDIN_CLIENT_SECRET", "")
        self.refresh_token = refresh_token or os.environ.get("LINKEDIN_REFRESH_TOKEN", "")
        self.person_urn = person_urn or os.environ.get("LINKEDIN_PERSON_URN", "")
        self.poll_interval = poll_interval
        self._processed_ids: set[str] = set()
        self._hourly_posts: List[float] = []
        self._session = self._build_session()
        self._scheduled_dir = self.vault_path / "Scheduled"

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=2.0, status_forcelist=[429, 500, 502, 503])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        self._update_auth_header(session)
        return session

    def _update_auth_header(self, session: Optional[requests.Session] = None) -> None:
        s = session or self._session
        s.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202401",
        })

    # ------------------------------------------------------------------
    # 1. authenticate()
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """
        Verify access token. If expired, refresh automatically using
        refresh_token. Saves new token back to environment.

        Returns True if authenticated successfully.
        """
        if not self.access_token:
            logger.error("LinkedIn: LINKEDIN_ACCESS_TOKEN not set")
            return False

        # Test token validity
        try:
            resp = self._session.get(f"{LI_API_BASE}/me", timeout=10)
            if resp.status_code == 401 and self.refresh_token:
                logger.info("LinkedIn token expired — refreshing…")
                return self._refresh_token()
            resp.raise_for_status()
            logger.info("LinkedIn authenticated OK")
            return True
        except requests.HTTPError as exc:
            if exc.response and exc.response.status_code == 401 and self.refresh_token:
                return self._refresh_token()
            logger.error("LinkedIn auth failed: %s", exc)
            return False

    def _refresh_token(self) -> bool:
        """Exchange refresh_token for a new access_token."""
        try:
            resp = requests.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access_token"]
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]
            # Persist to env
            os.environ["LINKEDIN_ACCESS_TOKEN"] = self.access_token
            self._update_auth_header()
            self._save_token_to_env()
            logger.info("LinkedIn token refreshed successfully")
            return True
        except Exception as exc:
            logger.error("LinkedIn token refresh failed: %s", exc)
            return False

    def _save_token_to_env(self) -> None:
        """Write refreshed tokens back to .env file."""
        env_path = Path(os.environ.get("ENV_FILE", ".env"))
        if not env_path.exists():
            return
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
            updated = []
            keys_written = set()
            for line in lines:
                if line.startswith("LINKEDIN_ACCESS_TOKEN="):
                    updated.append(f"LINKEDIN_ACCESS_TOKEN={self.access_token}")
                    keys_written.add("LINKEDIN_ACCESS_TOKEN")
                elif line.startswith("LINKEDIN_REFRESH_TOKEN="):
                    updated.append(f"LINKEDIN_REFRESH_TOKEN={self.refresh_token}")
                    keys_written.add("LINKEDIN_REFRESH_TOKEN")
                else:
                    updated.append(line)
            if "LINKEDIN_ACCESS_TOKEN" not in keys_written:
                updated.append(f"LINKEDIN_ACCESS_TOKEN={self.access_token}")
            env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not update .env: %s", exc)

    # ------------------------------------------------------------------
    # 2. get_my_profile()
    # ------------------------------------------------------------------

    def get_my_profile(self) -> Dict[str, str]:
        """
        Fetch authenticated member's profile and email.
        Saves URN to LINKEDIN_PERSON_URN env var.

        Returns: {"urn": ..., "name": ..., "email": ...}
        """
        try:
            me_resp = self._session.get(
                f"{LI_API_BASE}/me",
                params={"projection": "(id,localizedFirstName,localizedLastName)"},
                timeout=10,
            )
            me_resp.raise_for_status()
            me = me_resp.json()
            person_id = me.get("id", "")
            urn = f"urn:li:person:{person_id}"
            name = f"{me.get('localizedFirstName', '')} {me.get('localizedLastName', '')}".strip()

            email = ""
            try:
                email_resp = self._session.get(
                    f"{LI_API_BASE}/emailAddress",
                    params={"q": "members", "projection": "(elements*(handle~))"},
                    timeout=10,
                )
                email_resp.raise_for_status()
                elements = email_resp.json().get("elements", [])
                if elements:
                    email = elements[0].get("handle~", {}).get("emailAddress", "")
            except Exception:
                pass

            self.person_urn = urn
            os.environ["LINKEDIN_PERSON_URN"] = urn
            logger.info("LinkedIn profile: %s (%s)", name, urn)
            return {"urn": urn, "name": name, "email": email}
        except Exception as exc:
            logger.error("get_my_profile failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # 3. check_for_updates() / poll()
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        if not self.authenticate():
            logger.error("LinkedIn auth failed — watcher will not start")
            return
        if not self.person_urn:
            self.get_my_profile()
        logger.info("LinkedInWatcher started (interval=%ds)", self.poll_interval)
        self.log_event("WATCHER_START", "LinkedInWatcher started", {"urn": self.person_urn})
        attempt = 0
        while self._running:
            try:
                self.poll()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("LinkedIn poll error (attempt %d): %s — retry in %.1fs", attempt, exc, wait)
                self.log_event("POLL_ERROR", str(exc), {"attempt": attempt})
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
        self._check_post_activity()

    def _check_messages(self) -> None:
        """GET /v2/conversations?q=inbox — fetch unread messages."""
        try:
            resp = self._session.get(
                f"{LI_API_BASE}/conversations",
                params={"q": "inbox", "count": 20},
                timeout=15,
            )
            if resp.status_code != 200:
                return
            for conv in resp.json().get("elements", []):
                conv_id = conv.get("entityUrn", "")
                if conv_id in self._processed_ids:
                    continue
                events = conv.get("events", {}).get("elements", [])
                for event in events[:1]:  # latest message only
                    msg_text = (event.get("eventContent", {})
                                .get("com.linkedin.voyager.messaging.event.MessageEvent", {})
                                .get("attributedBody", {}).get("text", ""))
                    sender_urn = event.get("from", {}).get("messagingMember", {}).get("entityUrn", "")
                    sender_name = (event.get("from", {}).get("messagingMember", {})
                                   .get("miniProfile", {}).get("firstName", "Unknown"))
                    if self._has_business_keyword(msg_text):
                        self._create_action_file(
                            item_type="message",
                            item_id=conv_id,
                            sender_name=sender_name,
                            sender_urn=sender_urn,
                            message_text=msg_text,
                        )
                self._processed_ids.add(conv_id)
        except Exception as exc:
            logger.error("LinkedIn messages check failed: %s", exc)

    def _check_connection_requests(self) -> None:
        """GET /v2/invitations?q=pending — fetch pending connection requests."""
        try:
            resp = self._session.get(
                f"{LI_API_BASE}/invitations",
                params={"q": "pendingReceivedInvitations", "count": 10},
                timeout=15,
            )
            if resp.status_code != 200:
                return
            for inv in resp.json().get("elements", []):
                inv_id = inv.get("entityUrn", str(hash(str(inv))))
                if inv_id in self._processed_ids:
                    continue
                from_urn = inv.get("fromMember", {}).get("entityUrn", "")
                from_name = (inv.get("fromMember", {}).get("miniProfile", {})
                             .get("firstName", "Unknown"))
                note = inv.get("message", "")
                self._create_action_file(
                    item_type="connection_request",
                    item_id=inv_id,
                    sender_name=from_name,
                    sender_urn=from_urn,
                    message_text=note,
                )
                self._processed_ids.add(inv_id)
        except Exception as exc:
            logger.debug("LinkedIn invitations check: %s", exc)

    def _check_post_activity(self) -> None:
        """Check comments and reactions on recent posts."""
        if not self.person_urn:
            return
        try:
            resp = self._session.get(
                f"{LI_API_BASE}/ugcPosts",
                params={
                    "q": "authors",
                    "authors": f"List({self.person_urn})",
                    "count": 5,
                },
                timeout=15,
            )
            if resp.status_code != 200:
                return
            for post in resp.json().get("elements", []):
                post_urn = post.get("id", "")
                if not post_urn:
                    continue
                # Check comments
                self._check_post_comments(post_urn)
        except Exception as exc:
            logger.debug("LinkedIn post activity check: %s", exc)

    def _check_post_comments(self, post_urn: str) -> None:
        try:
            resp = self._session.get(
                f"{LI_API_BASE}/socialActions/{requests.utils.quote(post_urn, safe='')}/comments",
                params={"count": 10},
                timeout=15,
            )
            if resp.status_code != 200:
                return
            for comment in resp.json().get("elements", []):
                cid = comment.get("$URN", str(hash(str(comment))))
                if cid in self._processed_ids:
                    continue
                text = comment.get("message", {}).get("text", "")
                author = comment.get("actor", "")
                if self._has_business_keyword(text):
                    intent = self._detect_intent(text)
                    ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    metadata = {
                        "source": "linkedin",
                        "type": "post_comment",
                        "post_urn": post_urn,
                        "comment_id": cid,
                        "intent": intent,
                        "risk": self.classify_risk(text),
                        "status": "needs_action",
                    }
                    content = (
                        f"# LinkedIn Post Comment\n\n"
                        f"**Post URN:** {post_urn}\n"
                        f"**Author:** {author}\n"
                        f"**Intent:** {intent}\n\n"
                        f"## Comment\n\n{text}\n"
                    )
                    filename = f"LINKEDIN_comment_{ts_str}.md"
                    self.create_needs_action_file(filename, content, metadata)
                    self.log_event("LI_COMMENT", f"Post comment: {text[:60]}", {"intent": intent})
                self._processed_ids.add(cid)
        except Exception as exc:
            logger.debug("LinkedIn comment check for %s: %s", post_urn, exc)

    # ------------------------------------------------------------------
    # 4. create_action_file()
    # ------------------------------------------------------------------

    def _create_action_file(
        self,
        item_type: str,
        item_id: str,
        sender_name: str,
        sender_urn: str,
        message_text: str,
    ) -> Path:
        """Write to vault/Needs_Action/LINKEDIN_{type}_{id}.md"""
        intent = self._detect_intent(message_text)
        risk = self.classify_risk(message_text)
        intent_score = self._score_intent(message_text)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_id = re.sub(r"[^\w]", "_", item_id)[:30]
        filename = f"LINKEDIN_{item_type}_{safe_id}_{ts_str}.md"
        metadata = {
            "source": "linkedin",
            "type": item_type,
            "sender_name": sender_name,
            "sender_urn": sender_urn,
            "intent": intent,
            "intent_score": intent_score,
            "risk": risk,
            "timestamp": ts_str,
            "status": "needs_action",
        }
        content = (
            f"# LinkedIn {item_type.replace('_', ' ').title()} from {sender_name}\n\n"
            f"**From:** {sender_name}\n"
            f"**URN:** {sender_urn}\n"
            f"**Intent:** {intent} (score: {intent_score}/10)\n"
            f"**Risk:** {risk}\n\n"
            f"## Message\n\n{message_text or '_(no text)_'}\n"
        )
        path = self.create_needs_action_file(filename, content, metadata)
        self.log_event(
            f"LI_{item_type.upper()}",
            f"{item_type} from {sender_name}",
            {"intent": intent, "score": intent_score, "risk": risk},
        )
        return path

    # ------------------------------------------------------------------
    # 5. post_text()
    # ------------------------------------------------------------------

    def post_text(self, text: str, visibility: str = "PUBLIC") -> Optional[str]:
        """
        POST /v2/ugcPosts — publish a text post.
        Returns post_id or None on DRY_RUN.
        """
        if not self._check_rate_limit():
            return None
        if self.check_dry_run("linkedin_post_text"):
            return None
        if not self.person_urn:
            self.get_my_profile()

        payload = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            },
        }
        try:
            resp = self._session.post(
                f"{LI_API_BASE}/ugcPosts",
                json=payload,
                timeout=20,
            )
            resp.raise_for_status()
            post_id = resp.headers.get("X-RestLi-Id", resp.json().get("id", "unknown"))
            self._hourly_posts.append(time.time())
            self.log_event("LI_POST_TEXT", f"Posted: {text[:80]}", {"post_id": post_id})
            logger.info("LinkedIn post published: %s", post_id)
            return post_id
        except Exception as exc:
            self._save_failed(text, "linkedin", str(exc))
            logger.error("LinkedIn post_text failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 6. post_with_image()
    # ------------------------------------------------------------------

    def post_with_image(self, text: str, image_path: str) -> Optional[str]:
        """
        Upload image to LinkedIn and create a post with it.
        Step 1: Register upload → get uploadUrl + asset URN
        Step 2: PUT binary image to uploadUrl
        Step 3: POST ugcPost with asset URN
        """
        if not self._check_rate_limit():
            return None
        if self.check_dry_run("linkedin_post_with_image"):
            return None
        if not self.person_urn:
            self.get_my_profile()

        img_path = Path(image_path)
        if not img_path.exists():
            logger.error("Image not found: %s", image_path)
            return None

        # Resize image to LinkedIn spec: 1200x627
        img_path = self._resize_image(img_path, (1200, 627))

        try:
            # Step 1: Register upload
            reg_resp = self._session.post(
                f"{LI_API_BASE}/assets?action=registerUpload",
                json={
                    "registerUploadRequest": {
                        "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                        "owner": self.person_urn,
                        "serviceRelationships": [{
                            "relationshipType": "OWNER",
                            "identifier": "urn:li:userGeneratedContent",
                        }],
                    }
                },
                timeout=20,
            )
            reg_resp.raise_for_status()
            reg_data = reg_resp.json()
            upload_url = (reg_data["value"]["uploadMechanism"]
                          ["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
                          ["uploadUrl"])
            asset_urn = reg_data["value"]["asset"]

            # Step 2: Upload binary
            with img_path.open("rb") as f:
                upload_resp = requests.put(
                    upload_url,
                    data=f.read(),
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    timeout=60,
                )
                upload_resp.raise_for_status()

            # Step 3: Create post
            payload = {
                "author": self.person_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": text},
                        "shareMediaCategory": "IMAGE",
                        "media": [{
                            "status": "READY",
                            "description": {"text": text[:200]},
                            "media": asset_urn,
                            "title": {"text": text[:100]},
                        }],
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            }
            post_resp = self._session.post(
                f"{LI_API_BASE}/ugcPosts", json=payload, timeout=20
            )
            post_resp.raise_for_status()
            post_id = post_resp.headers.get("X-RestLi-Id", "unknown")
            self._hourly_posts.append(time.time())
            self.log_event("LI_POST_IMAGE", f"Image post: {text[:60]}", {"post_id": post_id})
            return post_id
        except Exception as exc:
            self._save_failed(text, "linkedin", str(exc))
            logger.error("LinkedIn post_with_image failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 7. get_post_analytics()
    # ------------------------------------------------------------------

    def get_post_analytics(self, post_id: str) -> Dict[str, Any]:
        """
        GET /v2/organizationalEntityShareStatistics — post metrics.
        Returns impressions, clicks, reactions, comments, shares.
        """
        try:
            resp = self._session.get(
                f"{LI_API_BASE}/socialMetadata/{requests.utils.quote(post_id, safe='')}",
                timeout=15,
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()
            return {
                "post_id": post_id,
                "impressions": data.get("totalShareStatistics", {}).get("impressionCount", 0),
                "clicks": data.get("totalShareStatistics", {}).get("clickCount", 0),
                "reactions": data.get("totalShareStatistics", {}).get("likeCount", 0),
                "comments": data.get("totalShareStatistics", {}).get("commentCount", 0),
                "shares": data.get("totalShareStatistics", {}).get("shareCount", 0),
            }
        except Exception as exc:
            logger.error("LinkedIn analytics failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # 8. schedule_post()
    # ------------------------------------------------------------------

    def schedule_post(
        self, text: str, scheduled_time: datetime, image_path: Optional[str] = None
    ) -> Path:
        """Save a scheduled post to vault/Scheduled/LINKEDIN_{ts}.md"""
        self._scheduled_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"LINKEDIN_{ts_str}.md"
        metadata = {
            "platform": "linkedin",
            "scheduled_time": scheduled_time.isoformat(),
            "content": text,
            "image_path": image_path or "",
            "recurring": "none",
            "status": "pending",
            "approved_by": "human",
        }
        body = (
            f"# Scheduled LinkedIn Post\n\n"
            f"**Scheduled:** {scheduled_time.isoformat()}\n\n"
            f"## Content\n\n{text}\n"
        )
        path = self._scheduled_dir / filename
        frontmatter = self._build_frontmatter(metadata)
        path.write_text(f"{frontmatter}\n\n{body}", encoding="utf-8")
        self.log_event("LI_SCHEDULED", f"Scheduled for {scheduled_time.isoformat()}", {})
        return path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _has_business_keyword(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in BUSINESS_KEYWORDS)

    def _detect_intent(self, text: str) -> str:
        lower = text.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return intent
        return "general"

    def _score_intent(self, text: str) -> int:
        lower = text.lower()
        score = 1
        high_value = ["invoice", "payment", "contract", "urgent", "partnership"]
        medium_value = ["pricing", "proposal", "collaboration", "quote"]
        if any(kw in lower for kw in high_value):
            score += 5
        if any(kw in lower for kw in medium_value):
            score += 3
        if len(text) > 200:
            score += 1
        return min(score, 10)

    def _check_rate_limit(self) -> bool:
        now = time.time()
        self._hourly_posts = [t for t in self._hourly_posts if now - t < 3600]
        if len(self._hourly_posts) >= RATE_LIMIT_PER_HOUR:
            logger.warning("LinkedIn rate limit reached: %d posts/hour", RATE_LIMIT_PER_HOUR)
            return False
        return True

    def _resize_image(self, img_path: Path, size: Tuple[int, int]) -> Path:
        """Resize image to platform spec using Pillow."""
        try:
            from PIL import Image
            img = Image.open(img_path)
            img = img.convert("RGB")
            img.thumbnail(size, Image.LANCZOS)
            # Pad to exact size
            background = Image.new("RGB", size, (255, 255, 255))
            offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
            background.paste(img, offset)
            out_path = img_path.parent / f"linkedin_{img_path.name}"
            background.save(out_path, "JPEG", quality=90)
            return out_path
        except ImportError:
            logger.debug("Pillow not installed — using original image")
            return img_path
        except Exception as exc:
            logger.warning("Image resize failed: %s", exc)
            return img_path

    def _save_failed(self, content: str, platform: str, error: str) -> None:
        """Save failed post to vault/Failed/"""
        failed_dir = self.vault_path / "Failed"
        failed_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        entry = {
            "ts": ts_str,
            "platform": platform,
            "content": content[:500],
            "error": error,
        }
        with (failed_dir / f"failed_{platform}_{ts_str}.json").open("w") as f:
            json.dump(entry, f, indent=2)
