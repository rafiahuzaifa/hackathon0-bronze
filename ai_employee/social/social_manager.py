"""
social/social_manager.py — Unified Social Media Manager
Gold Tier — Panaversity AI Employee Hackathon 2026

One post → all 4 platforms with Claude-adapted content.
Risk assessment, approval routing, and audit logging built in.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "./vault"))
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
RATE_LIMIT_PER_HOUR = 5

PLATFORM_SPECS = {
    "linkedin": {
        "max_chars": 1300,
        "image_size": (1200, 627),
        "tone": "professional thought leadership",
        "hashtags": "3-5 relevant hashtags",
    },
    "twitter": {
        "max_chars": 280,
        "image_size": (1200, 675),
        "tone": "concise and punchy",
        "hashtags": "2-3 hashtags",
    },
    "facebook": {
        "max_chars": 5000,
        "image_size": (1200, 630),
        "tone": "conversational and engaging",
        "hashtags": "optional",
    },
    "instagram": {
        "max_chars": 2200,
        "image_size": (1080, 1080),
        "tone": "visual-first with strong hook",
        "hashtags": "20-30 hashtags at bottom",
    },
}


class SocialMediaManager:
    """
    Unified manager for posting to LinkedIn, Twitter, Facebook, Instagram.

    Flow:
    1. adapt_content_for_platform() — Claude adapts content per platform
    2. assess_risk() — Claude rates content risk (low/medium/high)
    3. post_to_all() — routes to approval queue or posts directly
    """

    def __init__(
        self,
        vault_path: Optional[Path] = None,
        dry_run: Optional[bool] = None,
    ) -> None:
        self.vault_path = vault_path or VAULT_PATH
        self.dry_run = dry_run if dry_run is not None else DRY_RUN
        self._claude = None
        self._hourly_posts: Dict[str, List[float]] = {p: [] for p in PLATFORM_SPECS}

        # Lazy-init watchers
        self._linkedin: Optional[Any] = None
        self._twitter: Optional[Any] = None
        self._facebook: Optional[Any] = None
        self._instagram: Optional[Any] = None

        self._pending_approval_dir = self.vault_path / "Pending_Approval"
        self._done_dir = self.vault_path / "Done"
        self._logs_dir = self.vault_path / "Logs"
        self._failed_dir = self.vault_path / "Failed"
        for d in [self._pending_approval_dir, self._done_dir, self._logs_dir, self._failed_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Claude client
    # ------------------------------------------------------------------

    def _get_claude(self):
        if self._claude:
            return self._claude
        import anthropic
        self._claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        return self._claude

    # ------------------------------------------------------------------
    # Platform watcher accessors (lazy init from env)
    # ------------------------------------------------------------------

    def _get_linkedin(self):
        if self._linkedin is None:
            from watchers.linkedin_watcher import LinkedInWatcher
            self._linkedin = LinkedInWatcher(
                vault_path=self.vault_path,
                dry_run=self.dry_run,
            )
        return self._linkedin

    def _get_twitter(self):
        if self._twitter is None:
            from watchers.twitter_watcher import TwitterWatcher
            self._twitter = TwitterWatcher(
                vault_path=self.vault_path,
                dry_run=self.dry_run,
            )
        return self._twitter

    def _get_facebook(self):
        if self._facebook is None:
            from watchers.facebook_watcher import FacebookWatcher
            self._facebook = FacebookWatcher(
                vault_path=self.vault_path,
                dry_run=self.dry_run,
            )
        return self._facebook

    def _get_instagram(self):
        if self._instagram is None:
            from watchers.instagram_watcher import InstagramWatcher
            self._instagram = InstagramWatcher(
                vault_path=self.vault_path,
                dry_run=self.dry_run,
            )
        return self._instagram

    # ------------------------------------------------------------------
    # 1. adapt_content_for_platform()
    # ------------------------------------------------------------------

    def adapt_content_for_platform(
        self,
        base_content: str,
        platform: str,
        image_path: Optional[str] = None,
    ) -> str:
        """
        Use Claude to adapt content for a specific platform.
        Returns adapted text only.
        """
        spec = PLATFORM_SPECS.get(platform, {})
        max_chars = spec.get("max_chars", 500)
        tone = spec.get("tone", "professional")
        hashtags = spec.get("hashtags", "3-5 hashtags")

        prompt = f"""Adapt this content for {platform.upper()}:

Original: {base_content}

Platform rules:
- {platform.upper()}: {tone.capitalize()} tone. Max {max_chars} chars. {hashtags}.
- LinkedIn: Professional, thought leadership. Start with a hook. End with a question.
- Twitter: Max 280 chars STRICTLY. Punchy. Include CTA. 2-3 hashtags.
- Facebook: Conversational. Emojis welcome. Ask a question at the end.
- Instagram: 150 chars before "more". Strong visual hook. 20-30 hashtags separated by line breaks.

Return ONLY the adapted text, nothing else. No explanations."""

        try:
            claude = self._get_claude()
            resp = claude.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            adapted = resp.content[0].text.strip()
            # Hard enforce char limits for Twitter
            if platform == "twitter" and len(adapted) > 280:
                adapted = adapted[:277] + "..."
            return adapted
        except Exception as exc:
            logger.warning("Claude adapt failed for %s: %s — using original", platform, exc)
            return base_content[:max_chars]

    # ------------------------------------------------------------------
    # 2. assess_risk()
    # ------------------------------------------------------------------

    def assess_risk(self, content: str, platform: str) -> str:
        """
        Use Claude to assess content risk level.
        Returns: "low" | "medium" | "high"
        """
        prompt = f"""Assess the risk of posting this on {platform} for a business account.
Content: {content[:500]}

Risk levels:
- low: general info, educational, safe business content
- medium: promotional, pricing mentions, opinions
- high: controversial, legal claims, sensitive topics, personal info, competitor attacks

Reply with ONLY one word: low, medium, or high"""

        try:
            claude = self._get_claude()
            resp = claude.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            risk = resp.content[0].text.strip().lower()
            return risk if risk in ("low", "medium", "high") else "medium"
        except Exception as exc:
            logger.warning("Claude risk assessment failed: %s — defaulting to medium", exc)
            return "medium"

    # ------------------------------------------------------------------
    # 3. post_to_all()
    # ------------------------------------------------------------------

    def post_to_all(
        self,
        content: str,
        image_path: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        schedule_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Post to all platforms (or specified subset).
        Returns: {"posted": {...}, "pending_approval": [...], "scheduled": [...]}
        """
        if platforms is None:
            platforms = list(PLATFORM_SPECS.keys())

        results: Dict[str, Any] = {"posted": {}, "pending_approval": [], "scheduled": []}

        if schedule_time:
            # Schedule for later
            for platform in platforms:
                adapted = self.adapt_content_for_platform(content, platform, image_path)
                path = self._schedule_post(platform, adapted, image_path, schedule_time)
                results["scheduled"].append({"platform": platform, "file": path.name})
            return results

        for platform in platforms:
            if not self._check_platform_rate_limit(platform):
                continue

            adapted = self.adapt_content_for_platform(content, platform, image_path)
            risk = self.assess_risk(adapted, platform)

            if risk == "high" or self.dry_run:
                file_path = self.create_approval_file(adapted, platform, risk, image_path)
                results["pending_approval"].append({
                    "platform": platform,
                    "file": file_path.name,
                    "risk": risk,
                })
            elif risk == "medium":
                # Create approval file with auto-approve note
                file_path = self.create_approval_file(
                    adapted, platform, risk, image_path, auto_approve_hours=1
                )
                results["pending_approval"].append({
                    "platform": platform,
                    "file": file_path.name,
                    "risk": risk,
                    "auto_approve_hours": 1,
                })
            else:
                # Low risk: post directly
                post_id = self._post_to_platform(platform, adapted, image_path)
                results["posted"][platform] = post_id or "dry_run"
                self._audit_log("SOCIAL_POST", f"Posted to {platform}", {
                    "platform": platform, "post_id": post_id, "risk": risk
                })

        return results

    # ------------------------------------------------------------------
    # 4. create_approval_file()
    # ------------------------------------------------------------------

    def create_approval_file(
        self,
        content: str,
        platform: str,
        risk: str,
        image_path: Optional[str] = None,
        auto_approve_hours: Optional[int] = None,
    ) -> Path:
        """Create APPROVAL_REQUIRED file in vault/Pending_Approval/"""
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"SOCIAL_{platform.upper()}_{ts_str}.md"
        metadata_lines = [
            "---",
            f'source: "social"',
            f'platform: "{platform}"',
            f'risk: "{risk}"',
            f'type: "social_post"',
            f'content: "{content[:200].replace(chr(34), chr(39))}"',
            f'image_path: "{image_path or ""}"',
            f'created_at: "{ts_str}"',
            f'status: "pending_approval"',
        ]
        if auto_approve_hours:
            metadata_lines.append(f'auto_approve_hours: {auto_approve_hours}')
        metadata_lines.append("---")
        frontmatter = "\n".join(metadata_lines)

        body = (
            f"# Approval Required: {platform.upper()} Post\n\n"
            f"**Platform:** {platform.upper()}\n"
            f"**Risk Level:** {risk.upper()}\n"
            + (f"**Auto-approve in:** {auto_approve_hours}h if no action\n"
               if auto_approve_hours else "")
            + f"\n## Content\n\n{content}\n\n"
            + (f"**Image:** {image_path}\n" if image_path else "")
            + "\n---\n_Approve or reject in the dashboard._\n"
        )
        path = self._pending_approval_dir / filename
        path.write_text(f"{frontmatter}\n\n{body}", encoding="utf-8")
        self._audit_log("APPROVAL_CREATED", f"Approval pending: {platform}", {
            "platform": platform, "risk": risk, "file": filename
        })
        return path

    # ------------------------------------------------------------------
    # 5. _post_to_platform()
    # ------------------------------------------------------------------

    def _post_to_platform(
        self, platform: str, content: str, image_path: Optional[str] = None
    ) -> Optional[str]:
        """Dispatch to the appropriate watcher's post method."""
        try:
            if platform == "linkedin":
                w = self._get_linkedin()
                if image_path:
                    return w.post_with_image(content, image_path)
                return w.post_text(content)

            elif platform == "twitter":
                w = self._get_twitter()
                if image_path:
                    return (w.post_with_media(content, image_path) or {}).get("tweet_id")
                return (w.post_tweet(content) or {}).get("tweet_id")

            elif platform == "facebook":
                w = self._get_facebook()
                if image_path:
                    return (w.post_with_image(content, image_path) or {}).get("post_id")
                return w.post_text(content)

            elif platform == "instagram":
                w = self._get_instagram()
                # Instagram requires a URL; if local path, note it
                if image_path and image_path.startswith("http"):
                    return w.create_image_post(image_path, content)
                logger.warning("Instagram requires a public URL — saving to approval queue")
                return None

        except Exception as exc:
            logger.error("Post to %s failed: %s", platform, exc)
            self._save_failed(content, platform, str(exc))
            return None
        return None

    def _schedule_post(
        self,
        platform: str,
        content: str,
        image_path: Optional[str],
        scheduled_time: datetime,
    ) -> Path:
        """Route to watcher's schedule_post method."""
        try:
            if platform == "linkedin":
                return self._get_linkedin().schedule_post(content, scheduled_time, image_path)
            elif platform == "twitter":
                return self._get_twitter().schedule_tweet(content, scheduled_time, image_path)
            elif platform == "facebook":
                return self._get_facebook().schedule_post(content, scheduled_time, image_path)
            elif platform == "instagram":
                image_url = image_path if (image_path and image_path.startswith("http")) else ""
                return self._get_instagram().schedule_post(image_url, content, scheduled_time)
        except Exception as exc:
            logger.error("Schedule to %s failed: %s", platform, exc)

        # Fallback: write generic scheduled file
        scheduled_dir = self.vault_path / "Scheduled"
        scheduled_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{platform.upper()}_{ts_str}.md"
        path = scheduled_dir / filename
        path.write_text(
            f"---\nplatform: {platform}\nscheduled_time: {scheduled_time.isoformat()}\n"
            f"content: \"{content[:200]}\"\nstatus: pending\n---\n\n{content}",
            encoding="utf-8",
        )
        return path

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_analytics(self) -> Dict[str, Any]:
        """Fetch analytics from all platforms."""
        results: Dict[str, Any] = {}
        try:
            li = self._get_linkedin()
            profile = li.get_my_profile()
            results["linkedin"] = {"name": profile.get("name", ""), "urn": profile.get("urn", "")}
        except Exception:
            results["linkedin"] = {}

        try:
            tw = self._get_twitter()
            if tw._client:
                me = tw._client.get_me(user_fields=["public_metrics"])
                if me and me.data:
                    m = me.data.public_metrics or {}
                    results["twitter"] = {
                        "followers": m.get("followers_count", 0),
                        "following": m.get("following_count", 0),
                        "tweet_count": m.get("tweet_count", 0),
                    }
        except Exception:
            results["twitter"] = {}

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_platform_rate_limit(self, platform: str) -> bool:
        now = time.time()
        posts = self._hourly_posts.get(platform, [])
        self._hourly_posts[platform] = [t for t in posts if now - t < 3600]
        if len(self._hourly_posts[platform]) >= RATE_LIMIT_PER_HOUR:
            logger.warning("Rate limit reached for %s", platform)
            return False
        return True

    def _audit_log(self, event: str, message: str, extra: Dict[str, Any]) -> None:
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "message": message,
            "dry_run": self.dry_run,
            **extra,
        }
        log_path = self._logs_dir / "social_manager.jsonl"
        try:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _save_failed(self, content: str, platform: str, error: str) -> None:
        self._failed_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        entry = {"ts": ts_str, "platform": platform, "content": content[:500], "error": error}
        with (self._failed_dir / f"failed_{platform}_{ts_str}.json").open("w") as f:
            json.dump(entry, f, indent=2)
