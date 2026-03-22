#!/usr/bin/env python3
"""
ClawTeam orchestrator.
Manages swarm lifecycle: create → decompose → run pattern → synthesize → output contract.
"""
from __future__ import annotations
import json
import os
import re
import time
import datetime
from pathlib import Path

from clawteam import bus as _default_bus
from clawteam.runner import run_agent
from clawteam.decomposer import decompose
from clawteam.patterns import run_sequential, run_parallel, run_debate, run_hierarchy
from clawteam.registry import get_agent

BUILD_RESULTS_DIR = Path(os.environ.get("OPENCLAW_BUILD_RESULTS",
                         Path.home() / "openclaw" / "build-results"))

_SYNTH_PRIMARY  = "qwen3:32b"
_SYNTH_FALLBACK = "qwen3:30b"


def _make_swarm_id(task: str) -> str:
    ts = int(time.time())
    slug = re.sub(r"[^a-z0-9]+", "-", task.lower())[:20].strip("-")
    return f"swarm-{ts}-{slug}"


def _synthesize(subtask_results: list) -> str:
    """Call SYNTHESIZER (qwen3:32b, fallback qwen3:30b) to merge completed results."""
    completed = [r for r in subtask_results if r.get("status") == "complete"]
    if not completed:
        return ""
    combined = "\n\n".join(
        f"## {r.get('agent', 'Agent')}\n{r['result']}" for r in completed
    )
    prompt = f"Combine these research findings into one coherent, structured report:\n\n{combined}"
    result = run_agent("SYNTHESIZER", _SYNTH_PRIMARY, prompt)
    if result.startswith("[ERROR]"):
        result = run_agent("SYNTHESIZER", _SYNTH_FALLBACK, prompt)
    return result


def _write_output_contract(swarm_id: str, task: str, pattern: str, status: str,
                            subtasks: list, synthesis: str,
                            created_at: str, bus) -> Path:
    out_dir = BUILD_RESULTS_DIR / swarm_id
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = swarm_id.replace("swarm-", "")
    result_file = out_dir / f"result-{slug}.md"

    # Write human-readable result
    lines = [f"# Swarm Result: {task}",
             f"**Pattern:** {pattern} | **Status:** {status} | **Date:** {datetime.date.today()}",
             "", "## Synthesized Output", synthesis or "(synthesis unavailable)", ""]
    for sub in subtasks:
        lines += [f"## {sub.get('agent','?')} — {sub['id']}",
                  sub.get("result") or "(no result)", ""]
    result_file.write_text("\n".join(lines))

    # Write machine-readable contract
    contract = {
        "swarm_id": swarm_id,
        "task": task,
        "pattern": pattern,
        "status": status,
        "created_at": created_at,
        "completed_at": datetime.datetime.utcnow().isoformat(),
        "subtask_ids": [s["id"] for s in subtasks],
        "subtask_statuses": {s["id"]: s["status"] for s in subtasks},
        "result_file": str(result_file.resolve()),
    }
    (out_dir / "output-contract.json").write_text(json.dumps(contract, indent=2))
    return result_file


def run_swarm(task: str, pattern=None, bus=None, notify: bool = False) -> str:
    """
    Create and run a new swarm. Returns swarm_id.
    """
    if bus is None:
        bus = _default_bus
    swarm_id = _make_swarm_id(task)
    bus.create_swarm(swarm_id, task, pattern or "parallel")
    bus.update_swarm_status(swarm_id, "running")
    created_at = bus.get_swarm(swarm_id)["created_at"]

    # Decompose
    decomp = decompose(task)
    effective_pattern = pattern or decomp["pattern"]
    sub_defs = decomp["subtasks"]

    # Insert subtasks
    for idx, sub in enumerate(sub_defs):
        sub_id = f"{swarm_id}_{idx}"
        bus.insert_subtask(sub_id, swarm_id, sub["agent"], sub["model"],
                           sub["prompt"], sub.get("depends_on"))
        sub["id"] = sub_id

    # Run pattern
    synthesis = ""
    subtask_results = []

    try:
        if effective_pattern == "sequential":
            subtasks_db = bus.list_subtasks(swarm_id)
            raw = run_sequential(subtasks_db, bus, runner=run_agent)
            subtask_results = raw
            synthesis = _synthesize(raw)

        elif effective_pattern == "parallel":
            subtasks_db = bus.list_subtasks(swarm_id)
            def synthesizer(completed):
                return _synthesize(completed)
            result = run_parallel(subtasks_db, bus, runner=run_agent, synthesizer=synthesizer)
            synthesis = result["synthesis"]
            subtask_results = result["subtask_results"]

        elif effective_pattern == "debate":
            verdict = run_debate(swarm_id, task, bus, runner=run_agent)
            subtask_results = [{"id": f"{swarm_id}_verdict", "agent": "JUDGE",
                                 "result": verdict, "status": "complete"}]
            synthesis = verdict

        elif effective_pattern == "hierarchy":
            result = run_hierarchy(swarm_id, task, bus, runner=run_agent)
            subtask_results = result["worker_results"]
            synthesis = _synthesize(subtask_results)

    except Exception as e:
        synthesis = f"[ERROR] Pattern execution failed: {e}"

    # Determine final status
    completed = [r for r in subtask_results if r.get("status") == "complete"]
    if synthesis.startswith("[ERROR]") or not synthesis:
        status = "partial"
    elif not subtask_results or not completed:
        status = "failed"
    else:
        status = "complete"

    # All subtasks for final contract
    all_subtasks = bus.list_subtasks(swarm_id)

    _write_output_contract(swarm_id, task, effective_pattern, status,
                           all_subtasks, synthesis, created_at, bus)
    bus.update_swarm_status(swarm_id, status, result=synthesis)

    if notify:
        _send_telegram_notify(swarm_id, task, status)

    return swarm_id


def resume_swarm(swarm_id: str, bus=None, notify: bool = False) -> str:
    """
    Resume an interrupted swarm. Returns swarm_id.
    """
    if bus is None:
        bus = _default_bus
    swarm = bus.get_swarm(swarm_id)
    if swarm is None:
        raise ValueError(f"Swarm {swarm_id!r} not found in DB.")
    if swarm["status"] == "complete":
        print(f"Swarm {swarm_id} is already complete.")
        return swarm_id

    # Reset any interrupted running subtasks
    bus.reset_running_subtasks(swarm_id)
    bus.update_swarm_status(swarm_id, "running")

    # Re-run remaining subtasks (only pending ones)
    pending = [s for s in bus.list_subtasks(swarm_id) if s["status"] == "pending"]
    pattern = swarm["pattern"]
    synthesis = ""

    if pending:
        if pattern == "sequential":
            raw = run_sequential(pending, bus, runner=run_agent)
            synthesis = _synthesize(raw)
        elif pattern == "parallel":
            result = run_parallel(pending, bus, runner=run_agent,
                                  synthesizer=lambda c: _synthesize(c))
            synthesis = result["synthesis"]
        # debate and hierarchy don't have partial resume — re-run all pending as parallel
        else:
            result = run_parallel(pending, bus, runner=run_agent,
                                  synthesizer=lambda c: _synthesize(c))
            synthesis = result["synthesis"]

    all_subtasks = bus.list_subtasks(swarm_id)
    completed = [s for s in all_subtasks if s["status"] == "complete"]
    status = "complete" if completed and not synthesis.startswith("[ERROR]") else "partial"

    _write_output_contract(swarm_id, swarm["task"], pattern, status,
                           all_subtasks, synthesis, swarm["created_at"], bus)
    bus.update_swarm_status(swarm_id, status, result=synthesis)

    if notify:
        _send_telegram_notify(swarm_id, swarm["task"], status)

    return swarm_id


def _send_telegram_notify(swarm_id: str, task: str, status: str) -> None:
    """Send Telegram completion ping. Requires TELEGRAM_TOKEN + TELEGRAM_CHAT_ID in env."""
    import requests as req
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    emoji = "✅" if status == "complete" else "⚠️" if status == "partial" else "❌"
    text = f"{emoji} Swarm {status}: {swarm_id}\nTask: {task[:100]}"
    try:
        req.post(f"https://api.telegram.org/bot{token}/sendMessage",
                 json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception:
        pass  # Notification failure is non-fatal
