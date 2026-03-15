"""
ralph_wiggum/stop_hook.py — Claude Code Stop Hook
Gold Tier — Panaversity AI Employee Hackathon 2026

Intercepts Claude Code exit, checks task completion, re-injects if needed.

Hook specification:
- Reads JSON from stdin: {"session_id": "...", "stop_hook_active": bool, ...}
- Writes JSON to stdout: {"decision": "block"|"allow", "reason": "..."}
- Exit code 2 prevents Claude Code from stopping
- Exit code 0 allows Claude Code to stop
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).parent.parent.resolve()
VAULT_PATH = Path(os.environ.get("VAULT_PATH", str(BASE_DIR / "vault")))
STATE_FILE = BASE_DIR / ".ralph_state.json"
DONE_DIR = VAULT_PATH / "Done"
NEEDS_ACTION_DIR = VAULT_PATH / "Needs_Action"

MAX_ITERATIONS = 10


def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {"task_file": None, "iteration": 0, "previous_output": "",
                "started_at": datetime.utcnow().isoformat() + "Z"}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"task_file": None, "iteration": 0, "previous_output": "",
                "started_at": datetime.utcnow().isoformat() + "Z"}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"[ralph_stop_hook] Warning: could not write state: {exc}", file=sys.stderr)


def _reset_state() -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink(missing_ok=True)


def _is_task_done(task_file: Optional[str]) -> bool:
    if not task_file:
        return True
    task_name = Path(task_file).name
    if DONE_DIR.exists():
        for done_file in DONE_DIR.iterdir():
            if task_name in done_file.name:
                return True
    needs_action_file = NEEDS_ACTION_DIR / task_name
    if not needs_action_file.exists():
        return True
    return False


def _build_reinjection_prompt(task_file: Optional[str], previous_output: str, iteration: int) -> str:
    task_name = Path(task_file).name if task_file else "unknown_task"
    return "\n".join([
        f"[Ralph Wiggum Loop — Iteration {iteration}/{MAX_ITERATIONS}]",
        "",
        f"Task '{task_name}' has NOT been moved to vault/Done/ yet.",
        "The previous iteration did not complete the task.",
        "",
        "Previous output context:",
        "---",
        previous_output[-2000:] if previous_output else "(no previous output captured)",
        "---",
        "",
        "Please continue working on the task. Specifically:",
        f"1. Read the task file at: {NEEDS_ACTION_DIR / task_name}",
        "2. Complete the required action",
        "3. Move the task file to vault/Done/ when finished",
        "4. If the action requires human approval, move it to vault/Pending_Approval/",
        "",
        "Do NOT stop until the task file is no longer in vault/Needs_Action/.",
    ])


def main() -> int:
    try:
        raw_input = sys.stdin.read()
        hook_data: Dict[str, Any] = json.loads(raw_input) if raw_input.strip() else {}
    except (json.JSONDecodeError, OSError):
        hook_data = {}

    previous_output: str = hook_data.get("previous_output", "")
    stop_hook_active: bool = bool(hook_data.get("stop_hook_active", False))

    state = _load_state()
    task_file: Optional[str] = state.get("task_file")
    iteration: int = int(state.get("iteration", 0))

    if stop_hook_active and previous_output:
        state["previous_output"] = previous_output
        _save_state(state)

    if iteration >= MAX_ITERATIONS:
        reason = (f"[Ralph Wiggum] Max iterations ({MAX_ITERATIONS}) reached for "
                  f"'{task_file}'. Allowing exit.")
        print(json.dumps({"decision": "allow", "reason": reason}), flush=True)
        _reset_state()
        return 0

    if _is_task_done(task_file):
        reason = f"[Ralph Wiggum] Task '{task_file}' complete. Allowing exit."
        print(json.dumps({"decision": "allow", "reason": reason}), flush=True)
        _reset_state()
        return 0

    iteration += 1
    state["iteration"] = iteration
    state["previous_output"] = previous_output or state.get("previous_output", "")
    state["last_check"] = datetime.utcnow().isoformat() + "Z"
    _save_state(state)

    prompt = _build_reinjection_prompt(task_file, state["previous_output"], iteration)
    print(json.dumps({"decision": "block", "reason": prompt}, ensure_ascii=False), flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
