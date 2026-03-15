#!/usr/bin/env python3
"""
retry_handler.py — Comprehensive Error Handling for AI Employee

Features:
  1. @retry decorator with exponential backoff + jitter
  2. Error classification: Transient, Auth, Logic (with auto-categorization)
  3. Graceful degradation: queue tasks when APIs are down
  4. Dead-letter queue for permanently failed tasks
  5. Circuit breaker pattern for repeated failures
  6. Integration with audit_logger.py for structured JSON logging

Usage:
    from retry_handler import retry, ErrorHandler, ErrorCategory

    @retry(max_retries=3, backoff_base=1.0, category="TRANSIENT")
    def call_gmail_api():
        ...

    handler = ErrorHandler(component="orchestrator")
    handler.safe_execute(risky_function, fallback=queue_task)
"""

import os
import sys
import json
import time
import random
import functools
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any, Type

from audit_logger import AuditLogger, ErrorCategory, LogLevel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VAULT_DIR = Path("d:/hackathon0/hackathon/AI_Employee_Vault")
QUEUE_DIR = VAULT_DIR / "Logs" / "queue"
DEAD_LETTER_DIR = VAULT_DIR / "Logs" / "dead_letter"

QUEUE_DIR.mkdir(parents=True, exist_ok=True)
DEAD_LETTER_DIR.mkdir(parents=True, exist_ok=True)

# Default retry settings
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 1.0    # seconds
DEFAULT_BACKOFF_MAX = 30.0    # max delay seconds
DEFAULT_JITTER = 0.5          # random jitter factor (0-1)


# ---------------------------------------------------------------------------
# Error Classification
# ---------------------------------------------------------------------------
# Maps exception types → error categories
EXCEPTION_CATEGORY_MAP = [
    # Order matters: more specific types first (PermissionError is subclass of OSError)
    # Auth
    (PermissionError, ErrorCategory.AUTH),

    # System
    (MemoryError, ErrorCategory.SYSTEM),
    (SystemError, ErrorCategory.SYSTEM),

    # Transient (specific before generic OSError)
    (ConnectionError, ErrorCategory.TRANSIENT),
    (TimeoutError, ErrorCategory.TRANSIENT),
    (ConnectionResetError, ErrorCategory.TRANSIENT),
    (BrokenPipeError, ErrorCategory.TRANSIENT),
    (OSError, ErrorCategory.TRANSIENT),

    # Logic
    (ValueError, ErrorCategory.LOGIC),
    (TypeError, ErrorCategory.LOGIC),
    (KeyError, ErrorCategory.LOGIC),
    (AttributeError, ErrorCategory.LOGIC),
]

# String patterns in error messages → categories
ERROR_MESSAGE_PATTERNS = {
    ErrorCategory.TRANSIENT: [
        "timeout", "timed out", "connection refused", "connection reset",
        "rate limit", "429", "503", "502", "504", "temporary",
        "service unavailable", "try again", "ECONNREFUSED", "ETIMEDOUT",
    ],
    ErrorCategory.AUTH: [
        "401", "403", "unauthorized", "forbidden", "token expired",
        "invalid credentials", "authentication failed", "access denied",
        "permission denied", "invalid_grant",
    ],
    ErrorCategory.LOGIC: [
        "validation", "invalid", "missing required", "bad request", "400",
        "not found", "404", "already exists", "duplicate", "constraint",
    ],
    ErrorCategory.SYSTEM: [
        "disk full", "no space", "out of memory", "segfault",
        "killed", "oom", "ENOMEM", "ENOSPC",
    ],
}


def classify_error(error: Exception) -> str:
    """
    Classify an exception into an error category.

    Priority:
      1. Exact exception type match
      2. Error message pattern matching
      3. Default to LOGIC
    """
    # Check exception type (ordered list — specific types first)
    for exc_type, category in EXCEPTION_CATEGORY_MAP:
        if isinstance(error, exc_type):
            return category

    # Check error message patterns
    msg = str(error).lower()
    for category, patterns in ERROR_MESSAGE_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in msg:
                return category

    return ErrorCategory.LOGIC  # default


def is_retryable(error: Exception) -> bool:
    """Determine if an error should be retried."""
    category = classify_error(error)
    # Only retry transient errors; auth/logic/system are not retryable
    return category == ErrorCategory.TRANSIENT


# ---------------------------------------------------------------------------
# Retry Decorator
# ---------------------------------------------------------------------------
def retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    backoff_max: float = DEFAULT_BACKOFF_MAX,
    jitter: float = DEFAULT_JITTER,
    retryable_exceptions: tuple = (Exception,),
    category: Optional[str] = None,
    component: str = "system",
    on_retry: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
):
    """
    Retry decorator with exponential backoff and jitter.

    Args:
        max_retries: Maximum number of retry attempts
        backoff_base: Base delay in seconds (doubled each retry)
        backoff_max: Maximum delay cap
        jitter: Random jitter factor (0 to 1)
        retryable_exceptions: Tuple of exception types to retry
        category: Force error category (auto-detected if None)
        component: Component name for logging
        on_retry: Callback(attempt, error, delay) on each retry
        on_failure: Callback(error, attempts) when all retries exhausted
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = AuditLogger(component=component)
            trace_id = logger.start_trace()
            last_error = None

            for attempt in range(1, max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        logger.retry_success(attempt)
                    logger.end_trace()
                    return result

                except retryable_exceptions as e:
                    last_error = e
                    err_category = category or classify_error(e)

                    # Don't retry non-transient errors
                    if err_category != ErrorCategory.TRANSIENT and not category:
                        logger.error(
                            f"{func.__name__} failed (non-retryable): {e}",
                            event="non_retryable_error",
                            category=err_category,
                            error=e,
                            data={"function": func.__name__, "attempt": attempt},
                        )
                        logger.end_trace()
                        raise

                    if attempt < max_retries:
                        # Calculate delay with exponential backoff + jitter
                        delay = min(
                            backoff_base * (2 ** (attempt - 1)),
                            backoff_max,
                        )
                        if jitter > 0:
                            delay += random.uniform(0, delay * jitter)

                        logger.retry_attempt(
                            attempt, max_retries, str(e), int(delay * 1000)
                        )

                        if on_retry:
                            on_retry(attempt, e, delay)

                        time.sleep(delay)
                    else:
                        # All retries exhausted
                        logger.retry_exhausted(max_retries, str(e))

                        if on_failure:
                            on_failure(e, max_retries)

                        logger.end_trace()
                        raise

            logger.end_trace()
            return None

        # Attach metadata for inspection
        wrapper._retry_config = {
            "max_retries": max_retries,
            "backoff_base": backoff_base,
            "component": component,
        }
        return wrapper
    return decorator


# Async version
def async_retry(
    max_retries=DEFAULT_MAX_RETRIES,
    backoff_base=DEFAULT_BACKOFF_BASE,
    backoff_max=DEFAULT_BACKOFF_MAX,
    **kwargs,
):
    """Async version of the retry decorator."""
    import asyncio

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kw):
            logger = AuditLogger(component=kwargs.get("component", "system"))
            last_error = None

            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kw)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries and is_retryable(e):
                        delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                        logger.retry_attempt(attempt, max_retries, str(e), int(delay * 1000))
                        await asyncio.sleep(delay)
                    else:
                        logger.retry_exhausted(max_retries, str(e))
                        raise

        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------
class CircuitBreaker:
    """
    Circuit breaker pattern — stops calling a failing service
    after threshold consecutive failures.

    States:
      CLOSED  → normal operation, calls pass through
      OPEN    → service is down, calls fail fast
      HALF    → testing recovery, allows one call through
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, name, failure_threshold=5, recovery_timeout=60, logger=None):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # seconds
        self.logger = logger or AuditLogger(component=f"circuit_{name}")

        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.success_count = 0

    def can_execute(self):
        """Check if a call is allowed."""
        if self.state == self.CLOSED:
            return True

        if self.state == self.OPEN:
            # Check if recovery timeout has elapsed
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = self.HALF_OPEN
                self.logger.info(
                    f"Circuit {self.name} entering HALF_OPEN",
                    event="circuit_half_open",
                )
                return True
            return False

        if self.state == self.HALF_OPEN:
            return True

        return False

    def record_success(self):
        """Record a successful call."""
        if self.state == self.HALF_OPEN:
            self.state = self.CLOSED
            self.failure_count = 0
            self.logger.info(
                f"Circuit {self.name} CLOSED (recovered)",
                event="circuit_closed",
            )
        self.success_count += 1

    def record_failure(self, error=None):
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == self.HALF_OPEN:
            self.state = self.OPEN
            self.logger.warn(
                f"Circuit {self.name} re-OPENED (recovery failed)",
                event="circuit_reopened",
                data={"error": str(error) if error else None},
            )
        elif self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            self.logger.error(
                f"Circuit {self.name} OPENED ({self.failure_count} failures)",
                event="circuit_opened",
                category=ErrorCategory.TRANSIENT,
                data={"failure_count": self.failure_count, "threshold": self.failure_threshold},
            )

    def get_status(self):
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
        }


# ---------------------------------------------------------------------------
# Graceful Degradation — Task Queue
# ---------------------------------------------------------------------------
class TaskQueue:
    """
    File-based queue for tasks that can't be processed immediately.
    Tasks are saved as JSON files in /Logs/queue/ and retried later.
    """

    def __init__(self, queue_dir=QUEUE_DIR, dead_letter_dir=DEAD_LETTER_DIR, logger=None):
        self.queue_dir = Path(queue_dir)
        self.dead_letter_dir = Path(dead_letter_dir)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.dead_letter_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or AuditLogger(component="task_queue")

    def enqueue(self, task_id, task_type, payload, reason="api_down", max_retries=3):
        """Add a task to the retry queue."""
        task = {
            "id": task_id,
            "type": task_type,
            "payload": payload,
            "reason": reason,
            "enqueued_at": datetime.now().isoformat(),
            "retry_count": 0,
            "max_retries": max_retries,
            "status": "queued",
        }

        filepath = self.queue_dir / f"q_{task_id}_{int(time.time())}.json"
        filepath.write_text(json.dumps(task, indent=2, default=str), encoding="utf-8")

        self.logger.queued(f"{task_type}:{task_id}", filepath, reason)
        return filepath

    def dequeue_all(self):
        """Get all queued tasks, sorted by enqueue time."""
        tasks = []
        for f in sorted(self.queue_dir.glob("q_*.json")):
            try:
                task = json.loads(f.read_text(encoding="utf-8"))
                task["_filepath"] = str(f)
                tasks.append(task)
            except (json.JSONDecodeError, OSError):
                continue
        return tasks

    def mark_completed(self, task_filepath):
        """Remove a completed task from the queue."""
        fp = Path(task_filepath)
        if fp.exists():
            fp.unlink()

    def send_to_dead_letter(self, task_filepath, error_msg):
        """Move a permanently failed task to the dead letter queue."""
        fp = Path(task_filepath)
        if not fp.exists():
            return

        task = json.loads(fp.read_text(encoding="utf-8"))
        task["dead_letter_reason"] = error_msg
        task["dead_letter_at"] = datetime.now().isoformat()
        task["status"] = "dead_letter"

        dl_path = self.dead_letter_dir / fp.name
        dl_path.write_text(json.dumps(task, indent=2, default=str), encoding="utf-8")
        fp.unlink()

        self.logger.error(
            f"Task {task['id']} moved to dead letter: {error_msg}",
            event="dead_letter",
            category=ErrorCategory.TRANSIENT,
            data={"task_id": task["id"], "retries": task["retry_count"]},
        )

    def process_queue(self, processor_fn):
        """
        Process all queued tasks.
        processor_fn(task) should return True on success, raise on failure.
        """
        tasks = self.dequeue_all()
        results = {"processed": 0, "failed": 0, "dead_letter": 0}

        for task in tasks:
            task["retry_count"] = task.get("retry_count", 0) + 1
            filepath = task["_filepath"]

            try:
                self.logger.dequeued(f"{task['type']}:{task['id']}")
                processor_fn(task)
                self.mark_completed(filepath)
                results["processed"] += 1
            except Exception as e:
                if task["retry_count"] >= task.get("max_retries", 3):
                    self.send_to_dead_letter(filepath, str(e))
                    results["dead_letter"] += 1
                else:
                    # Update retry count in queue file
                    task_data = {k: v for k, v in task.items() if k != "_filepath"}
                    Path(filepath).write_text(
                        json.dumps(task_data, indent=2, default=str), encoding="utf-8"
                    )
                    results["failed"] += 1

        return results

    def queue_size(self):
        return len(list(self.queue_dir.glob("q_*.json")))

    def dead_letter_size(self):
        return len(list(self.dead_letter_dir.glob("q_*.json")))


# ---------------------------------------------------------------------------
# Error Handler — Unified Interface
# ---------------------------------------------------------------------------
class ErrorHandler:
    """
    High-level error handler that combines retry, circuit breaker,
    queue, and audit logging into a single interface.

    Usage:
        handler = ErrorHandler(component="gmail_watcher")
        result = handler.safe_execute(
            fn=call_gmail_api,
            fallback=lambda e: handler.queue("gmail_fetch", {...}),
            max_retries=3,
        )
    """

    def __init__(self, component="system"):
        self.component = component
        self.logger = AuditLogger(component=component)
        self.queue = TaskQueue(logger=self.logger)
        self.circuits = {}

    def get_circuit(self, name):
        if name not in self.circuits:
            self.circuits[name] = CircuitBreaker(name, logger=self.logger)
        return self.circuits[name]

    def safe_execute(
        self,
        fn: Callable,
        args: tuple = (),
        kwargs: dict = None,
        fallback: Optional[Callable] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        circuit_name: Optional[str] = None,
    ):
        """
        Execute a function with full error handling:
          1. Check circuit breaker
          2. Execute with retry
          3. On permanent failure, call fallback (e.g., queue)
          4. Log everything

        Returns: (success: bool, result: Any, error: Optional[Exception])
        """
        kwargs = kwargs or {}

        # Check circuit breaker
        if circuit_name:
            circuit = self.get_circuit(circuit_name)
            if not circuit.can_execute():
                self.logger.warn(
                    f"Circuit {circuit_name} is OPEN — skipping {fn.__name__}",
                    event="circuit_skip",
                )
                if fallback:
                    return False, fallback(ConnectionError(f"Circuit {circuit_name} open")), None
                return False, None, ConnectionError(f"Circuit {circuit_name} open")

        # Execute with retry
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                result = fn(*args, **kwargs)

                if circuit_name:
                    self.get_circuit(circuit_name).record_success()
                if attempt > 1:
                    self.logger.retry_success(attempt)

                return True, result, None

            except Exception as e:
                last_error = e
                err_category = classify_error(e)

                if circuit_name:
                    self.get_circuit(circuit_name).record_failure(e)

                # Only retry transient errors
                if err_category != ErrorCategory.TRANSIENT:
                    self.logger.error(
                        f"{fn.__name__} failed (non-retryable): {e}",
                        event="execution_failed",
                        category=err_category,
                        error=e,
                    )
                    if fallback:
                        return False, fallback(e), e
                    return False, None, e

                if attempt < max_retries:
                    delay = min(1.0 * (2 ** (attempt - 1)), 30.0)
                    delay += random.uniform(0, delay * 0.5)
                    self.logger.retry_attempt(attempt, max_retries, str(e), int(delay * 1000))
                    time.sleep(delay)
                else:
                    self.logger.retry_exhausted(max_retries, str(e))
                    if fallback:
                        return False, fallback(e), e
                    return False, None, e

        return False, None, last_error

    def enqueue_task(self, task_id, task_type, payload, reason="api_down"):
        """Queue a task for later processing."""
        return self.queue.enqueue(task_id, task_type, payload, reason)

    def process_queued(self, processor_fn):
        """Process all queued tasks."""
        return self.queue.process_queue(processor_fn)

    def get_status(self):
        """Get overall error handler status."""
        return {
            "component": self.component,
            "queue_size": self.queue.queue_size(),
            "dead_letter_size": self.queue.dead_letter_size(),
            "circuits": {
                name: cb.get_status() for name, cb in self.circuits.items()
            },
        }


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------
def run_tests():
    """Simulate 3 error types and recover — Ralph Wiggum loop."""
    import shutil
    import tempfile

    # Fix Windows console encoding
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    MAX_ATTEMPTS = 3
    success = False

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\nRalph Wiggum Iteration #{attempt}")

        passed = 0
        failed = 0

        def check(condition, name):
            nonlocal passed, failed
            if condition:
                passed += 1
                print(f"  PASS: {name}")
            else:
                failed += 1
                print(f"  FAIL: {name}")

        print("=" * 60)
        print("ERROR HANDLING SYSTEM — TEST SUITE")
        print("=" * 60)

        # Temp dirs for isolated testing
        tmp = Path(tempfile.mkdtemp(prefix="error_test_"))
        test_logs = tmp / "Logs"
        test_queue = test_logs / "queue"
        test_dl = test_logs / "dead_letter"
        test_logs.mkdir()
        test_queue.mkdir()
        test_dl.mkdir()

        try:
            # ── Test 1: Error Classification ──
            print("\n[1/12] Error Classification")
            check(classify_error(ConnectionError("refused")) == ErrorCategory.TRANSIENT,
                  "ConnectionError → TRANSIENT")
            check(classify_error(TimeoutError("timeout")) == ErrorCategory.TRANSIENT,
                  "TimeoutError → TRANSIENT")
            check(classify_error(PermissionError("denied")) == ErrorCategory.AUTH,
                  "PermissionError → AUTH")
            check(classify_error(ValueError("invalid")) == ErrorCategory.LOGIC,
                  "ValueError → LOGIC")
            check(classify_error(MemoryError("oom")) == ErrorCategory.SYSTEM,
                  "MemoryError → SYSTEM")

            # Message-based classification
            check(classify_error(Exception("rate limit exceeded")) == ErrorCategory.TRANSIENT,
                  "'rate limit' → TRANSIENT")
            check(classify_error(Exception("401 unauthorized")) == ErrorCategory.AUTH,
                  "'401 unauthorized' → AUTH")
            check(classify_error(Exception("validation failed")) == ErrorCategory.LOGIC,
                  "'validation failed' → LOGIC")

            # ── Test 2: Retryable Detection ──
            print("\n[2/12] Retryable Detection")
            check(is_retryable(ConnectionError("network")) == True,
                  "ConnectionError is retryable")
            check(is_retryable(ValueError("bad input")) == False,
                  "ValueError is NOT retryable")
            check(is_retryable(PermissionError("denied")) == False,
                  "PermissionError is NOT retryable")

            # ── Test 3: Retry Decorator — Transient Recovery ──
            print("\n[3/12] Retry Decorator — Transient Error Recovery")
            call_count_3 = 0

            @retry(max_retries=3, backoff_base=0.01, component="test")
            def flaky_api():
                nonlocal call_count_3
                call_count_3 += 1
                if call_count_3 < 3:
                    raise ConnectionError("Connection refused")
                return "success"

            result = flaky_api()
            check(result == "success", "Recovered after transient errors")
            check(call_count_3 == 3, f"Called {call_count_3} times (expected 3)")

            # ── Test 4: Retry Decorator — Auth Failure (no retry) ──
            print("\n[4/12] Retry Decorator — Auth Error (no retry)")
            call_count_4 = 0

            @retry(max_retries=3, backoff_base=0.01, component="test")
            def auth_fail():
                nonlocal call_count_4
                call_count_4 += 1
                raise PermissionError("403 Forbidden")

            try:
                auth_fail()
                check(False, "Should have raised")
            except PermissionError:
                check(True, "PermissionError raised immediately")
            check(call_count_4 == 1, f"Called only {call_count_4} time (no retry)")

            # ── Test 5: Retry Decorator — Logic Error (no retry) ──
            print("\n[5/12] Retry Decorator — Logic Error (no retry)")
            call_count_5 = 0

            @retry(max_retries=3, backoff_base=0.01, component="test")
            def logic_fail():
                nonlocal call_count_5
                call_count_5 += 1
                raise ValueError("Invalid invoice amount")

            try:
                logic_fail()
            except ValueError:
                check(True, "ValueError raised immediately")
            check(call_count_5 == 1, f"Called only {call_count_5} time (no retry)")

            # ── Test 6: Retry Exhaustion ──
            print("\n[6/12] Retry Exhaustion")
            call_count_6 = 0

            @retry(max_retries=3, backoff_base=0.01, category=ErrorCategory.TRANSIENT, component="test")
            def always_fail():
                nonlocal call_count_6
                call_count_6 += 1
                raise ConnectionError("Always fails")

            try:
                always_fail()
                check(False, "Should have raised")
            except ConnectionError:
                check(True, "ConnectionError raised after retries")
            check(call_count_6 == 3, f"Exhausted all 3 retries ({call_count_6} calls)")

            # ── Test 7: Audit Logger ──
            print("\n[7/12] Audit Logger — JSON Structured Logging")
            logger = AuditLogger(component="test_component", logs_dir=test_logs)
            tid = logger.start_trace()
            check(tid is not None, f"Trace ID generated: {tid}")

            e1 = logger.info("Test info message", event="test_event", data={"key": "value"})
            check(e1["level"] == "INFO", "Info entry level correct")
            check(e1["component"] == "test_component", "Component correct")
            check(e1["trace_id"] == tid, "Trace ID attached")

            e2 = logger.transient("API timeout", data={"endpoint": "/api"})
            check(e2["category"] == ErrorCategory.TRANSIENT, "Transient category")

            e3 = logger.auth_error("Token expired")
            check(e3["category"] == ErrorCategory.AUTH, "Auth category")

            e4 = logger.logic_error("Invalid amount", data={"amount": -100})
            check(e4["category"] == ErrorCategory.LOGIC, "Logic category")

            logger.end_trace()

            # Verify JSONL file
            log_files = list(test_logs.glob("audit_*.jsonl"))
            check(len(log_files) == 1, "JSONL log file created")
            if log_files:
                entries = AuditLogger.read_logs(log_files[0])
                check(len(entries) >= 4, f"At least 4 entries written ({len(entries)})")

                # Filter by category
                transient_entries = AuditLogger.read_logs(
                    log_files[0], category=ErrorCategory.TRANSIENT
                )
                check(len(transient_entries) >= 1, "Can filter by TRANSIENT category")

                # Count by category
                counts = AuditLogger.count_by_category(log_files[0])
                check(ErrorCategory.TRANSIENT in counts, "TRANSIENT in category counts")

            # ── Test 8: Task Queue — Enqueue ──
            print("\n[8/12] Task Queue — Enqueue on API Down")
            queue = TaskQueue(queue_dir=test_queue, dead_letter_dir=test_dl,
                              logger=AuditLogger("queue_test", test_logs))

            qf1 = queue.enqueue("task_001", "gmail_fetch", {"query": "unread"}, reason="api_timeout")
            qf2 = queue.enqueue("task_002", "social_post", {"platform": "twitter"}, reason="rate_limited")
            check(Path(qf1).exists(), "Task 1 queued to file")
            check(Path(qf2).exists(), "Task 2 queued to file")
            check(queue.queue_size() == 2, f"Queue size: {queue.queue_size()}")

            # ── Test 9: Task Queue — Process ──
            print("\n[9/12] Task Queue — Process Queued Tasks")
            process_results = []

            def mock_processor(task):
                process_results.append(task["id"])
                if task["id"] == "task_002":
                    raise ConnectionError("Still down")

            result = queue.process_queue(mock_processor)
            check(result["processed"] == 1, f"Processed: {result['processed']}")
            check("task_001" in process_results, "task_001 processed")
            check(result["failed"] == 1, f"Failed (will retry): {result['failed']}")

            # ── Test 10: Dead Letter Queue ──
            print("\n[10/12] Dead Letter Queue")
            # Process again until max retries exceeded
            for _ in range(5):
                queue.process_queue(mock_processor)

            check(queue.dead_letter_size() >= 1, f"Dead letter items: {queue.dead_letter_size()}")
            dl_files = list(test_dl.glob("q_*.json"))
            if dl_files:
                dl_task = json.loads(dl_files[0].read_text(encoding="utf-8"))
                check(dl_task["status"] == "dead_letter", "Dead letter status set")
                check("dead_letter_reason" in dl_task, "Dead letter reason recorded")

            # ── Test 11: Circuit Breaker ──
            print("\n[11/12] Circuit Breaker")
            cb = CircuitBreaker("gmail_api", failure_threshold=3, recovery_timeout=0.1,
                                logger=AuditLogger("circuit_test", test_logs))

            check(cb.state == CircuitBreaker.CLOSED, "Initial state: CLOSED")
            check(cb.can_execute() == True, "Can execute when CLOSED")

            # Trigger failures
            cb.record_failure(ConnectionError("fail 1"))
            cb.record_failure(ConnectionError("fail 2"))
            check(cb.state == CircuitBreaker.CLOSED, "Still CLOSED after 2 failures")

            cb.record_failure(ConnectionError("fail 3"))
            check(cb.state == CircuitBreaker.OPEN, "OPENED after 3 failures")
            check(cb.can_execute() == False, "Cannot execute when OPEN")

            # Wait for recovery
            time.sleep(0.15)
            check(cb.can_execute() == True, "Can execute after recovery timeout (HALF_OPEN)")
            check(cb.state == CircuitBreaker.HALF_OPEN, "State: HALF_OPEN")

            # Successful recovery
            cb.record_success()
            check(cb.state == CircuitBreaker.CLOSED, "CLOSED after recovery success")

            # ── Test 12: ErrorHandler — safe_execute with fallback ──
            print("\n[12/12] ErrorHandler — safe_execute + Fallback Queue")
            handler = ErrorHandler(component="test_handler")
            handler.queue = TaskQueue(queue_dir=test_queue, dead_letter_dir=test_dl,
                                      logger=AuditLogger("handler_test", test_logs))

            # Success case
            ok, res, err = handler.safe_execute(fn=lambda: "ok")
            check(ok == True, "safe_execute returns success")
            check(res == "ok", "Result returned")
            check(err is None, "No error")

            # Failure with fallback
            fallback_called = []

            def fallback_fn(e):
                fallback_called.append(str(e))
                return "queued"

            ok2, res2, err2 = handler.safe_execute(
                fn=lambda: (_ for _ in ()).throw(ValueError("bad")),
                fallback=fallback_fn,
                max_retries=1,
            )
            check(ok2 == False, "safe_execute returns failure")
            check(res2 == "queued", "Fallback result returned")
            check(len(fallback_called) == 1, "Fallback was called")

            # Status check
            status = handler.get_status()
            check(status["component"] == "test_handler", "Status has component")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # ── Results ──
        print("\n" + "=" * 60)
        print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
        print("=" * 60)

        if failed == 0:
            success = True
            break

    if success:
        print("\nAll tests passed!")
        return True
    else:
        print(f"\nTests failing after {MAX_ATTEMPTS} attempts.")
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if "--test" in sys.argv:
        ok = run_tests()
        sys.exit(0 if ok else 1)
    else:
        print("Usage: python retry_handler.py --test")
        print("Import this module to use retry, ErrorHandler, etc.")
