"""
social/scheduler.py — Post Scheduler using APScheduler
Gold Tier — Panaversity AI Employee Hackathon 2026

Reads vault/Scheduled/ every 60 seconds.
Executes posts at scheduled_time.
Handles recurring posts, approval expirations.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "./vault"))
SCHEDULED_FOLDER = VAULT_PATH / "Scheduled"
CANCELLED_FOLDER = VAULT_PATH / "Cancelled"
FAILED_FOLDER = VAULT_PATH / "Failed"
DONE_FOLDER = VAULT_PATH / "Done"
PENDING_APPROVAL_FOLDER = VAULT_PATH / "Pending_Approval"
LOGS_FOLDER = VAULT_PATH / "Logs"


def _parse_frontmatter(text: str) -> Dict[str, Any]:
    """Parse YAML-ish frontmatter between --- markers."""
    meta: Dict[str, Any] = {}
    if not text.startswith("---"):
        return meta
    parts = text.split("---", 2)
    if len(parts) < 3:
        return meta
    for line in parts[1].splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            v = val.strip().strip('"').strip("'")
            # Parse booleans and numbers
            if v.lower() == "true":
                meta[key.strip()] = True
            elif v.lower() == "false":
                meta[key.strip()] = False
            else:
                try:
                    meta[key.strip()] = int(v)
                except ValueError:
                    meta[key.strip()] = v
    return meta


def _update_frontmatter_status(file_path: Path, status: str, extra: Optional[Dict] = None) -> None:
    """Update the 'status' field in frontmatter in-place."""
    try:
        text = file_path.read_text(encoding="utf-8")
        text = re.sub(r'(^|\n)status:\s*\S+', f'\\1status: "{status}"', text)
        if extra:
            for k, v in extra.items():
                val_str = f'"{v}"' if isinstance(v, str) else str(v)
                if f'\n{k}:' in text:
                    text = re.sub(rf'(\n){k}:\s*\S+', f'\\1{k}: {val_str}', text)
                else:
                    # Insert before closing ---
                    text = text.replace("\n---\n\n", f"\n{k}: {val_str}\n---\n\n", 1)
        file_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not update frontmatter in %s: %s", file_path, exc)


class PostScheduler:
    """
    Reads vault/Scheduled/ folder every 60 seconds.
    Executes posts when scheduled_time <= now.
    Supports one-time, daily, weekly recurring posts.
    """

    def __init__(
        self,
        vault_path: Optional[Path] = None,
        social_manager: Optional[Any] = None,
    ) -> None:
        self.vault_path = vault_path or VAULT_PATH
        self.scheduled_folder = self.vault_path / "Scheduled"
        self.cancelled_folder = self.vault_path / "Cancelled"
        self.failed_folder = self.vault_path / "Failed"
        self.done_folder = self.vault_path / "Done"
        self.pending_folder = self.vault_path / "Pending_Approval"
        self.logs_folder = self.vault_path / "Logs"
        self._social_manager = social_manager
        self._scheduler = None

        for d in [self.scheduled_folder, self.cancelled_folder, self.failed_folder,
                  self.done_folder, self.pending_folder, self.logs_folder]:
            d.mkdir(parents=True, exist_ok=True)

    def _get_social_manager(self):
        if self._social_manager:
            return self._social_manager
        from social.social_manager import SocialMediaManager
        self._social_manager = SocialMediaManager(vault_path=self.vault_path)
        return self._social_manager

    # ------------------------------------------------------------------
    # 1. start()
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialize APScheduler and start the background scheduler."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.interval import IntervalTrigger

            self._scheduler = BackgroundScheduler(timezone="UTC")
            self._scheduler.add_job(
                self.scan_scheduled_folder,
                trigger=IntervalTrigger(seconds=60),
                id="scan_scheduled",
                name="Scan Scheduled Posts",
                replace_existing=True,
            )
            self._scheduler.add_job(
                self.check_approval_expirations,
                trigger=IntervalTrigger(seconds=300),
                id="check_approvals",
                name="Check Approval Expirations",
                replace_existing=True,
            )
            self._scheduler.start()
            logger.info("PostScheduler started")
        except ImportError:
            logger.error("APScheduler not installed — pip install apscheduler")

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("PostScheduler stopped")

    # ------------------------------------------------------------------
    # 2. scan_scheduled_folder()
    # ------------------------------------------------------------------

    def scan_scheduled_folder(self) -> None:
        """Check all pending scheduled posts and execute due ones."""
        now = datetime.now(timezone.utc)
        for file_path in self.scheduled_folder.glob("*.md"):
            try:
                text = file_path.read_text(encoding="utf-8")
                meta = _parse_frontmatter(text)
                if meta.get("status", "pending") != "pending":
                    continue
                scheduled_str = meta.get("scheduled_time", "")
                if not scheduled_str:
                    continue
                scheduled_dt = datetime.fromisoformat(str(scheduled_str))
                if scheduled_dt.tzinfo is None:
                    scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
                if scheduled_dt <= now:
                    self.execute_scheduled_post(file_path, meta)
            except Exception as exc:
                logger.error("Error processing scheduled file %s: %s", file_path.name, exc)

    # ------------------------------------------------------------------
    # 3. execute_scheduled_post()
    # ------------------------------------------------------------------

    def execute_scheduled_post(self, file_path: Path, meta: Dict[str, Any]) -> None:
        """Execute a scheduled post and update its status."""
        platform = str(meta.get("platform", ""))
        content = str(meta.get("content", ""))
        image_path = str(meta.get("image_path", "")) or None
        recurring = str(meta.get("recurring", "none"))

        if not platform or not content:
            logger.warning("Scheduled file %s missing platform/content", file_path.name)
            return

        logger.info("Executing scheduled post: %s → %s", file_path.name, platform)
        _update_frontmatter_status(file_path, "executing")

        try:
            sm = self._get_social_manager()
            platforms = ["linkedin", "twitter", "facebook", "instagram"] if platform == "all" else [platform]
            result = sm.post_to_all(content, image_path=image_path, platforms=platforms)

            # Mark as done and move
            _update_frontmatter_status(file_path, "done", {
                "post_result": str(result)[:200],
                "executed_at": datetime.now(timezone.utc).isoformat(),
            })
            dest = self.done_folder / file_path.name
            file_path.rename(dest)
            self._audit_log("SCHEDULED_EXECUTED", f"Executed: {file_path.name}", {
                "platform": platform, "result": str(result)[:200]
            })

            # Handle recurring
            if recurring in ("daily", "weekly"):
                self.add_recurring_post(content, platform, meta, recurring, file_path)

        except Exception as exc:
            logger.error("Scheduled post %s failed: %s", file_path.name, exc)
            _update_frontmatter_status(file_path, "failed", {"error": str(exc)[:200]})
            dest = self.failed_folder / file_path.name
            try:
                file_path.rename(dest)
            except OSError:
                pass
            self._audit_log("SCHEDULED_FAILED", f"Failed: {file_path.name}", {"error": str(exc)})

    # ------------------------------------------------------------------
    # 4. add_recurring_post()
    # ------------------------------------------------------------------

    def add_recurring_post(
        self,
        content: str,
        platform: str,
        meta: Dict[str, Any],
        frequency: str,
        original_path: Optional[Path] = None,
    ) -> Path:
        """Create next occurrence of a recurring post."""
        now = datetime.now(timezone.utc)
        if frequency == "daily":
            next_time = now + timedelta(days=1)
        elif frequency == "weekly":
            day_name = str(meta.get("recurring_day", "monday")).lower()
            days_ahead = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6,
            }.get(day_name, 7)
            next_monday = now + timedelta(days=(days_ahead - now.weekday()) % 7 + 7)
            next_time = next_monday.replace(
                hour=int(meta.get("hour", 9)),
                minute=0, second=0, microsecond=0,
            )
        else:
            return original_path or self.scheduled_folder / "unknown.md"

        from_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{platform.upper()}_{from_str}.md"
        new_meta = dict(meta)
        new_meta["scheduled_time"] = next_time.isoformat()
        new_meta["status"] = "pending"

        lines = ["---"]
        for k, v in new_meta.items():
            lines.append(f'{k}: "{v}"' if isinstance(v, str) else f"{k}: {v}")
        lines.append("---")
        lines.append(f"\n# Recurring {platform.title()} Post\n\n{content}")

        path = self.scheduled_folder / filename
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Next recurring post scheduled: %s → %s", filename, next_time.isoformat())
        return path

    # ------------------------------------------------------------------
    # 5. check_approval_expirations()
    # ------------------------------------------------------------------

    def check_approval_expirations(self) -> None:
        """Auto-approve or expire pending approval files."""
        now = datetime.now(timezone.utc)
        for file_path in self.pending_folder.glob("*.md"):
            try:
                text = file_path.read_text(encoding="utf-8")
                meta = _parse_frontmatter(text)
                if meta.get("status", "") != "pending_approval":
                    continue

                created_str = str(meta.get("created_at", ""))
                auto_hours = meta.get("auto_approve_hours")

                if created_str and auto_hours:
                    created_dt = datetime.fromisoformat(created_str)
                    if created_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=timezone.utc)
                    if now > created_dt + timedelta(hours=int(auto_hours)):
                        logger.info("Auto-approving: %s", file_path.name)
                        dest = self.vault_path / "Approved" / file_path.name
                        (self.vault_path / "Approved").mkdir(exist_ok=True)
                        _update_frontmatter_status(file_path, "auto_approved")
                        file_path.rename(dest)
                        self._audit_log("AUTO_APPROVED", f"Auto-approved: {file_path.name}", {})
            except Exception as exc:
                logger.debug("Approval expiration check error: %s", exc)

    # ------------------------------------------------------------------
    # 6. get_upcoming_posts()
    # ------------------------------------------------------------------

    def get_upcoming_posts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return next N scheduled posts sorted by scheduled_time."""
        posts = []
        for file_path in self.scheduled_folder.glob("*.md"):
            try:
                meta = _parse_frontmatter(file_path.read_text(encoding="utf-8"))
                if meta.get("status", "pending") != "pending":
                    continue
                scheduled_str = str(meta.get("scheduled_time", ""))
                if scheduled_str:
                    posts.append({
                        "filename": file_path.name,
                        "platform": meta.get("platform", ""),
                        "scheduled_time": scheduled_str,
                        "content_preview": str(meta.get("content", ""))[:100],
                        "recurring": meta.get("recurring", "none"),
                        "status": "pending",
                    })
            except Exception:
                pass
        posts.sort(key=lambda x: x["scheduled_time"])
        return posts[:limit]

    # ------------------------------------------------------------------
    # 7. cancel_post()
    # ------------------------------------------------------------------

    def cancel_post(self, file_name: str) -> bool:
        """Move file to vault/Cancelled/."""
        file_path = self.scheduled_folder / file_name
        if not file_path.exists():
            return False
        self.cancelled_folder.mkdir(parents=True, exist_ok=True)
        _update_frontmatter_status(file_path, "cancelled")
        file_path.rename(self.cancelled_folder / file_name)
        self._audit_log("POST_CANCELLED", f"Cancelled: {file_name}", {})
        # Remove APScheduler job if exists
        if self._scheduler:
            job_id = f"scheduled_{file_name}"
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _audit_log(self, event: str, message: str, extra: Dict[str, Any]) -> None:
        self.logs_folder.mkdir(parents=True, exist_ok=True)
        import json
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "message": message,
            **extra,
        }
        try:
            with (self.logs_folder / "scheduler.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass
