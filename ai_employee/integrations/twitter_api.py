"""
integrations/twitter_api.py — Twitter/X Real API Integration
Gold Tier — Panaversity AI Employee Hackathon 2026

Tweepy v4 (API v2) for reading/posting + v1.1 for media upload.
OAuth 1.0a User Context required for tweet creation.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("integrations.twitter")


class TwitterAPI:
    """
    Twitter/X API client:
    - Post tweets / threads / media tweets
    - Monitor mentions with since_id cursor
    - Search recent tweets by keyword
    - Get tweet analytics (public_metrics)
    - Delete tweets
    - Media upload via v1.1 API
    """

    def __init__(self) -> None:
        self.api_key        = os.environ.get("TWITTER_API_KEY", "")
        self.api_secret     = os.environ.get("TWITTER_API_SECRET", "")
        self.access_token   = os.environ.get("TWITTER_ACCESS_TOKEN", "")
        self.access_secret  = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")
        self.bearer_token   = os.environ.get("TWITTER_BEARER_TOKEN", "")
        self.my_user_id     = os.environ.get("TWITTER_MY_USER_ID", "")
        self.dry_run        = os.environ.get("DRY_RUN", "true").lower() == "true"
        self._client        = None   # tweepy.Client (v2)
        self._v1_api        = None   # tweepy.API (v1.1 for media)
        self._since_id: Optional[str] = None

    # ── Lazy init ─────────────────────────────────────────────────────────────

    def _get_client(self):
        if self._client is None:
            try:
                import tweepy
                self._client = tweepy.Client(
                    bearer_token=self.bearer_token,
                    consumer_key=self.api_key,
                    consumer_secret=self.api_secret,
                    access_token=self.access_token,
                    access_token_secret=self.access_secret,
                    wait_on_rate_limit=True,
                )
                # Cache own user ID
                if not self.my_user_id:
                    me = self._client.get_me()
                    if me.data:
                        self.my_user_id = str(me.data.id)
                        os.environ["TWITTER_MY_USER_ID"] = self.my_user_id
                logger.info("Twitter client init, user_id=%s", self.my_user_id)
            except ImportError:
                raise RuntimeError("tweepy not installed — run: pip install tweepy>=4.14.0")
        return self._client

    def _get_v1_api(self):
        if self._v1_api is None:
            try:
                import tweepy
                auth = tweepy.OAuth1UserHandler(
                    self.api_key, self.api_secret,
                    self.access_token, self.access_secret,
                )
                self._v1_api = tweepy.API(auth, wait_on_rate_limit=True)
            except ImportError:
                raise RuntimeError("tweepy not installed")
        return self._v1_api

    # ── Posting ───────────────────────────────────────────────────────────────

    def post_tweet(self, text: str,
                   in_reply_to: Optional[str] = None,
                   media_ids: Optional[List[str]] = None) -> Optional[str]:
        """Post a single tweet. Returns tweet ID."""
        text = text[:280]  # hard cap
        if self.dry_run:
            logger.info("[DRY_RUN] Twitter post_tweet: %s", text[:80])
            return "DRY_RUN_ID"

        client = self._get_client()
        kwargs: Dict[str, Any] = {"text": text}
        if in_reply_to:
            kwargs["in_reply_to_tweet_id"] = in_reply_to
        if media_ids:
            kwargs["media_ids"] = media_ids

        resp = client.create_tweet(**kwargs)
        tweet_id = str(resp.data["id"])
        logger.info("Tweet posted: %s", tweet_id)
        return tweet_id

    def post_thread(self, tweets: List[str]) -> List[str]:
        """Post a thread — each tweet replies to the previous."""
        ids = []
        prev_id = None
        for text in tweets:
            tid = self.post_tweet(text, in_reply_to=prev_id)
            if tid:
                ids.append(tid)
                prev_id = tid
            time.sleep(1)  # avoid rate limits
        return ids

    def upload_media(self, image_path: Path) -> Optional[str]:
        """Upload image via v1.1 API. Returns media_id string."""
        if self.dry_run:
            logger.info("[DRY_RUN] Twitter upload_media: %s", image_path)
            return "DRY_RUN_MEDIA_ID"
        api = self._get_v1_api()
        media = api.media_upload(str(image_path))
        return str(media.media_id)

    def post_with_media(self, text: str, image_path: Path) -> Optional[str]:
        """Upload image then post tweet with media."""
        media_id = self.upload_media(image_path)
        return self.post_tweet(text, media_ids=[media_id] if media_id else None)

    def delete_tweet(self, tweet_id: str) -> bool:
        if self.dry_run:
            logger.info("[DRY_RUN] Twitter delete_tweet: %s", tweet_id)
            return True
        try:
            self._get_client().delete_tweet(tweet_id)
            return True
        except Exception as exc:
            logger.error("delete_tweet failed: %s", exc)
            return False

    # ── Monitoring ────────────────────────────────────────────────────────────

    def get_mentions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch latest @mentions using since_id cursor."""
        if not self.my_user_id:
            try:
                self._get_client()
            except Exception:
                return []
        try:
            client = self._get_client()
            kwargs: Dict[str, Any] = {
                "id": self.my_user_id,
                "max_results": min(limit, 100),
                "tweet_fields": ["created_at", "author_id", "text", "public_metrics"],
                "expansions": ["author_id"],
            }
            if self._since_id:
                kwargs["since_id"] = self._since_id

            resp = client.get_users_mentions(**kwargs)
            tweets = resp.data or []
            if tweets:
                self._since_id = str(tweets[0].id)

            return [
                {
                    "id": str(t.id),
                    "text": t.text,
                    "author_id": str(t.author_id),
                    "created_at": t.created_at.isoformat() if t.created_at else "",
                    "metrics": t.public_metrics or {},
                }
                for t in tweets
            ]
        except Exception as exc:
            logger.warning("get_mentions failed: %s", exc)
            return []

    def search_recent(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search recent tweets matching a query."""
        try:
            client = self._get_client()
            resp = client.search_recent_tweets(
                query=f"{query} -is:retweet lang:en",
                max_results=min(limit, 100),
                tweet_fields=["created_at", "author_id", "public_metrics"],
            )
            return [
                {
                    "id": str(t.id),
                    "text": t.text,
                    "author_id": str(t.author_id),
                    "created_at": t.created_at.isoformat() if t.created_at else "",
                    "metrics": t.public_metrics or {},
                }
                for t in (resp.data or [])
            ]
        except Exception as exc:
            logger.warning("search_recent failed: %s", exc)
            return []

    # ── Analytics ─────────────────────────────────────────────────────────────

    def get_tweet_analytics(self, tweet_id: str) -> Dict[str, Any]:
        try:
            resp = self._get_client().get_tweet(
                tweet_id,
                tweet_fields=["public_metrics", "created_at"],
            )
            if resp.data:
                return {
                    "id": tweet_id,
                    "metrics": resp.data.public_metrics or {},
                    "created_at": resp.data.created_at.isoformat() if resp.data.created_at else "",
                }
        except Exception as exc:
            logger.warning("get_tweet_analytics failed: %s", exc)
        return {}

    def get_profile_analytics(self) -> Dict[str, Any]:
        """Follower/tweet counts for dashboard."""
        try:
            client = self._get_client()
            resp = client.get_user(
                id=self.my_user_id,
                user_fields=["public_metrics", "name", "username"],
            )
            if resp.data:
                return {
                    "name": resp.data.name,
                    "username": f"@{resp.data.username}",
                    **( resp.data.public_metrics or {}),
                }
        except Exception as exc:
            logger.warning("get_profile_analytics failed: %s", exc)
        return {}

    # ── Schedule ──────────────────────────────────────────────────────────────

    def schedule_tweet(self, text: str, scheduled_at: datetime,
                       vault_path: Optional[Path] = None) -> Path:
        import json as _json
        vault = vault_path or Path(os.environ.get("VAULT_PATH", "./vault"))
        sched_dir = vault / "Scheduled"
        sched_dir.mkdir(parents=True, exist_ok=True)
        ts = scheduled_at.strftime("%Y%m%d_%H%M%S")
        dest = sched_dir / f"TWITTER_{ts}.md"
        dest.write_text(
            f"---\nplatform: twitter\ncontent: {_json.dumps(text)}\n"
            f"scheduled_time: \"{scheduled_at.isoformat()}\"\nrecurring: none\n"
            f"status: pending\ncreated_at: \"{datetime.utcnow().isoformat()}\"\n---\n",
            encoding="utf-8",
        )
        return dest


# ── Singleton ─────────────────────────────────────────────────────────────────

_twitter: Optional[TwitterAPI] = None

def get_twitter() -> TwitterAPI:
    global _twitter
    if _twitter is None:
        _twitter = TwitterAPI()
    return _twitter
