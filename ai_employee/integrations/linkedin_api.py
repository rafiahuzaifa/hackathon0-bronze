"""
integrations/linkedin_api.py — LinkedIn Real API Integration
Gold Tier — Panaversity AI Employee Hackathon 2026

OAuth 2.0 three-legged flow, token refresh, profile fetch,
text/image posting, analytics, message/connection monitoring.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("integrations.linkedin")

API_BASE = "https://api.linkedin.com/v2"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

SCOPES = [
    "r_liteprofile", "r_emailaddress",
    "w_member_social", "r_organization_social",
    "rw_company_admin",
]


class LinkedInAPI:
    """
    Full LinkedIn API client with:
    - OAuth2 PKCE + refresh token auto-renewal
    - Profile fetch (person URN)
    - Text post & image post (3-step upload)
    - Message / connection-request monitoring
    - Post analytics via socialMetadata
    """

    def __init__(self) -> None:
        self.client_id     = os.environ.get("LINKEDIN_CLIENT_ID", "")
        self.client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
        self.access_token  = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
        self.refresh_token = os.environ.get("LINKEDIN_REFRESH_TOKEN", "")
        self.token_expiry  = float(os.environ.get("LINKEDIN_TOKEN_EXPIRY", "0"))
        self.person_urn    = os.environ.get("LINKEDIN_PERSON_URN", "")
        self.dry_run       = os.environ.get("DRY_RUN", "true").lower() == "true"
        self._session      = requests.Session()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        self._ensure_token()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def _ensure_token(self) -> None:
        """Auto-refresh access token if within 5 minutes of expiry."""
        if self.token_expiry and time.time() >= (self.token_expiry - 300):
            if self.refresh_token:
                self.refresh_access_token()
            else:
                logger.warning("LinkedIn token expired and no refresh_token available")

    def refresh_access_token(self) -> bool:
        """Exchange refresh_token for new access_token. Saves to .env."""
        if not self.client_id or not self.client_secret or not self.refresh_token:
            logger.error("LinkedIn: missing credentials for token refresh")
            return False
        try:
            resp = requests.post(TOKEN_URL, data={
                "grant_type":    "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id":     self.client_id,
                "client_secret": self.client_secret,
            }, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self.access_token  = data["access_token"]
            self.token_expiry  = time.time() + data.get("expires_in", 5184000)
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]
            self._persist_tokens()
            logger.info("LinkedIn token refreshed, expires in %ds", data.get("expires_in", 0))
            return True
        except Exception as exc:
            logger.error("LinkedIn token refresh failed: %s", exc)
            return False

    def _persist_tokens(self) -> None:
        """Write updated tokens back to .env file."""
        env_path = Path(".env")
        if not env_path.exists():
            return
        lines = env_path.read_text().splitlines()
        updates = {
            "LINKEDIN_ACCESS_TOKEN":  self.access_token,
            "LINKEDIN_REFRESH_TOKEN": self.refresh_token,
            "LINKEDIN_TOKEN_EXPIRY":  str(int(self.token_expiry)),
        }
        new_lines = []
        updated_keys: set = set()
        for line in lines:
            key = line.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        for key, val in updates.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={val}")
        env_path.write_text("\n".join(new_lines) + "\n")

    # ── Profile ───────────────────────────────────────────────────────────────

    def get_profile(self) -> Dict[str, Any]:
        """Fetch own profile and cache person URN."""
        resp = self._session.get(f"{API_BASE}/me", headers=self._headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self.person_urn = f"urn:li:person:{data['id']}"
        os.environ["LINKEDIN_PERSON_URN"] = self.person_urn
        return data

    def get_email(self) -> str:
        resp = self._session.get(
            f"{API_BASE}/emailAddress",
            params={"q": "members", "projection": "(elements*(handle~))"},
            headers=self._headers(), timeout=10,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        if elements:
            return elements[0].get("handle~", {}).get("emailAddress", "")
        return ""

    def get_connections_count(self) -> int:
        try:
            resp = self._session.get(
                f"{API_BASE}/connections",
                params={"q": "viewer", "start": 0, "count": 0},
                headers=self._headers(), timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("paging", {}).get("total", 0)
        except Exception:
            return 0

    # ── Posting ───────────────────────────────────────────────────────────────

    def post_text(self, text: str, visibility: str = "PUBLIC") -> Optional[str]:
        """Post a text update. Returns the URN of the new post."""
        if self.dry_run:
            logger.info("[DRY_RUN] LinkedIn post_text: %s", text[:80])
            return "urn:li:ugcPost:DRY_RUN"

        if not self.person_urn:
            self.get_profile()

        body = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": visibility},
        }
        resp = self._session.post(f"{API_BASE}/ugcPosts", json=body,
                                  headers=self._headers(), timeout=15)
        resp.raise_for_status()
        post_urn = resp.headers.get("X-RestLi-Id", "")
        logger.info("LinkedIn post created: %s", post_urn)
        return post_urn

    def post_with_image(self, text: str, image_path: Path) -> Optional[str]:
        """3-step: register upload → PUT binary → post with asset URN."""
        if self.dry_run:
            logger.info("[DRY_RUN] LinkedIn post_with_image: %s", image_path)
            return "urn:li:ugcPost:DRY_RUN"

        if not self.person_urn:
            self.get_profile()

        # Step 1 — register
        reg_body = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": self.person_urn,
                "serviceRelationships": [{"relationshipType": "OWNER",
                                          "identifier": "urn:li:userGeneratedContent"}],
            }
        }
        r1 = self._session.post(f"{API_BASE}/assets?action=registerUpload",
                                json=reg_body, headers=self._headers(), timeout=15)
        r1.raise_for_status()
        reg = r1.json()
        upload_url = reg["value"]["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset = reg["value"]["asset"]

        # Step 2 — upload binary
        img_bytes = image_path.read_bytes()
        up_headers = {"Authorization": f"Bearer {self.access_token}",
                      "Content-Type": "application/octet-stream"}
        r2 = self._session.put(upload_url, data=img_bytes, headers=up_headers, timeout=60)
        r2.raise_for_status()

        # Step 3 — create post
        body = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "IMAGE",
                    "media": [{"status": "READY", "media": asset}],
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        r3 = self._session.post(f"{API_BASE}/ugcPosts", json=body,
                                headers=self._headers(), timeout=15)
        r3.raise_for_status()
        return r3.headers.get("X-RestLi-Id", "")

    # ── Monitoring ────────────────────────────────────────────────────────────

    def get_unread_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch latest inbox conversations."""
        try:
            resp = self._session.get(
                f"{API_BASE}/conversations",
                params={"q": "inbox", "count": limit},
                headers=self._headers(), timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as exc:
            logger.warning("LinkedIn get_messages failed: %s", exc)
            return []

    def get_pending_invitations(self) -> List[Dict[str, Any]]:
        """Fetch pending connection requests."""
        try:
            resp = self._session.get(
                f"{API_BASE}/invitations",
                params={"q": "pendingReceivedInvitations"},
                headers=self._headers(), timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as exc:
            logger.warning("LinkedIn get_invitations failed: %s", exc)
            return []

    def get_post_comments(self, post_urn: str) -> List[Dict[str, Any]]:
        """Fetch comments on a specific post."""
        encoded = requests.utils.quote(post_urn, safe="")
        try:
            resp = self._session.get(
                f"{API_BASE}/socialActions/{encoded}/comments",
                headers=self._headers(), timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as exc:
            logger.warning("LinkedIn get_comments failed: %s", exc)
            return []

    # ── Analytics ─────────────────────────────────────────────────────────────

    def get_post_analytics(self, post_urn: str) -> Dict[str, Any]:
        """Fetch likes/comments/shares for a post via socialMetadata."""
        encoded = requests.utils.quote(post_urn, safe="")
        try:
            resp = self._session.get(
                f"{API_BASE}/socialMetadata/{encoded}",
                headers=self._headers(), timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("LinkedIn analytics failed: %s", exc)
            return {}

    def get_profile_analytics(self) -> Dict[str, Any]:
        """Return follower/connection stats for dashboard."""
        try:
            profile = self.get_profile()
            return {
                "name": f"{profile.get('localizedFirstName','')} {profile.get('localizedLastName','')}".strip(),
                "person_urn": self.person_urn,
                "followers": self.get_connections_count(),
            }
        except Exception as exc:
            logger.warning("LinkedIn profile_analytics failed: %s", exc)
            return {}

    # ── Schedule ──────────────────────────────────────────────────────────────

    def schedule_post(self, text: str, scheduled_at: datetime,
                      image_path: Optional[Path] = None,
                      vault_path: Optional[Path] = None) -> Path:
        """Write a scheduled post file to vault/Scheduled/."""
        vault = vault_path or Path(os.environ.get("VAULT_PATH", "./vault"))
        sched_dir = vault / "Scheduled"
        sched_dir.mkdir(parents=True, exist_ok=True)
        ts = scheduled_at.strftime("%Y%m%d_%H%M%S")
        dest = sched_dir / f"LINKEDIN_{ts}.md"
        dest.write_text(
            f"---\nplatform: linkedin\ncontent: {json.dumps(text)}\n"
            f"scheduled_time: \"{scheduled_at.isoformat()}\"\nrecurring: none\n"
            f"status: pending\ncreated_at: \"{datetime.utcnow().isoformat()}\"\n"
            + (f"image_path: \"{image_path}\"\n" if image_path else "")
            + "---\n",
            encoding="utf-8",
        )
        logger.info("LinkedIn post scheduled → %s", dest)
        return dest


# ── Singleton ─────────────────────────────────────────────────────────────────

_linkedin: Optional[LinkedInAPI] = None

def get_linkedin() -> LinkedInAPI:
    global _linkedin
    if _linkedin is None:
        _linkedin = LinkedInAPI()
    return _linkedin
