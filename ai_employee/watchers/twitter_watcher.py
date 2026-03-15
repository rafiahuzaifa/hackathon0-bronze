"""
twitter_watcher.py — Twitter/X Mentions and DMs Watcher
Uses Tweepy v4 to monitor mentions, DMs, and hashtags.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_watcher import BaseWatcher

logger = logging.getLogger(__name__)

POLL_INTERVAL = 120

INTENT_KEYWORDS = {
    "support": ["help", "issue", "broken", "bug", "not working", "error"],
    "sales": ["price", "buy", "purchase", "how much", "order"],
    "partnership": ["collab", "partner", "dm", "work together"],
    "complaint": ["bad", "worst", "terrible", "horrible", "scam", "fraud"],
    "praise": ["great", "love", "amazing", "awesome", "excellent", "perfect"],
}


class TwitterWatcher(BaseWatcher):
    """Monitors Twitter/X for mentions and direct messages."""

    def __init__(
        self,
        vault_path: str | Path,
        bearer_token: str,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
        monitored_hashtags: Optional[List[str]] = None,
        dry_run: bool = False,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.bearer_token = bearer_token
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.monitored_hashtags = monitored_hashtags or []
        self.poll_interval = poll_interval
        self._client = None
        self._processed_ids: set[str] = set()
        self._last_mention_id: Optional[str] = None

    def _get_client(self):
        if self._client:
            return self._client
        import tweepy
        self._client = tweepy.Client(
            bearer_token=self.bearer_token,
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret,
            wait_on_rate_limit=True,
        )
        return self._client

    def start(self) -> None:
        self._running = True
        logger.info("TwitterWatcher started (interval=%ds)", self.poll_interval)
        self.log_event("WATCHER_START", "TwitterWatcher started", {})
        attempt = 0
        while self._running:
            try:
                self.poll()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("Twitter poll error (attempt %d): %s", attempt, exc)
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
            self._check_hashtags()

    def _check_mentions(self) -> None:
        """Fetch recent mentions of authenticated user."""
        try:
            client = self._get_client()
            me = client.get_me()
            if not me or not me.data:
                return
            user_id = me.data.id
            kwargs: Dict[str, Any] = {
                "id": user_id,
                "tweet_fields": ["created_at", "author_id", "text"],
                "expansions": ["author_id"],
                "user_fields": ["username", "name"],
                "max_results": 20,
            }
            if self._last_mention_id:
                kwargs["since_id"] = self._last_mention_id

            resp = client.get_mentions(**kwargs)
            if not resp.data:
                return

            users = {u.id: u for u in (resp.includes.get("users") or [])}
            for tweet in resp.data:
                if str(tweet.id) in self._processed_ids:
                    continue
                author = users.get(tweet.author_id)
                username = author.username if author else "unknown"
                self._process_mention(tweet, username)
                self._processed_ids.add(str(tweet.id))

            self._last_mention_id = str(resp.data[0].id)
        except Exception as exc:
            logger.error("Twitter mentions fetch failed: %s", exc)

    def _process_mention(self, tweet, username: str) -> None:
        text = tweet.text
        intent = self._detect_intent(text)
        risk = self.classify_risk(text)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        metadata: Dict[str, Any] = {
            "source": "twitter",
            "type": "mention",
            "tweet_id": str(tweet.id),
            "from": f"@{username}",
            "intent": intent,
            "risk": risk,
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action",
        }
        content = (
            f"# Twitter Mention by @{username}\n\n"
            f"**From:** @{username}\n"
            f"**Tweet ID:** {tweet.id}\n"
            f"**Intent:** {intent}\n"
            f"**Risk:** {risk}\n\n"
            f"## Tweet\n\n{text}\n"
        )
        safe_u = re.sub(r"[^\w]", "_", username)[:20]
        filename = f"TW_MENTION_{safe_u}_{ts_str}.md"
        self.create_needs_action_file(filename, content, metadata)
        self.log_event("TW_MENTION", f"Mention by @{username}", {"intent": intent, "risk": risk})

    def _check_hashtags(self) -> None:
        """Search recent tweets for monitored hashtags."""
        try:
            client = self._get_client()
            for hashtag in self.monitored_hashtags:
                query = f"#{hashtag} -is:retweet lang:en"
                resp = client.search_recent_tweets(
                    query=query,
                    tweet_fields=["created_at", "author_id", "text"],
                    max_results=10,
                )
                if not resp.data:
                    continue
                for tweet in resp.data:
                    tid = str(tweet.id)
                    if tid in self._processed_ids:
                        continue
                    intent = self._detect_intent(tweet.text)
                    if intent in ("sales", "support", "partnership"):
                        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        metadata: Dict[str, Any] = {
                            "source": "twitter",
                            "type": "hashtag",
                            "hashtag": f"#{hashtag}",
                            "tweet_id": tid,
                            "intent": intent,
                            "processed": datetime.now(timezone.utc).isoformat(),
                            "status": "needs_action",
                        }
                        content = (
                            f"# Twitter #{hashtag} Match\n\n"
                            f"**Hashtag:** #{hashtag}\n"
                            f"**Intent:** {intent}\n\n"
                            f"## Tweet\n\n{tweet.text}\n"
                        )
                        filename = f"TW_HT_{hashtag[:10]}_{ts_str}.md"
                        self.create_needs_action_file(filename, content, metadata)
                        self.log_event("TW_HASHTAG", f"#{hashtag} match", {"intent": intent})
                    self._processed_ids.add(tid)
        except Exception as exc:
            logger.error("Twitter hashtag search failed: %s", exc)

    def _detect_intent(self, text: str) -> str:
        lower = text.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return intent
        return "general"
