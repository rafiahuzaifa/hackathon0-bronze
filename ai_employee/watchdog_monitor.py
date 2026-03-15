"""
watchdog_monitor.py — System Health Monitor
Gold Tier — Panaversity AI Employee Hackathon 2026

Monitors all AI Employee processes and vault health.
Generates health reports to vault/Logs/health.json every 60 seconds.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.resolve()
VAULT_PATH = Path(os.environ.get("VAULT_PATH", str(BASE_DIR / "vault")))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
HEALTH_REPORT_INTERVAL = int(os.environ.get("HEALTH_REPORT_INTERVAL", "60"))
MIN_DISK_MB = 500

LOGS_DIR = VAULT_PATH / "Logs"
PIDS_DIR = VAULT_PATH / "pids"

REQUIRED_DIRS = [
    VAULT_PATH / "Needs_Action",
    VAULT_PATH / "Pending_Approval",
    VAULT_PATH / "Approved",
    VAULT_PATH / "Rejected",
    VAULT_PATH / "Done",
    LOGS_DIR,
    PIDS_DIR,
]

REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "GMAIL_CLIENT_ID",
    "TWITTER_API_KEY",
    "LINKEDIN_CLIENT_ID",
    "FACEBOOK_APP_ID",
]

WATCHER_NAMES = [
    "gmail", "whatsapp", "linkedin", "twitter",
    "facebook", "instagram", "filesystem", "bank",
]

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("watchdog_monitor")


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    critical: bool = False
    details: Optional[Dict[str, Any]] = None


@dataclass
class HealthReport:
    timestamp: str
    overall_status: str
    checks: List[CheckResult] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "overall_status": self.overall_status,
            "summary": self.summary,
            "checks": [
                {"name": c.name, "passed": c.passed, "message": c.message,
                 "critical": c.critical, "details": c.details}
                for c in self.checks
            ],
        }


class HealthChecker:
    def __init__(self) -> None:
        self._vault_path = VAULT_PATH

    def check_all(self) -> HealthReport:
        checks: List[CheckResult] = []
        checks.extend(self._check_watcher_processes())
        checks.extend(self._check_vault_dirs())
        checks.append(self._check_disk_space())
        checks.extend(self._check_env_vars())
        checks.append(self._check_api_server())

        failed_critical = [c for c in checks if not c.passed and c.critical]
        failed_any = [c for c in checks if not c.passed]

        if failed_critical:
            overall = "critical"
        elif failed_any:
            overall = "degraded"
        else:
            overall = "healthy"

        summary = (
            f"{len(checks) - len(failed_any)}/{len(checks)} checks passed. "
            f"Critical failures: {len(failed_critical)}."
        )

        report = HealthReport(
            timestamp=datetime.utcnow().isoformat() + "Z",
            overall_status=overall,
            checks=checks,
            summary=summary,
        )

        for c in failed_critical:
            logger.error("[HEALTH CRITICAL] %s: %s", c.name, c.message)
        for c in failed_any:
            if not c.critical:
                logger.warning("[HEALTH WARNING] %s: %s", c.name, c.message)

        return report

    def _check_watcher_processes(self) -> List[CheckResult]:
        results = []
        for name in WATCHER_NAMES:
            pid_file = PIDS_DIR / f"{name}.pid"
            if not pid_file.exists():
                results.append(CheckResult(
                    name=f"watcher.{name}", passed=False,
                    message=f"PID file not found: {pid_file}", critical=False,
                ))
                continue
            try:
                pid = int(pid_file.read_text().strip())
            except (ValueError, OSError) as exc:
                results.append(CheckResult(
                    name=f"watcher.{name}", passed=False,
                    message=f"Could not read PID: {exc}", critical=False,
                ))
                continue
            alive = self._is_pid_alive(pid)
            results.append(CheckResult(
                name=f"watcher.{name}", passed=alive,
                message=f"pid={pid} is {'alive' if alive else 'dead'}.",
                critical=False, details={"pid": pid},
            ))
        return results

    def _check_vault_dirs(self) -> List[CheckResult]:
        results = []
        for d in REQUIRED_DIRS:
            exists = d.is_dir()
            if not exists:
                try:
                    d.mkdir(parents=True, exist_ok=True)
                    exists = True
                    msg = f"Directory created: {d}"
                except OSError as exc:
                    msg = f"Directory missing and could not be created: {exc}"
            else:
                msg = f"Directory exists: {d}"
            results.append(CheckResult(
                name=f"vault.dir.{d.name}", passed=exists,
                message=msg, critical=True, details={"path": str(d)},
            ))
        return results

    def _check_disk_space(self) -> CheckResult:
        try:
            usage = shutil.disk_usage(str(VAULT_PATH))
            free_mb = usage.free / (1024 * 1024)
            passed = free_mb >= MIN_DISK_MB
            return CheckResult(
                name="disk.space", passed=passed,
                message=f"Free: {free_mb:.0f} MB ({'OK' if passed else f'BELOW {MIN_DISK_MB}MB'})",
                critical=False, details={"free_mb": round(free_mb, 1)},
            )
        except OSError as exc:
            return CheckResult(name="disk.space", passed=False,
                               message=f"Disk check failed: {exc}", critical=False)

    def _check_env_vars(self) -> List[CheckResult]:
        results = []
        for var in REQUIRED_ENV_VARS:
            value = os.environ.get(var, "")
            is_set = bool(value and value.strip() and not value.startswith("sk-ant-..."))
            results.append(CheckResult(
                name=f"env.{var}", passed=is_set,
                message=f"{var} is {'set' if is_set else 'NOT set or placeholder'}.",
                critical=(var == "ANTHROPIC_API_KEY"),
            ))
        return results

    def _check_api_server(self) -> CheckResult:
        import urllib.request
        api_host = os.environ.get("API_HOST", "127.0.0.1")
        api_port = int(os.environ.get("API_PORT", "8000"))
        url = f"http://{api_host}:{api_port}/health"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
                passed = data.get("status") == "ok"
                return CheckResult(name="api.server", passed=passed,
                                   message=f"API {'healthy' if passed else 'non-ok'} at {url}",
                                   critical=False)
        except Exception as exc:
            return CheckResult(name="api.server", passed=False,
                               message=f"API unreachable at {url}: {exc}", critical=False)

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def write_health_report(report: HealthReport) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    health_path = LOGS_DIR / "health.json"
    try:
        health_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        logger.error("Failed to write health report: %s", exc)


def run() -> None:
    checker = HealthChecker()
    logger.info("Watchdog monitor started. Interval=%ds", HEALTH_REPORT_INTERVAL)
    while True:
        try:
            report = checker.check_all()
            write_health_report(report)
            logger.info("Health: %s — %s", report.overall_status.upper(), report.summary)
        except Exception as exc:
            logger.error("Health check error: %s", exc, exc_info=True)
        time.sleep(HEALTH_REPORT_INTERVAL)


if __name__ == "__main__":
    run()
