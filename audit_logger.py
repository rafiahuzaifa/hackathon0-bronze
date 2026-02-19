#!/usr/bin/env python3
"""
audit_logger.py — Structured JSON Audit Logging for AI Employee

Writes machine-readable JSON log entries to /Logs/ with:
  - Structured fields: timestamp, level, category, component, message, data
  - Daily log rotation (one file per day)
  - Error categorization: TRANSIENT, AUTH, LOGIC, SYSTEM
  - Event tracking for audit compliance
  - Query helpers for log analysis

Log Format (one JSON object per line — JSONL):
  {
    "ts": "2026-02-19T20:30:00.000Z",
    "level": "ERROR",
    "category": "TRANSIENT",
    "component": "gmail_watcher",
    "event": "api_call_failed",
    "message": "Gmail API timeout after 15s",
    "data": {"endpoint": "/messages", "attempt": 2, "max_retries": 3},
    "trace_id": "abc123"
  }
"""

import os
import sys
import json
import uuid
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VAULT_DIR = Path("d:/hackathon0/hackathon/AI_Employee_Vault")
LOGS_DIR = VAULT_DIR / "Logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Error categories
class ErrorCategory:
    TRANSIENT = "TRANSIENT"  # Network timeouts, API rate limits, temp failures
    AUTH = "AUTH"            # Authentication failures, expired tokens, permission denied
    LOGIC = "LOGIC"         # Business logic errors, validation failures, bad data
    SYSTEM = "SYSTEM"       # Disk full, OOM, config missing, unexpected crashes


# Log levels
class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    AUDIT = "AUDIT"     # Special level for audit trail entries


# ---------------------------------------------------------------------------
# Audit Logger
# ---------------------------------------------------------------------------
class AuditLogger:
    """
    Structured JSON logger that writes to /Logs/audit_YYYY-MM-DD.jsonl

    Each entry is a single JSON line (JSONL format) for easy parsing.
    """

    def __init__(self, component="system", logs_dir=LOGS_DIR):
        self.component = component
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._trace_id = None
        self._session_id = str(uuid.uuid4())[:8]

        # Also set up a Python logger for console output
        self._py_logger = logging.getLogger(f"audit.{component}")
        if not self._py_logger.handlers:
            handler = logging.StreamHandler(
                open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)
                if sys.platform == "win32"
                else sys.stdout
            )
            handler.setFormatter(logging.Formatter(
                "[%(asctime)s] [%(name)s] %(levelname)s: %(message)s"
            ))
            self._py_logger.addHandler(handler)
            self._py_logger.setLevel(logging.DEBUG)

    @property
    def trace_id(self):
        return self._trace_id

    def start_trace(self, trace_id=None):
        """Start a new trace context for correlating related log entries."""
        self._trace_id = trace_id or str(uuid.uuid4())[:12]
        return self._trace_id

    def end_trace(self):
        """End the current trace context."""
        tid = self._trace_id
        self._trace_id = None
        return tid

    def _log_file_path(self):
        """Get today's log file path."""
        return self.logs_dir / f"audit_{date.today().isoformat()}.jsonl"

    def _write_entry(self, entry):
        """Write a JSON entry to the log file."""
        filepath = self._log_file_path()
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def log(
        self,
        level: str,
        message: str,
        event: str = "general",
        category: Optional[str] = None,
        data: Optional[dict] = None,
        error: Optional[Exception] = None,
    ):
        """Write a structured log entry."""
        entry = {
            "ts": datetime.now().isoformat(),
            "level": level,
            "component": self.component,
            "event": event,
            "message": message,
            "session_id": self._session_id,
        }

        if category:
            entry["category"] = category
        if data:
            entry["data"] = data
        if self._trace_id:
            entry["trace_id"] = self._trace_id
        if error:
            entry["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }

        self._write_entry(entry)

        # Also log to console
        py_level = getattr(logging, level if level != "AUDIT" else "INFO", logging.INFO)
        cat_prefix = f"[{category}] " if category else ""
        self._py_logger.log(py_level, f"{cat_prefix}{event}: {message}")

        return entry

    # ── Convenience methods ──

    def debug(self, message, event="debug", **kwargs):
        return self.log(LogLevel.DEBUG, message, event, **kwargs)

    def info(self, message, event="info", **kwargs):
        return self.log(LogLevel.INFO, message, event, **kwargs)

    def warn(self, message, event="warning", **kwargs):
        return self.log(LogLevel.WARN, message, event, **kwargs)

    def error(self, message, event="error", category=ErrorCategory.LOGIC, **kwargs):
        return self.log(LogLevel.ERROR, message, event, category=category, **kwargs)

    def critical(self, message, event="critical", category=ErrorCategory.SYSTEM, **kwargs):
        return self.log(LogLevel.CRITICAL, message, event, category=category, **kwargs)

    def audit(self, message, event="audit_trail", **kwargs):
        """Special audit trail entry for compliance."""
        return self.log(LogLevel.AUDIT, message, event, **kwargs)

    # ── Error-category shortcuts ──

    def transient(self, message, event="transient_error", **kwargs):
        return self.error(message, event, category=ErrorCategory.TRANSIENT, **kwargs)

    def auth_error(self, message, event="auth_failure", **kwargs):
        return self.error(message, event, category=ErrorCategory.AUTH, **kwargs)

    def logic_error(self, message, event="logic_error", **kwargs):
        return self.error(message, event, category=ErrorCategory.LOGIC, **kwargs)

    def system_error(self, message, event="system_error", **kwargs):
        return self.error(message, event, category=ErrorCategory.SYSTEM, **kwargs)

    # ── Retry logging ──

    def retry_attempt(self, attempt, max_retries, error_msg, delay_ms, **kwargs):
        """Log a retry attempt."""
        return self.warn(
            f"Retry {attempt}/{max_retries}: {error_msg} (next in {delay_ms}ms)",
            event="retry_attempt",
            data={"attempt": attempt, "max_retries": max_retries, "delay_ms": delay_ms},
            **kwargs,
        )

    def retry_exhausted(self, max_retries, error_msg, **kwargs):
        """Log when all retries are exhausted."""
        return self.error(
            f"All {max_retries} retries exhausted: {error_msg}",
            event="retry_exhausted",
            category=ErrorCategory.TRANSIENT,
            data={"max_retries": max_retries},
            **kwargs,
        )

    def retry_success(self, attempt, **kwargs):
        """Log successful retry."""
        return self.info(
            f"Succeeded on attempt {attempt}",
            event="retry_success",
            data={"attempt": attempt},
            **kwargs,
        )

    # ── Queue logging ──

    def queued(self, task_desc, queue_file, reason, **kwargs):
        """Log a task being queued for later processing."""
        return self.warn(
            f"Queued: {task_desc} -> {queue_file} (reason: {reason})",
            event="task_queued",
            data={"task": task_desc, "queue_file": str(queue_file), "reason": reason},
            **kwargs,
        )

    def dequeued(self, task_desc, **kwargs):
        """Log a task being dequeued for processing."""
        return self.info(
            f"Dequeued: {task_desc}",
            event="task_dequeued",
            data={"task": task_desc},
            **kwargs,
        )

    # ── Query helpers ──

    @staticmethod
    def read_logs(log_file, level=None, category=None, component=None, limit=100):
        """Read and filter log entries from a JSONL file."""
        entries = []
        filepath = Path(log_file)
        if not filepath.exists():
            return entries

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if level and entry.get("level") != level:
                    continue
                if category and entry.get("category") != category:
                    continue
                if component and entry.get("component") != component:
                    continue

                entries.append(entry)
                if len(entries) >= limit:
                    break

        return entries

    @staticmethod
    def count_by_category(log_file):
        """Count log entries by error category."""
        counts = {}
        filepath = Path(log_file)
        if not filepath.exists():
            return counts

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    cat = entry.get("category", "NONE")
                    counts[cat] = counts.get(cat, 0) + 1
                except (json.JSONDecodeError, AttributeError):
                    continue

        return counts


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------
_default_logger = None


def get_logger(component="system"):
    """Get or create an AuditLogger for the given component."""
    global _default_logger
    if _default_logger is None or _default_logger.component != component:
        _default_logger = AuditLogger(component=component)
    return _default_logger
