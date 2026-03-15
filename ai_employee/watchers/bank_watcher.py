"""
bank_watcher.py — Bank Transaction Watcher
Watches an upload folder for new CSV/PDF bank statements.
Runs anomaly detection and creates audit reports in vault.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base_watcher import BaseWatcher

logger = logging.getLogger(__name__)

POLL_INTERVAL = 300  # 5 minutes

ANOMALY_RULES = {
    "ROUND_AMOUNT_FLAG": lambda amt: amt > 1000 and amt % 1000 == 0,
    "HIGH_VALUE_FLAG": lambda amt: amt > 50000,
    "DUPLICATE_FLAG": None,  # checked separately
    "UNKNOWN_VENDOR_FLAG": None,  # checked separately
}

KNOWN_VENDORS = [
    "electricity", "internet", "water", "gas", "rent",
    "payroll", "salary", "google", "aws", "azure",
    "openai", "anthropic", "github", "digital ocean",
]


class Transaction:
    def __init__(self, date: str, description: str, amount: float, currency: str = "PKR") -> None:
        self.date = date
        self.description = description
        self.amount = amount
        self.currency = currency
        self.flags: List[str] = []


class BankWatcher(BaseWatcher):
    """
    Monitors an upload folder for new bank CSV files.
    Runs anomaly detection and creates audit vault files.
    """

    def __init__(
        self,
        vault_path: str | Path,
        watch_folder: str | Path,
        currency: str = "PKR",
        dry_run: bool = False,
        poll_interval: int = POLL_INTERVAL,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(vault_path, dry_run, audit_logger)
        self.watch_folder = Path(watch_folder)
        self.currency = currency
        self.poll_interval = poll_interval
        self._processed_files: set[str] = set()

    def start(self) -> None:
        self._running = True
        self.watch_folder.mkdir(parents=True, exist_ok=True)
        logger.info("BankWatcher started, watching: %s", self.watch_folder)
        self.log_event("WATCHER_START", "BankWatcher started",
                       {"watch_folder": str(self.watch_folder)})
        attempt = 0
        while self._running:
            try:
                self.poll()
                attempt = 0
            except Exception as exc:
                wait = self.exponential_backoff(attempt)
                logger.error("Bank poll error (attempt %d): %s", attempt, exc)
                attempt += 1
                time.sleep(wait)
                continue
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("BankWatcher stopping…")

    def poll(self) -> None:
        """Scan watch folder for new CSV files."""
        for csv_file in self.watch_folder.glob("*.csv"):
            key = str(csv_file)
            if key in self._processed_files:
                continue
            self._process_csv(csv_file)
            self._processed_files.add(key)

    def _process_csv(self, csv_path: Path) -> None:
        """Parse bank CSV, run anomaly detection, create vault report."""
        logger.info("Processing bank CSV: %s", csv_path)
        transactions = self._parse_csv(csv_path)
        if not transactions:
            logger.warning("No transactions parsed from %s", csv_path)
            return

        self._detect_anomalies(transactions)
        self._create_audit_report(csv_path.stem, transactions)

    def _parse_csv(self, csv_path: Path) -> List[Transaction]:
        """Parse CSV with flexible column names."""
        transactions = []
        try:
            with csv_path.open(encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # Flexible column names
                        date = (row.get("date") or row.get("Date") or
                                row.get("DATE") or "")
                        desc = (row.get("description") or row.get("Description") or
                                row.get("DESCRIPTION") or row.get("narration") or "")
                        amt_str = (row.get("amount") or row.get("Amount") or
                                   row.get("AMOUNT") or "0")
                        amt = float(str(amt_str).replace(",", "").replace(" ", ""))
                        transactions.append(Transaction(
                            date=date, description=desc, amount=abs(amt), currency=self.currency
                        ))
                    except (ValueError, KeyError):
                        continue
        except OSError as exc:
            logger.error("Could not read CSV %s: %s", csv_path, exc)
        return transactions

    def _detect_anomalies(self, transactions: List[Transaction]) -> None:
        """Flag anomalous transactions in-place."""
        seen: Dict[Tuple[str, float], int] = {}
        amounts = [t.amount for t in transactions]
        avg = sum(amounts) / len(amounts) if amounts else 0

        for tx in transactions:
            # Round amount flag
            if tx.amount > 1000 and tx.amount % 1000 == 0:
                tx.flags.append("ROUND_AMOUNT_FLAG")
            # High value flag
            if tx.amount > 50000:
                tx.flags.append("HIGH_VALUE_FLAG")
            # Spike flag (3x average)
            if avg > 0 and tx.amount > avg * 3:
                tx.flags.append("SPIKE_FLAG")
            # Unknown vendor flag
            desc_lower = tx.description.lower()
            if not any(v in desc_lower for v in KNOWN_VENDORS):
                tx.flags.append("UNKNOWN_VENDOR_FLAG")
            # Duplicate detection
            key = (tx.description[:50], tx.amount)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                tx.flags.append("DUPLICATE_FLAG")

    def _create_audit_report(self, stem: str, transactions: List[Transaction]) -> None:
        """Create a vault audit report for a bank statement."""
        flagged = [t for t in transactions if t.flags]
        total_income = sum(t.amount for t in transactions)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        lines = [
            f"# Bank Audit Report — {stem}",
            "",
            f"**Date:** {ts_str}",
            f"**Total Transactions:** {len(transactions)}",
            f"**Total Amount:** {self.currency} {total_income:,.2f}",
            f"**Flagged:** {len(flagged)}",
            "",
            "## Flagged Transactions",
            "",
            "| Date | Description | Amount | Flags |",
            "|------|-------------|--------|-------|",
        ]
        for tx in flagged:
            flags_str = ", ".join(tx.flags)
            lines.append(f"| {tx.date} | {tx.description[:40]} | "
                         f"{self.currency} {tx.amount:,.2f} | {flags_str} |")

        lines += ["", "## All Transactions", "", "| Date | Description | Amount | Flags |",
                  "|------|-------------|--------|-------|"]
        for tx in transactions:
            flags_str = ", ".join(tx.flags) if tx.flags else "—"
            lines.append(f"| {tx.date} | {tx.description[:40]} | "
                         f"{self.currency} {tx.amount:,.2f} | {flags_str} |")

        content = "\n".join(lines)
        metadata: Dict[str, Any] = {
            "source": "bank",
            "file": stem,
            "total_transactions": len(transactions),
            "flagged_count": len(flagged),
            "processed": datetime.now(timezone.utc).isoformat(),
            "status": "needs_action" if flagged else "done",
        }

        if flagged:
            filename = f"BANK_AUDIT_{stem}_{ts_str}.md"
            self.create_needs_action_file(filename, content, metadata)
            self.log_event("BANK_FLAGGED", f"{len(flagged)} anomalies in {stem}",
                           {"flagged": len(flagged)})
        else:
            # Write directly to Done
            done_dir = self.vault_path / "Done"
            done_dir.mkdir(parents=True, exist_ok=True)
            filename = f"BANK_CLEAN_{stem}_{ts_str}.md"
            frontmatter = self._build_frontmatter(metadata)
            (done_dir / filename).write_text(
                f"{frontmatter}\n\n{content}", encoding="utf-8"
            )
            self.log_event("BANK_CLEAN", f"No anomalies in {stem}", {})
