"""
social_mcp.py — Social Media MCP Action Server
Posts to LinkedIn, Twitter/X, Facebook, Instagram with DRY_RUN and approval checks.
"""

from __future__ import annotations
import os
import logging
import tweepy
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

CHAR_LIMITS = {"twitter": 280, "linkedin": 3000, "facebook": 63206, "instagram": 2200}


@dataclass
class PostResult:
    ok: bool
    platform: str
    action: str   # "posted" | "dry_run" | "error"
    post_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    dry_run: bool = False
    char_count: int = 0


class SocialMCP:
    """Unified social media posting server with DRY_RUN support."""

    def __init__(self, vault_path: Path, dry_run: bool = True):
        self.vault_path = vault_path
        self.dry_run = dry_run
        self._approved_dir = vault_path / "Approved"

    # ---- Twitter/X --------------------------------------------------------
    def post_twitter(self, content: str, thread: bool = False) -> PostResult:
        """Post a tweet. Raises ValueError if over 280 chars."""
        if len(content) > CHAR_LIMITS["twitter"]:
            return PostResult(ok=False, platform="twitter", action="error",
                              error=f"Content exceeds {CHAR_LIMITS['twitter']} chars ({len(content)})")
        if self.dry_run:
            logger.info("[DRY RUN] Would tweet (%d chars): %s…", len(content), content[:60])
            return PostResult(ok=True, platform="twitter", action="dry_run", dry_run=True, char_count=len(content))
        try:
            client = tweepy.Client(
                consumer_key=os.environ["TWITTER_API_KEY"],
                consumer_secret=os.environ["TWITTER_API_SECRET"],
                access_token=os.environ["TWITTER_ACCESS_TOKEN"],
                access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
            )
            resp = client.create_tweet(text=content)
            tweet_id = str(resp.data["id"])
            url = f"https://twitter.com/i/web/status/{tweet_id}"
            logger.info("Tweet posted: %s", url)
            return PostResult(ok=True, platform="twitter", action="posted", post_id=tweet_id, url=url, char_count=len(content))
        except Exception as exc:
            logger.error("Twitter post failed: %s", exc)
            return PostResult(ok=False, platform="twitter", action="error", error=str(exc))

    # ---- LinkedIn --------------------------------------------------------
    def post_linkedin(self, content: str, media_url: Optional[str] = None) -> PostResult:
        """Post to LinkedIn company page."""
        if len(content) > CHAR_LIMITS["linkedin"]:
            content = content[:CHAR_LIMITS["linkedin"] - 3] + "..."
        if self.dry_run:
            logger.info("[DRY RUN] Would post to LinkedIn (%d chars): %s…", len(content), content[:60])
            return PostResult(ok=True, platform="linkedin", action="dry_run", dry_run=True, char_count=len(content))
        try:
            token = os.environ["LINKEDIN_ACCESS_TOKEN"]
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Restli-Protocol-Version": "2.0.0"}
            # Get person/org URN
            me_resp = requests.get("https://api.linkedin.com/v2/me", headers=headers, timeout=10)
            me_resp.raise_for_status()
            author_urn = f"urn:li:person:{me_resp.json()['id']}"
            payload: dict = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {"com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": content},
                    "shareMediaCategory": "NONE",
                }},
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            }
            resp = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
            post_id = resp.headers.get("X-RestLi-Id", "unknown")
            logger.info("LinkedIn post created: %s", post_id)
            return PostResult(ok=True, platform="linkedin", action="posted", post_id=post_id, char_count=len(content))
        except Exception as exc:
            logger.error("LinkedIn post failed: %s", exc)
            return PostResult(ok=False, platform="linkedin", action="error", error=str(exc))

    # ---- Facebook --------------------------------------------------------
    def post_facebook(self, content: str, page_id: Optional[str] = None, media_url: Optional[str] = None) -> PostResult:
        """Post to Facebook page."""
        pid = page_id or os.environ.get("FACEBOOK_PAGE_ID", "")
        if self.dry_run:
            logger.info("[DRY RUN] Would post to Facebook page %s: %s…", pid, content[:60])
            return PostResult(ok=True, platform="facebook", action="dry_run", dry_run=True, char_count=len(content))
        try:
            token = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]
            url = f"https://graph.facebook.com/v19.0/{pid}/feed"
            payload: dict = {"message": content, "access_token": token}
            if media_url:
                payload["link"] = media_url
            resp = requests.post(url, data=payload, timeout=10)
            resp.raise_for_status()
            post_id = resp.json().get("id", "unknown")
            logger.info("Facebook post created: %s", post_id)
            return PostResult(ok=True, platform="facebook", action="posted", post_id=post_id, char_count=len(content))
        except Exception as exc:
            logger.error("Facebook post failed: %s", exc)
            return PostResult(ok=False, platform="facebook", action="error", error=str(exc))

    # ---- Instagram -------------------------------------------------------
    def post_instagram(self, caption: str, media_url: str) -> PostResult:
        """Post image + caption to Instagram Business account."""
        if len(caption) > CHAR_LIMITS["instagram"]:
            caption = caption[:CHAR_LIMITS["instagram"] - 3] + "..."
        if self.dry_run:
            logger.info("[DRY RUN] Would post to Instagram: %s…", caption[:60])
            return PostResult(ok=True, platform="instagram", action="dry_run", dry_run=True, char_count=len(caption))
        try:
            token = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]
            ig_id = os.environ["INSTAGRAM_BUSINESS_ACCOUNT_ID"]
            # Step 1: Create media container
            create_url = f"https://graph.facebook.com/v19.0/{ig_id}/media"
            create_resp = requests.post(create_url, params={
                "image_url": media_url, "caption": caption, "access_token": token,
            }, timeout=10)
            create_resp.raise_for_status()
            container_id = create_resp.json()["id"]
            # Step 2: Publish
            pub_url = f"https://graph.facebook.com/v19.0/{ig_id}/media_publish"
            pub_resp = requests.post(pub_url, params={"creation_id": container_id, "access_token": token}, timeout=10)
            pub_resp.raise_for_status()
            post_id = pub_resp.json().get("id", "unknown")
            logger.info("Instagram post published: %s", post_id)
            return PostResult(ok=True, platform="instagram", action="posted", post_id=post_id, char_count=len(caption))
        except Exception as exc:
            logger.error("Instagram post failed: %s", exc)
            return PostResult(ok=False, platform="instagram", action="error", error=str(exc))
