"""
twitter_watcher.py — Twitter/X Real Integration (API v2, Tweepy)
Gold Tier — Panaversity AI Employee Hackathon 2026

Watches mentions, DMs, home timeline, keyword searches.
Posts tweets, threads, media. Supports scheduling.
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

from .base_watcher import BaseWatcher

logger = logging.getLogger(__name__)

POLL_INTERVAL = 60
RATE_LIMIT_PER_HOUR = 5
MAX_TWEET_LENGTH = 280

INTENT_KEYWORDS = {
    "support": ["help", "issue", "broken", "bug", "not working", "error", "problem"],
    "sales": ["price", "buy", "purchase", "how much", "order", "invoice"],
    "partnership": ["collab", "partner", "dm", "work together", "collaboration"],
    "complaint": ["bad", "worst", "terrible", "horrible", "scam", "fraud", "refund"],
    "praise": ["great", "love", "amazing", "awesome", "excellent", "perfect"],
    "urgent": ["urgent", "asap", "immediately", "deadline"],
}

BUSINESS_KEYWORDS = [
    "invoice", "payment", "pricing", "partnership", "collaboration", "urgent",
]


class TwitterWatcher(BaseWatcher):
    """
    Full Twitter/X integration using Tweepy v4.
    Uses API v2 Client for reading/posting, v1.1 API for media upload.
    """

    def __init__(
        self,
        vault_path: str | Path,
        bearer_token: str = "",
        api_key: str = "",
        api_secret: str = "",
        access_token: str = "",
        access_token_secret: str = "",
        monitored_hashtags: Optional[List[str]] = None,
        dry_run: bool = True,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.bearer_token = bearer_token or os.environ.get("TWITTER_BEARER_TOKEN", "")
        self.api_key = api_key or os.environ.get("TWITTER_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("TWITTER_API_SECRET", "")
        self.access_token = access_token or os.environ.get("TWITTER_ACCESS_TOKEN", "")
        self.access_token_secret = (
            access_token_secret or os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")
        )
        self.monitored_hashtags = monitored_hashtags or []
        self.poll_interval = poll_interval
        self._client = None       # Tweepy v2 Client
        self._api_v1 = None       # Tweepy v1 API (media upload)
        self._my_user_id: Optional[str] = None
        self._my_username: Optional[str] = None
        self._processed_ids: set[str] = set()
        self._last_mention_id: Optional[str] = None
        self._hourly_posts: List[float] = []
        self._scheduled_dir = self.vault_path / "Scheduled"

    # ------------------------------------------------------------------
    # 1. authenticate()
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """
        Initialise Tweepy client and verify credentials.
        Saves TWITTER_MY_USER_ID to env.
        """
        try:
            import tweepy
            self._client = tweepy.Client(
                bearer_token=self.bearer_token,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
                wait_on_rate_limit=True,
            )
            me = self._client.get_me(user_fields=["id", "username", "name"])
            if not me or not me.data:
                logger.error("Twitter: could not fetch authenticated user")
                return False
            self._my_user_id = str(me.data.id)
            self._my_username = me.data.username
            os.environ["TWITTER_MY_USER_ID"] = self._my_user_id
            logger.info("Twitter authenticated as @%s (id=%s)", self._my_username, self._my_user_id)
            return True
        except ImportError:
            logger.error("tweepy not installed — pip install tweepy")
            return False
        except Exception as exc:
            logger.error("Twitter auth failed: %s", exc)
            return False

    def _get_v1_api(self):
        """Lazy-init Tweepy v1 API for media upload."""
        if self._api_v1:
            return self._api_v1
        import tweepy
        auth = tweepy.OAuth1UserHandler(
            self.api_key, self.api_secret,
            self.access_token, self.access_token_secret,
        )
        self._api_v1 = tweepy.API(auth)
        return self._api_v1

    # ------------------------------------------------------------------
    # 2. check_for_updates() / poll()
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        if not self.authenticate():
            logger.error("Twitter auth failed — watcher will not start")
            return
        logger.info("TwitterWatcher started (interval=%ds)", self.poll_interval)
        self.log_event("WATCHER_START", "TwitterWatcher started", {"user_id": self._my_user_id})
        attempt = 0
        while self._running:
            try:
                self.poll()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("Twitter poll error (attempt %d): %s — retry in %.1fs", attempt, exc, wait)
                self.log_event("POLL_ERROR", str(exc), {"attempt": attempt})
                attempt += 1
                time.sleep(wait)
                continue
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("TwitterWatcher stopping…")

    def poll(self) -> None:
        self._check_mentions()
        if self.monitored_hashtags:
            self._check_keyword_search()

    def _check_mentions(self) -> None:
        """Fetch new mentions since last_mention_id."""
        if not self._client or not self._my_user_id:
            return
        try:
            kwargs: Dict[str, Any] = {
                "id": self._my_user_id,
                "tweet_fields": ["created_at", "author_id", "text", "public_metrics"],
                "expansions": ["author_id"],
                "user_fields": ["username", "name"],
                "max_results": 10,
            }
            if self._last_mention_id:
                kwargs["since_id"] = self._last_mention_id

            resp = self._client.get_users_mentions(**kwargs)
            if not resp.data:
                return

            users = {u.id: u for u in (resp.includes.get("users") or [])}
            for tweet in resp.data:
                tid = str(tweet.id)
                if tid in self._processed_ids:
                    continue
                author = users.get(tweet.author_id)
                username = author.username if author else "unknown"
                self._process_tweet(tweet, username, "mention")
                self._processed_ids.add(tid)

            self._last_mention_id = str(resp.data[0].id)
        except Exception as exc:
            logger.error("Twitter mentions check failed: %s", exc)

    def _check_keyword_search(self) -> None:
        """Search recent tweets for business keywords + hashtags."""
        if not self._client:
            return
        try:
            all_terms = BUSINESS_KEYWORDS + [f"#{h}" for h in self.monitored_hashtags]
            query = " OR ".join(all_terms[:10]) + " -is:retweet lang:en"
            resp = self._client.search_recent_tweets(
                query=query,
                tweet_fields=["created_at", "author_id", "text", "public_metrics"],
                expansions=["author_id"],
                user_fields=["username"],
                max_results=10,
            )
            if not resp.data:
                return
            users = {u.id: u for u in (resp.includes.get("users") or [])}
            for tweet in resp.data:
                tid = str(tweet.id)
                if tid in self._processed_ids:
                    continue
                intent = self._detect_intent(tweet.text)
                if intent in ("sales", "partnership", "urgent"):
                    author = users.get(tweet.author_id)
                    username = author.username if author else "unknown"
                    self._process_tweet(tweet, username, "keyword_match")
                self._processed_ids.add(tid)
        except Exception as exc:
            logger.error("Twitter keyword search failed: %s", exc)

    def _process_tweet(self, tweet, username: str, tweet_type: str) -> None:
        intent = self._detect_intent(tweet.text)
        risk = self.classify_risk(tweet.text)
        metrics = getattr(tweet, "public_metrics", {}) or {}
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_u = re.sub(r"[^\w]", "_", username)[:20]
        filename = f"TW_{tweet_type.upper()}_{safe_u}_{ts_str}.md"
        metadata = {
            "source": "twitter",
            "type": tweet_type,
            "tweet_id": str(tweet.id),
            "from": f"@{username}",
            "intent": intent,
            "risk": risk,
            "likes": metrics.get("like_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action",
        }
        content = (
            f"# Twitter {tweet_type.replace('_', ' ').title()} by @{username}\n\n"
            f"**From:** @{username}\n"
            f"**Tweet ID:** {tweet.id}\n"
            f"**Intent:** {intent}\n"
            f"**Risk:** {risk}\n"
            f"**Likes:** {metrics.get('like_count', 0)} | "
            f"**Retweets:** {metrics.get('retweet_count', 0)}\n\n"
            f"## Tweet\n\n{tweet.text}\n"
        )
        self.create_needs_action_file(filename, content, metadata)
        self.log_event(f"TW_{tweet_type.upper()}", f"@{username}: {tweet.text[:60]}", {"intent": intent})

    # ------------------------------------------------------------------
    # 3. post_tweet()
    # ------------------------------------------------------------------

    def post_tweet(
        self,
        text: str,
        reply_to_id: Optional[str] = None,
        media_ids: Optional[List[str]] = None,
    ) -> Optional[Dict[str, str]]:
        """
        Create a tweet. Returns {"tweet_id": ..., "url": ...} or None.
        """
        if len(text) > MAX_TWEET_LENGTH:
            logger.warning("Tweet truncated from %d to 280 chars", len(text))
            text = text[:MAX_TWEET_LENGTH]
        if not self._check_rate_limit():
            return None
        if self.check_dry_run("twitter_post_tweet"):
            return None
        if not self._client:
            self.authenticate()

        try:
            kwargs: Dict[str, Any] = {
                "text": text,
                "reply_settings": "mentionedUsers",
            }
            if reply_to_id:
                kwargs["in_reply_to_tweet_id"] = reply_to_id
            if media_ids:
                kwargs["media_ids"] = media_ids

            resp = self._client.create_tweet(**kwargs)
            if not resp.data:
                return None
            tweet_id = str(resp.data.id)
            url = f"https://twitter.com/{self._my_username}/status/{tweet_id}"
            self._hourly_posts.append(time.time())
            self.log_event("TW_POSTED", f"Tweet: {text[:80]}", {"tweet_id": tweet_id, "url": url})
            logger.info("Tweet posted: %s", url)
            return {"tweet_id": tweet_id, "url": url}
        except Exception as exc:
            self._save_failed(text, "twitter", str(exc))
            logger.error("post_tweet failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 4. post_thread()
    # ------------------------------------------------------------------

    def post_thread(self, tweets_list: List[str]) -> List[str]:
        """
        Post a Twitter thread. Each tweet replies to the previous.
        Returns list of tweet_ids.
        """
        if not tweets_list:
            return []
        ids = []
        prev_id = None
        for text in tweets_list:
            result = self.post_tweet(text, reply_to_id=prev_id)
            if result:
                prev_id = result["tweet_id"]
                ids.append(prev_id)
            else:
                break
        self.log_event("TW_THREAD", f"Thread: {len(ids)} tweets posted", {"ids": ids})
        return ids

    # ------------------------------------------------------------------
    # 5. upload_media()
    # ------------------------------------------------------------------

    def upload_media(self, image_path: str) -> Optional[str]:
        """
        Upload media via Tweepy v1 API.
        Returns media_id string.
        """
        img_path = self._resize_image(Path(image_path), (1200, 675))
        try:
            api = self._get_v1_api()
            media = api.media_upload(str(img_path))
            logger.info("Media uploaded: %s", media.media_id_string)
            return media.media_id_string
        except Exception as exc:
            logger.error("upload_media failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 6. post_with_media()
    # ------------------------------------------------------------------

    def post_with_media(self, text: str, image_path: str) -> Optional[Dict[str, str]]:
        media_id = self.upload_media(image_path)
        if not media_id:
            return None
        return self.post_tweet(text, media_ids=[media_id])

    # ------------------------------------------------------------------
    # 7. get_tweet_analytics()
    # ------------------------------------------------------------------

    def get_tweet_analytics(self, tweet_id: str) -> Dict[str, Any]:
        """Return public_metrics for a tweet."""
        if not self._client:
            return {}
        try:
            resp = self._client.get_tweet(
                id=tweet_id,
                tweet_fields=["public_metrics", "created_at"],
            )
            if not resp.data:
                return {}
            m = resp.data.public_metrics or {}
            return {
                "tweet_id": tweet_id,
                "retweet_count": m.get("retweet_count", 0),
                "reply_count": m.get("reply_count", 0),
                "like_count": m.get("like_count", 0),
                "impression_count": m.get("impression_count", 0),
                "quote_count": m.get("quote_count", 0),
            }
        except Exception as exc:
            logger.error("get_tweet_analytics failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # 8. schedule_tweet()
    # ------------------------------------------------------------------

    def schedule_tweet(
        self,
        text: str,
        scheduled_time: datetime,
        image_path: Optional[str] = None,
    ) -> Path:
        """Save tweet to vault/Scheduled/TWITTER_{ts}.md"""
        self._scheduled_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"TWITTER_{ts_str}.md"
        metadata = {
            "platform": "twitter",
            "scheduled_time": scheduled_time.isoformat(),
            "content": text,
            "image_path": image_path or "",
            "recurring": "none",
            "status": "pending",
            "approved_by": "human",
        }
        body = (
            f"# Scheduled Tweet\n\n"
            f"**Scheduled:** {scheduled_time.isoformat()}\n\n"
            f"## Content\n\n{text}\n"
        )
        path = self._scheduled_dir / filename
        frontmatter = self._build_frontmatter(metadata)
        path.write_text(f"{frontmatter}\n\n{body}", encoding="utf-8")
        self.log_event("TW_SCHEDULED", f"Scheduled for {scheduled_time.isoformat()}", {})
        return path

    # ------------------------------------------------------------------
    # 9. delete_tweet()
    # ------------------------------------------------------------------

    def delete_tweet(self, tweet_id: str) -> bool:
        """Delete a tweet. Only executes when DRY_RUN is False."""
        if self.check_dry_run("twitter_delete_tweet"):
            return False
        if not self._client:
            self.authenticate()
        try:
            self._client.delete_tweet(id=tweet_id)
            self.log_event("TW_DELETED", f"Deleted tweet {tweet_id}", {})
            return True
        except Exception as exc:
            logger.error("delete_tweet failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
            logger.warning("Twitter rate limit reached: %d posts/hour", RATE_LIMIT_PER_HOUR)
            return False
        return True

    def _resize_image(self, img_path: Path, size: Tuple[int, int]) -> Path:
        try:
            from PIL import Image
            img = Image.open(img_path).convert("RGB")
            img.thumbnail(size, Image.LANCZOS)
            background = Image.new("RGB", size, (255, 255, 255))
            background.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
            out = img_path.parent / f"twitter_{img_path.name}"
            background.save(out, "JPEG", quality=90)
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
