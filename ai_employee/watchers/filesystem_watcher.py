"""
filesystem_watcher.py — Vault Filesystem Watcher
Uses watchdog library to monitor vault/Needs_Action/ for new .md files
and trigger the orchestrator to process them.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .base_watcher import BaseWatcher

logger = logging.getLogger(__name__)


class FilesystemWatcher(BaseWatcher):
    """
    Monitors vault directories for new files using watchdog.
    Calls on_new_file callback when a new .md file is created.
    """

    def __init__(
        self,
        vault_path: str | Path,
        on_new_file: Optional[Callable[[Path], None]] = None,
        watch_dirs: Optional[list] = None,
        dry_run: bool = False,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.on_new_file = on_new_file or self._default_handler
        self.watch_dirs = watch_dirs or [
            self._needs_action_dir,
            self._pending_approval_dir,
            self._approved_dir,
        ]
        self._observer = None
        self._known_files: set[str] = set()

    def _default_handler(self, filepath: Path) -> None:
        logger.info("New vault file detected: %s", filepath)
        self.log_event("FILE_DETECTED", f"New file: {filepath.name}",
                       {"path": str(filepath), "dir": filepath.parent.name})

    def start(self) -> None:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class VaultHandler(FileSystemEventHandler):
                def __init__(self, watcher: "FilesystemWatcher"):
                    self._watcher = watcher

                def on_created(self, event):
                    if not event.is_directory and event.src_path.endswith(".md"):
                        path = Path(event.src_path)
                        self._watcher.on_new_file(path)
                        self._watcher.log_event(
                            "FILE_CREATED", f"Created: {path.name}",
                            {"path": str(path), "dir": path.parent.name}
                        )

            self._observer = Observer()
            handler = VaultHandler(self)
            for watch_dir in self.watch_dirs:
                watch_dir.mkdir(parents=True, exist_ok=True)
                self._observer.schedule(handler, str(watch_dir), recursive=False)
                logger.info("Watching: %s", watch_dir)

            self._observer.start()
            self._running = True
            logger.info("FilesystemWatcher started (%d dirs)", len(self.watch_dirs))
            self.log_event("WATCHER_START", "FilesystemWatcher started",
                           {"dirs": [str(d) for d in self.watch_dirs]})

            while self._running:
                time.sleep(1)

        except ImportError:
            logger.warning("watchdog not installed — falling back to polling")
            self._start_polling()

    def _start_polling(self) -> None:
        """Fallback polling when watchdog is not available."""
        self._running = True
        while self._running:
            try:
                self.poll()
            except Exception as exc:
                logger.error("Filesystem poll error: %s", exc)
            time.sleep(5)

    def stop(self) -> None:
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join()
        logger.info("FilesystemWatcher stopped.")

    def poll(self) -> None:
        """Polling fallback: scan watched dirs for new .md files."""
        for watch_dir in self.watch_dirs:
            if not watch_dir.exists():
                continue
            for filepath in watch_dir.glob("*.md"):
                key = str(filepath)
                if key not in self._known_files:
                    self._known_files.add(key)
                    self.on_new_file(filepath)
