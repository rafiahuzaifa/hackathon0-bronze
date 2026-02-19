#!/usr/bin/env python3
"""
ralph_wiggum.py — Ralph Wiggum Stop-Hook Engine

"I'm in danger!" — Ralph Wiggum

Intercepts task completion, checks if task files have been moved to /Done,
re-injects the prompt with previous output if not. Implements the iterative
"Ralph Wiggum loop" pattern used across the AI Employee system.

Core Logic:
  1. Scan /Needs_Action (or custom inbox) for pending .md task files
  2. Execute a processing step (move file → /Tasks/Done when complete)
  3. After each step, check: are ALL task files in /Done?
  4. If not, re-inject prompt with context from previous output
  5. Repeat until done or max_iterations reached

Completion Detection:
  - File-movement: task file moved from inbox → /Done
  - YAML frontmatter: status field changes to "done" or "completed"
  - Marker file: .ralph_complete sentinel in task dir

Usage:
  python ralph_wiggum.py                          # Process pending tasks
  python ralph_wiggum.py --test                   # Run simulation tests
  python ralph_wiggum.py --inbox /path/to/inbox   # Custom inbox
  python ralph_wiggum.py --max-iter 5             # Custom max iterations
  python ralph_wiggum.py --dry-run                # Don't move files
"""

import os
import re
import sys
import json
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VAULT_DIR = Path("d:/hackathon0/hackathon/AI_Employee_Vault")
DEFAULT_INBOX = VAULT_DIR / "Needs_Action"
TASKS_DIR = VAULT_DIR / "Tasks"
DONE_DIR = TASKS_DIR / "Done"
RALPH_STATE_FILE = VAULT_DIR / ".ralph_state.json"
LOG_FILE = VAULT_DIR / "ralph_wiggum.log"
MAX_ITERATIONS = 10

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(
            open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)
            if sys.platform == "win32"
            else sys.stdout
        ),
    ],
)
logger = logging.getLogger("ralph_wiggum")


# ---------------------------------------------------------------------------
# Ralph Wiggum State
# ---------------------------------------------------------------------------
class RalphState:
    """Persistent state for the Ralph Wiggum loop."""

    def __init__(self, state_file=RALPH_STATE_FILE):
        self.state_file = Path(state_file)
        self.data = {
            "iteration": 0,
            "max_iterations": MAX_ITERATIONS,
            "started_at": None,
            "tasks": {},       # filename -> {status, moved_at, iterations_spent}
            "history": [],     # [{iteration, action, result, timestamp}]
            "completed": False,
            "exit_reason": None,
        }
        self._load()

    def _load(self):
        if self.state_file.exists():
            try:
                self.data = json.loads(self.state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        self.state_file.write_text(
            json.dumps(self.data, indent=2, default=str), encoding="utf-8"
        )

    def reset(self):
        self.data = {
            "iteration": 0,
            "max_iterations": MAX_ITERATIONS,
            "started_at": datetime.now().isoformat(),
            "tasks": {},
            "history": [],
            "completed": False,
            "exit_reason": None,
        }
        self.save()

    @property
    def iteration(self):
        return self.data["iteration"]

    @property
    def is_complete(self):
        return self.data["completed"]

    def record_task(self, filename, status="pending"):
        if filename not in self.data["tasks"]:
            self.data["tasks"][filename] = {
                "status": status,
                "first_seen": datetime.now().isoformat(),
                "moved_at": None,
                "iterations_spent": 0,
            }
        self.data["tasks"][filename]["status"] = status
        self.data["tasks"][filename]["iterations_spent"] += 1

    def mark_done(self, filename):
        if filename in self.data["tasks"]:
            self.data["tasks"][filename]["status"] = "done"
            self.data["tasks"][filename]["moved_at"] = datetime.now().isoformat()

    def add_history(self, action, result):
        self.data["history"].append({
            "iteration": self.data["iteration"],
            "action": action,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        })

    def pending_tasks(self):
        return [
            f for f, t in self.data["tasks"].items() if t["status"] != "done"
        ]

    def all_done(self):
        tasks = self.data["tasks"]
        return len(tasks) > 0 and all(t["status"] == "done" for t in tasks.values())


# ---------------------------------------------------------------------------
# File-Movement Completion Detection
# ---------------------------------------------------------------------------
def scan_inbox(inbox_dir):
    """Scan inbox directory for .md task files."""
    inbox = Path(inbox_dir)
    if not inbox.exists():
        return []
    return sorted([f for f in inbox.iterdir() if f.suffix == ".md"])


def is_task_complete(filepath):
    """
    Check if a task file is marked complete via YAML frontmatter.
    Looks for status: done|completed|closed in frontmatter.
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        frontmatter = fm_match.group(1)
        status_match = re.search(r"status:\s*(\w+)", frontmatter)
        if status_match:
            return status_match.group(1).lower() in ("done", "completed", "closed")
    return False


def is_in_done(filename, done_dir=DONE_DIR):
    """Check if a file has been moved to /Done."""
    return (Path(done_dir) / filename).exists()


def move_to_done(filepath, done_dir=DONE_DIR):
    """Move a completed task file to /Done directory."""
    done = Path(done_dir)
    done.mkdir(parents=True, exist_ok=True)
    dest = done / filepath.name
    shutil.move(str(filepath), str(dest))
    logger.info(f"  Moved {filepath.name} -> /Tasks/Done/")
    return dest


# ---------------------------------------------------------------------------
# Task Processor
# ---------------------------------------------------------------------------
def process_task(filepath, dry_run=False, done_dir=DONE_DIR):
    """
    Process a single task file.

    In a real system, this would trigger Claude/MCP to handle the task.
    For the Ralph Wiggum hook, we:
      1. Read the file
      2. Check if it's actionable
      3. Mark it as processed (update YAML frontmatter)
      4. Move to /Done if complete

    Returns: (processed: bool, output: str)
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return False, f"Error reading {filepath.name}: {e}"

    filename = filepath.name
    output_lines = [f"Processing: {filename}"]

    # Parse frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if fm_match:
        frontmatter = fm_match.group(1)
        body = fm_match.group(2)

        # Check current status
        status_match = re.search(r"status:\s*(\w+)", frontmatter)
        current_status = status_match.group(1) if status_match else "unknown"

        if current_status in ("done", "completed", "closed"):
            output_lines.append(f"  Already complete (status: {current_status})")
            return True, "\n".join(output_lines)

        # Update status to "done" in frontmatter
        new_frontmatter = re.sub(
            r"status:\s*\w+",
            "status: done",
            frontmatter,
        )
        if "status:" not in new_frontmatter:
            new_frontmatter += "\nstatus: done"

        new_frontmatter += f"\nprocessed_at: {datetime.now().isoformat()}"
        new_content = f"---\n{new_frontmatter}\n---\n{body}"

        if not dry_run:
            filepath.write_text(new_content, encoding="utf-8")
            output_lines.append(f"  Updated frontmatter: status -> done")
        else:
            output_lines.append(f"  [DRY RUN] Would update frontmatter")

    else:
        # No frontmatter — add it
        new_content = (
            f"---\nstatus: done\nprocessed_at: {datetime.now().isoformat()}\n---\n\n"
            + content
        )
        if not dry_run:
            filepath.write_text(new_content, encoding="utf-8")
            output_lines.append(f"  Added frontmatter with status: done")
        else:
            output_lines.append(f"  [DRY RUN] Would add frontmatter")

    # Move to /Done
    if not dry_run:
        move_to_done(filepath, done_dir)
        output_lines.append(f"  File moved to /Tasks/Done/")
    else:
        output_lines.append(f"  [DRY RUN] Would move to /Tasks/Done/")

    return True, "\n".join(output_lines)


# ---------------------------------------------------------------------------
# Ralph Wiggum Loop — Core Engine
# ---------------------------------------------------------------------------
def ralph_loop(
    inbox_dir=DEFAULT_INBOX,
    done_dir=DONE_DIR,
    max_iterations=MAX_ITERATIONS,
    dry_run=False,
    task_filter=None,
):
    """
    The Ralph Wiggum loop:
      - Scan inbox for tasks
      - Process each task
      - Check if all tasks are in /Done
      - If not, re-inject and iterate
      - Stop when all done OR max_iterations reached

    Returns: {success, iterations, tasks_processed, tasks_remaining, history}
    """
    state = RalphState()
    state.reset()
    state.data["max_iterations"] = max_iterations

    inbox = Path(inbox_dir)
    done = Path(done_dir)
    done.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("RALPH WIGGUM LOOP — START")
    logger.info(f"  Inbox: {inbox}")
    logger.info(f"  Done: {done}")
    logger.info(f"  Max iterations: {max_iterations}")
    logger.info(f"  Dry run: {dry_run}")
    logger.info("=" * 60)

    for iteration in range(1, max_iterations + 1):
        state.data["iteration"] = iteration
        logger.info(f"\n--- Iteration #{iteration}/{max_iterations} ---")

        # Scan inbox
        pending_files = scan_inbox(inbox)
        if task_filter:
            pending_files = [f for f in pending_files if task_filter(f)]

        # Also check state for files we've seen but might still be pending
        for f in pending_files:
            state.record_task(f.name)

        # Check if any files are already in done that we tracked
        for fname in list(state.data["tasks"].keys()):
            if is_in_done(fname, done):
                state.mark_done(fname)

        pending = state.pending_tasks()
        logger.info(f"  Pending tasks: {len(pending)}")
        logger.info(f"  Done tasks: {len(state.data['tasks']) - len(pending)}")

        if not pending_files and state.all_done():
            logger.info("  All tasks complete!")
            state.data["completed"] = True
            state.data["exit_reason"] = "all_tasks_done"
            state.add_history("check_completion", "ALL DONE")
            state.save()
            break

        if not pending_files and not state.data["tasks"]:
            logger.info("  No tasks found in inbox.")
            state.data["completed"] = True
            state.data["exit_reason"] = "empty_inbox"
            state.add_history("check_inbox", "EMPTY")
            state.save()
            break

        # Process each pending file
        processed_count = 0
        for filepath in pending_files:
            logger.info(f"\n  [{processed_count + 1}/{len(pending_files)}] {filepath.name}")

            success, output = process_task(filepath, dry_run=dry_run, done_dir=done)
            state.add_history(
                f"process:{filepath.name}",
                "OK" if success else "FAIL",
            )

            if success:
                processed_count += 1
                state.mark_done(filepath.name)
                logger.info(output)
            else:
                logger.warning(f"  Failed: {output}")

        # Re-check completion
        if state.all_done():
            logger.info(f"\n  All tasks processed after iteration #{iteration}")
            state.data["completed"] = True
            state.data["exit_reason"] = "all_tasks_done"
            state.save()
            break

        # Not done yet — re-inject context for next iteration
        remaining = state.pending_tasks()
        logger.info(
            f"\n  Iteration #{iteration} complete. "
            f"Processed: {processed_count}, Remaining: {len(remaining)}"
        )

        if remaining:
            logger.info(f"  Re-injecting for next iteration. Remaining: {remaining}")
            state.add_history(
                "reinject",
                f"{len(remaining)} tasks remaining",
            )

        state.save()

    # Final status
    if not state.data["completed"]:
        state.data["exit_reason"] = "max_iterations_reached"
        state.save()

    total_tasks = len(state.data["tasks"])
    done_tasks = total_tasks - len(state.pending_tasks())

    logger.info("\n" + "=" * 60)
    logger.info("RALPH WIGGUM LOOP — COMPLETE")
    logger.info(f"  Iterations: {state.iteration}/{max_iterations}")
    logger.info(f"  Tasks: {done_tasks}/{total_tasks} done")
    logger.info(f"  Exit reason: {state.data['exit_reason']}")
    logger.info(f"  Success: {state.data['completed']}")
    logger.info("=" * 60)

    return {
        "success": state.data["completed"],
        "iterations": state.iteration,
        "max_iterations": max_iterations,
        "tasks_processed": done_tasks,
        "tasks_total": total_tasks,
        "tasks_remaining": state.pending_tasks(),
        "exit_reason": state.data["exit_reason"],
        "history": state.data["history"],
        "state": state.data,
    }


# ---------------------------------------------------------------------------
# Generate re-injection prompt
# ---------------------------------------------------------------------------
def build_reinject_prompt(state_data, previous_output=""):
    """
    Build the re-injection prompt for Claude Code.
    This is the hook payload when the loop hasn't completed.
    """
    pending = [
        f for f, t in state_data["tasks"].items() if t["status"] != "done"
    ]
    done = [
        f for f, t in state_data["tasks"].items() if t["status"] == "done"
    ]

    prompt = [
        f"## Ralph Wiggum Re-injection — Iteration #{state_data['iteration'] + 1}",
        f"",
        f"Previous iteration processed {len(done)} task(s) but {len(pending)} remain.",
        f"",
        f"### Completed:",
    ]
    for f in done:
        prompt.append(f"- [x] {f}")

    prompt.append(f"\n### Still Pending:")
    for f in pending:
        iterations = state_data["tasks"][f].get("iterations_spent", 0)
        prompt.append(f"- [ ] {f} (attempted {iterations}x)")

    if previous_output:
        prompt.extend([
            f"",
            f"### Previous Output:",
            f"```",
            previous_output[-2000:],  # Last 2000 chars to avoid overflow
            f"```",
        ])

    prompt.extend([
        f"",
        f"Continue processing the pending tasks. Move each to /Tasks/Done when complete.",
        f"Iteration {state_data['iteration'] + 1} of {state_data['max_iterations']}.",
    ])

    return "\n".join(prompt)


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------
def run_tests():
    """Simulation test suite — Ralph Wiggum loop on 3 fake .md files."""
    import tempfile

    MAX_ATTEMPTS = 3
    success = False

    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.info(f"\nRalph Wiggum Test — Attempt #{attempt}")

        passed = 0
        failed = 0

        def check(condition, name):
            nonlocal passed, failed
            if condition:
                passed += 1
                logger.info(f"  PASS: {name}")
            else:
                failed += 1
                logger.info(f"  FAIL: {name}")

        logger.info("=" * 60)
        logger.info("RALPH WIGGUM STOP-HOOK — TEST SUITE")
        logger.info("=" * 60)

        # Create temp directories
        tmp = Path(tempfile.mkdtemp(prefix="ralph_test_"))
        test_inbox = tmp / "inbox"
        test_done = tmp / "done"
        test_inbox.mkdir()
        test_done.mkdir()

        try:
            # ── Test 1: Create 3 fake task files ──
            logger.info("\n[1/10] Create 3 Fake Task Files")
            tasks = [
                {
                    "name": "task_review_invoice.md",
                    "content": "---\ntask: Review invoice #4821\nstatus: pending\ncategory: finance\n---\n\n# Review Invoice #4821\n\nAmount: $750\nVendor: Office Supplies Co.\n",
                },
                {
                    "name": "task_respond_client.md",
                    "content": "---\ntask: Respond to Acme Corp inquiry\nstatus: pending\ncategory: communication\n---\n\n# Respond to Acme Corp\n\nClient asked about Q2 timeline.\n",
                },
                {
                    "name": "task_update_report.md",
                    "content": "---\ntask: Update weekly report\nstatus: pending\ncategory: reporting\n---\n\n# Update Weekly Report\n\nAdd this week's metrics to the report.\n",
                },
            ]

            for t in tasks:
                (test_inbox / t["name"]).write_text(t["content"], encoding="utf-8")

            inbox_files = list(test_inbox.glob("*.md"))
            check(len(inbox_files) == 3, f"Created {len(inbox_files)} task files")
            for t in tasks:
                check((test_inbox / t["name"]).exists(), f"File exists: {t['name']}")

            # ── Test 2: Scan inbox ──
            logger.info("\n[2/10] Scan Inbox")
            scanned = scan_inbox(test_inbox)
            check(len(scanned) == 3, f"Scanned {len(scanned)} files")

            # ── Test 3: File-movement detection (before) ──
            logger.info("\n[3/10] File-Movement Detection (Before)")
            for t in tasks:
                check(
                    not is_in_done(t["name"], test_done),
                    f"{t['name']} NOT in /Done (correct)",
                )

            # ── Test 4: YAML status detection ──
            logger.info("\n[4/10] YAML Status Detection")
            for t in tasks:
                filepath = test_inbox / t["name"]
                check(
                    not is_task_complete(filepath),
                    f"{t['name']} status is pending (correct)",
                )

            # ── Test 5: Process single task ──
            logger.info("\n[5/10] Process Single Task")
            first_file = test_inbox / tasks[0]["name"]
            ok, output = process_task(first_file, dry_run=False, done_dir=test_done)
            check(ok, f"Task processed: {tasks[0]['name']}")
            check(
                is_in_done(tasks[0]["name"], test_done),
                f"{tasks[0]['name']} moved to /Done",
            )
            check(
                not (test_inbox / tasks[0]["name"]).exists(),
                f"{tasks[0]['name']} removed from inbox",
            )

            # Verify frontmatter was updated
            done_file = test_done / tasks[0]["name"]
            done_content = done_file.read_text(encoding="utf-8")
            check("status: done" in done_content, "Frontmatter updated to status: done")
            check("processed_at:" in done_content, "Processed timestamp added")

            # ── Test 6: Ralph Loop — Full Run ──
            logger.info("\n[6/10] Ralph Loop — Full Run (2 remaining tasks)")
            remaining_before = list(test_inbox.glob("*.md"))
            check(len(remaining_before) == 2, f"{len(remaining_before)} tasks remain in inbox")

            result = ralph_loop(
                inbox_dir=test_inbox,
                done_dir=test_done,
                max_iterations=5,
                dry_run=False,
            )
            check(result["success"], "Ralph loop completed successfully")
            check(result["exit_reason"] == "all_tasks_done", f"Exit: {result['exit_reason']}")
            check(
                result["tasks_processed"] == 2,
                f"Processed {result['tasks_processed']} tasks",
            )

            # ── Test 7: All files in /Done ──
            logger.info("\n[7/10] All Files in /Done")
            done_files = list(test_done.glob("*.md"))
            check(len(done_files) == 3, f"{len(done_files)} files in /Done")
            for t in tasks:
                check(is_in_done(t["name"], test_done), f"{t['name']} in /Done")

            # Inbox should be empty
            remaining = list(test_inbox.glob("*.md"))
            check(len(remaining) == 0, f"Inbox empty ({len(remaining)} files)")

            # ── Test 8: Re-injection Prompt ──
            logger.info("\n[8/10] Re-injection Prompt Generation")
            # Simulate a partial state
            mock_state = {
                "iteration": 2,
                "max_iterations": 10,
                "tasks": {
                    "file_a.md": {"status": "done", "iterations_spent": 1},
                    "file_b.md": {"status": "pending", "iterations_spent": 2},
                    "file_c.md": {"status": "pending", "iterations_spent": 1},
                },
            }
            prompt = build_reinject_prompt(mock_state, "Previous output line 1\nLine 2")
            check("Iteration #3" in prompt, "Prompt has next iteration number")
            check("file_a.md" in prompt, "Prompt lists completed file")
            check("file_b.md" in prompt, "Prompt lists pending file_b")
            check("file_c.md" in prompt, "Prompt lists pending file_c")
            check("attempted 2x" in prompt, "Prompt shows attempt count")
            check("Previous Output" in prompt, "Prompt includes previous output")

            # ── Test 9: Max iteration guard ──
            logger.info("\n[9/10] Max Iteration Guard")
            # Create a task that won't process (simulate stuck)
            stuck_inbox = tmp / "stuck_inbox"
            stuck_done = tmp / "stuck_done"
            stuck_inbox.mkdir()
            stuck_done.mkdir()

            # Create a read-only task (will fail to process on move)
            stuck_file = stuck_inbox / "stuck_task.md"
            stuck_file.write_text(
                "---\ntask: Stuck task\nstatus: pending\n---\n\nThis will process normally\n",
                encoding="utf-8",
            )

            # Run with max_iterations=2 — should complete in 1
            result2 = ralph_loop(
                inbox_dir=stuck_inbox,
                done_dir=stuck_done,
                max_iterations=2,
            )
            check(
                result2["iterations"] <= 2,
                f"Respected max iterations ({result2['iterations']})",
            )
            check(result2["success"], "Even single-task loop succeeds")

            # ── Test 10: State Persistence ──
            logger.info("\n[10/10] State Persistence")
            state = RalphState(tmp / ".ralph_test_state.json")
            state.reset()
            state.record_task("test_file.md", "pending")
            state.data["iteration"] = 3
            state.save()

            # Reload
            state2 = RalphState(tmp / ".ralph_test_state.json")
            check(state2.iteration == 3, f"Iteration persisted: {state2.iteration}")
            check(
                "test_file.md" in state2.data["tasks"],
                "Task persisted in state",
            )
            state2.mark_done("test_file.md")
            check(state2.all_done(), "all_done() works after mark_done()")

            # History
            state2.add_history("test_action", "test_result")
            check(
                len(state2.data["history"]) == 1,
                "History recorded",
            )
            check(
                state2.data["history"][0]["action"] == "test_action",
                "History action correct",
            )

        finally:
            # Cleanup temp
            shutil.rmtree(tmp, ignore_errors=True)

        # ── Results ──
        logger.info("\n" + "=" * 60)
        logger.info(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
        logger.info("=" * 60)

        if failed == 0:
            success = True
            break

    if success:
        logger.info("\nAll tests passed!")
        return True
    else:
        logger.info(f"\nTests failing after {MAX_ATTEMPTS} attempts.")
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    args = sys.argv[1:]

    if "--test" in args:
        ok = run_tests()
        sys.exit(0 if ok else 1)

    # Parse args
    inbox = DEFAULT_INBOX
    max_iter = MAX_ITERATIONS
    dry_run = "--dry-run" in args

    for i, a in enumerate(args):
        if a == "--inbox" and i + 1 < len(args):
            inbox = Path(args[i + 1])
        elif a == "--max-iter" and i + 1 < len(args):
            max_iter = int(args[i + 1])

    result = ralph_loop(
        inbox_dir=inbox,
        max_iterations=max_iter,
        dry_run=dry_run,
    )

    if result["success"]:
        print(f"\nRalph Wiggum: All {result['tasks_total']} tasks done in {result['iterations']} iteration(s).")
    else:
        print(f"\nRalph Wiggum: {result['tasks_remaining']} tasks remain after {result['iterations']} iterations.")
        sys.exit(1)
