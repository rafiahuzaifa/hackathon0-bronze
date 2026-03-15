"""
base_watcher.py — Abstract BaseWatcher
Gold Tier — Panaversity AI Employee Hackathon 2026

All platform watchers inherit from this class.
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

YAML_SEPARATOR = "---"


class BaseWatcher(ABC):
    """
    Abstract base class for all platform watchers.

    Subclasses must implement:
        - start()  — enter the polling/event loop
        - stop()   — signal the loop to stop
        - poll()   — one iteration of the check cycle
    """

    def __init__(
        self,
        vault_path: str | Path,
        dry_run: bool = False,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        self.vault_path = Path(vault_path)
        self.dry_run = dry_run
        self._audit_logger = audit_logger or logging.getLogger(f"{self.__class__.__name__}.audit")
        self._running = False

        # Standard vault directories
        self._needs_action_dir = self.vault_path / "Needs_Action"
        self._pending_approval_dir = self.vault_path / "Pending_Approval"
        self._approved_dir = self.vault_path / "Approved"
        self._rejected_dir = self.vault_path / "Rejected"
        self._done_dir = self.vault_path / "Done"
        self._logs_dir = self.vault_path / "Logs"

        self._ensure_dirs()

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def start(self) -> None:
        """Enter the main polling loop. Blocks until stop() is called."""

    @abstractmethod
    def stop(self) -> None:
        """Signal the polling loop to exit."""

    @abstractmethod
    def poll(self) -> None:
        """Run one polling cycle. Called repeatedly by start()."""

    # ------------------------------------------------------------------
    # Vault file helpers
    # ------------------------------------------------------------------

    def create_needs_action_file(
        self, filename: str, content: str, metadata: Dict[str, Any]
    ) -> Path:
        """
        Write a Markdown file with YAML frontmatter to vault/Needs_Action/.

        Args:
            filename: Target filename (e.g. ``EMAIL_001.md``).
            content:  Body content below the frontmatter.
            metadata: Dict serialised as YAML frontmatter.

        Returns:
            Path to the created file.
        """
        return self._write_vault_file(self._needs_action_dir, filename, content, metadata)

    def create_pending_approval_file(
        self, filename: str, content: str, metadata: Dict[str, Any]
    ) -> Path:
        """Write a file to vault/Pending_Approval/."""
        return self._write_vault_file(self._pending_approval_dir, filename, content, metadata)

    def _write_vault_file(
        self, directory: Path, filename: str, content: str, metadata: Dict[str, Any]
    ) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / filename
        frontmatter = self._build_frontmatter(metadata)
        full_content = f"{frontmatter}\n\n{content}"
        if self.dry_run:
            logger.info("[DRY RUN] Would write %s", filepath)
            return filepath
        filepath.write_text(full_content, encoding="utf-8")
        logger.debug("Vault file written: %s", filepath)
        return filepath

    @staticmethod
    def _build_frontmatter(metadata: Dict[str, Any]) -> str:
        lines = [YAML_SEPARATOR]
        for key, value in metadata.items():
            if isinstance(value, str):
                # Escape quotes
                escaped = value.replace('"', '\\"')
                lines.append(f'{key}: "{escaped}"')
            elif isinstance(value, bool):
                lines.append(f"{key}: {str(value).lower()}")
            elif value is None:
                lines.append(f"{key}: null")
            else:
                lines.append(f"{key}: {value}")
        lines.append(YAML_SEPARATOR)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Risk classification
    # ------------------------------------------------------------------

    HIGH_RISK_KEYWORDS = frozenset([
        "urgent", "lawsuit", "legal", "complaint", "fraud", "hack",
        "password", "credentials", "bank", "payment", "invoice",
        "refund", "deadline", "emergency",
    ])

    MEDIUM_RISK_KEYWORDS = frozenset([
        "price", "quote", "contract", "proposal", "discount",
        "follow up", "reminder", "overdue", "issue",
    ])

    def classify_risk(self, text: str) -> str:
        """
        Classify message risk level as 'high', 'medium', or 'low'.

        Args:
            text: Message body to analyse.

        Returns:
            'high' | 'medium' | 'low'
        """
        lower = text.lower()
        if any(kw in lower for kw in self.HIGH_RISK_KEYWORDS):
            return "high"
        if any(kw in lower for kw in self.MEDIUM_RISK_KEYWORDS):
            return "medium"
        return "low"

    # ------------------------------------------------------------------
    # DRY_RUN guard
    # ------------------------------------------------------------------

    def check_dry_run(self, action_name: str) -> bool:
        """
        Return True if dry_run is active (and log it).

        Use this before any irreversible action (send, post, pay).
        """
        if self.dry_run:
            logger.info("[DRY RUN] Skipping action: %s", action_name)
            return True
        return False

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def log_event(self, event_type: str, message: str, extra: Dict[str, Any]) -> None:
        """
        Write a structured audit event to vault/Logs/<watcher>.jsonl.

        Args:
            event_type: Short uppercase label (e.g. ``EMAIL_RECEIVED``).
            message:    Human-readable description.
            extra:      Additional context dict.
        """
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = self._logs_dir / f"{self.__class__.__name__.lower()}.jsonl"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "message": message,
            "dry_run": self.dry_run,
            **extra,
        }
        try:
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Could not write audit log: %s", exc)

        self._audit_logger.info("[%s] %s — %s", event_type, message, extra)

    # ------------------------------------------------------------------
    # Retry / backoff
    # ------------------------------------------------------------------

    @staticmethod
    def exponential_backoff(
        attempt: int,
        base: float = 1.0,
        multiplier: float = 2.0,
        cap: float = 300.0,
        jitter: float = 0.3,
    ) -> float:
        """
        Compute exponential backoff with jitter.

        Args:
            attempt:    Zero-based attempt number.
            base:       Starting wait in seconds.
            multiplier: Growth factor per attempt.
            cap:        Maximum wait in seconds.
            jitter:     Random fraction ± to add/subtract.

        Returns:
            Seconds to wait before the next retry.
        """
        delay = min(base * (multiplier ** attempt), cap)
        delay *= 1 + random.uniform(-jitter, jitter)
        return max(0.0, delay)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        for d in [
            self._needs_action_dir,
            self._pending_approval_dir,
            self._approved_dir,
            self._rejected_dir,
            self._done_dir,
            self._logs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)
