#!/usr/bin/env python3
"""
ClawTeam swarm patterns.
Each pattern takes subtasks + bus and dispatches agent calls via runner.
"""
from __future__ import annotations
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional, List

from clawteam import bus as _bus_mod
from clawteam.runner import run_agent
from clawteam.registry import get_agent

_MAX_WORKERS = 3
_DEP_POLL_INTERVAL = 0.5  # seconds


# ── Dependency check ──────────────────────────────────────────────────────────

def _deps_satisfied(subtask: dict, bus) -> object:
    """
    Returns True if all dependencies are complete.
    Returns False if any are still pending/running.
    Returns "failed" if any dependency has failed (caller should cascade).
    Returns True if depends_on is None or empty.
    """
    depends_on = subtask.get("depends_on")
    if not depends_on:
        return True
    dep_ids = [d.strip() for d in depends_on.split(",") if d.strip()]
    for dep_id in dep_ids:
        dep = bus.get_subtask(dep_id)
        if dep is None:
            return False  # not yet inserted — treat as pending
        if dep["status"] == "complete":
            continue
        if dep["status"] == "failed":
            return "failed"
        return False  # pending or running
    return True


def _ensure_subtask_in_bus(subtask: dict, bus) -> None:
    """Insert subtask into bus if not already present (call on main thread only)."""
    existing = bus.get_subtask(subtask["id"])
    if existing is None:
        bus.insert_subtask(
            subtask["id"], subtask["swarm_id"], subtask["agent"],
            subtask["model"], subtask["prompt"], subtask.get("depends_on")
        )


def _run_subtask(subtask: dict, bus, runner: Callable) -> str:
    """Execute one subtask via runner; persist result to bus.
    Caller must ensure the subtask row exists in bus before calling this."""
    bus.update_subtask_status(subtask["id"], "running")
    result = runner(subtask["agent"], subtask["model"], subtask["prompt"])
    if result.startswith("[ERROR]"):
        bus.fail_subtask(subtask["id"])
    else:
        bus.complete_subtask(subtask["id"], result)
    return result


# ── Sequential ────────────────────────────────────────────────────────────────

def run_sequential(subtasks: List[dict], bus, runner: Callable = run_agent) -> List[dict]:
    """
    Run subtasks one-by-one. Each result is prepended to the next prompt.
    Returns list of {id, result, status} dicts.
    """
    # Pre-insert all subtasks on main thread so _run_subtask can assume rows exist
    for subtask in subtasks:
        _ensure_subtask_in_bus(subtask, bus)
    results = []
    prior_result = ""
    for subtask in subtasks:
        prompt = subtask["prompt"]
        if prior_result:
            prompt = f"Prior step result: {prior_result}\n\n{prompt}"
        enriched = {**subtask, "prompt": prompt}
        result = _run_subtask(enriched, bus, runner)
        prior_result = result
        results.append({"id": subtask["id"], "result": result,
                         "status": "complete" if not result.startswith("[ERROR]") else "failed"})
    return results


# ── Parallel ──────────────────────────────────────────────────────────────────

def run_parallel(subtasks: List[dict], bus, runner: Callable = run_agent,
                 synthesizer: Optional[Callable] = None) -> dict:
    """
    Fan-out: run all subtasks concurrently (max 3 workers).
    Fan-in: pass completed results to synthesizer.
    Returns {"synthesis": str, "subtask_results": list}.
    """
    # Pre-insert all subtasks on main thread so threads can assume rows exist
    for subtask in subtasks:
        _ensure_subtask_in_bus(subtask, bus)
    subtask_results = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        future_to_sub = {pool.submit(_run_subtask, sub, bus, runner): sub for sub in subtasks}
        for future in as_completed(future_to_sub):
            sub = future_to_sub[future]
            result = future.result()
            subtask_results.append({"id": sub["id"], "agent": sub["agent"], "result": result,
                                     "status": "complete" if not result.startswith("[ERROR]") else "failed"})

    completed = [r for r in subtask_results if r["status"] == "complete"]
    synthesis = synthesizer(completed) if synthesizer else "\n\n".join(
        f"## {r['agent']}\n{r['result']}" for r in completed
    )
    return {"synthesis": synthesis, "subtask_results": subtask_results}


# ── Debate ────────────────────────────────────────────────────────────────────

def run_debate(swarm_id: str, task: str, bus, runner: Callable = run_agent) -> str:
    """
    Three-subtask debate: POSITION_A (SCOUT), POSITION_B (AXIS), JUDGE (AXIS).
    Returns JUDGE's verdict string.
    """
    pos_a = {
        "id": f"{swarm_id}_debate_a",
        "swarm_id": swarm_id,
        "agent": "SCOUT",
        "model": get_agent("SCOUT").primary_model,
        "prompt": f"Argue in favor of the following proposition. Support your position with evidence and reasoning.\n\nProposition: {task}",
        "depends_on": None,
        "status": "pending",
        "result": None,
    }
    pos_b = {
        "id": f"{swarm_id}_debate_b",
        "swarm_id": swarm_id,
        "agent": "AXIS",
        "model": get_agent("AXIS").primary_model,
        "prompt": f"Argue against the following proposition. Support your position with evidence and reasoning.\n\nProposition: {task}",
        "depends_on": None,
        "status": "pending",
        "result": None,
    }

    # Persist subtask rows
    for sub in (pos_a, pos_b):
        bus.insert_subtask(sub["id"], sub["swarm_id"], sub["agent"],
                           sub["model"], sub["prompt"], sub["depends_on"])

    # Run positions in parallel
    results_map = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_run_subtask, sub, bus, runner): sub for sub in (pos_a, pos_b)}
        for future in as_completed(futures):
            sub = futures[future]
            results_map[sub["id"]] = future.result()

    a_result = results_map.get(pos_a["id"], "(position A unavailable)")
    b_result = results_map.get(pos_b["id"], "(position B unavailable)")

    judge_prompt = (
        f"You have two positions on this topic:\n\n"
        f"**Proposition:** {task}\n\n"
        f"**Position A (in favor):**\n{a_result}\n\n"
        f"**Position B (against):**\n{b_result}\n\n"
        f"Produce a compressed summary:\n"
        f"- Key points from Position A (2-3 bullets)\n"
        f"- Key points from Position B (2-3 bullets)\n"
        f"- Your verdict with reasoning (1-2 paragraphs)"
    )
    verdict = runner("JUDGE", get_agent("AXIS").primary_model, judge_prompt)
    return verdict


# ── Hierarchy ─────────────────────────────────────────────────────────────────

def run_hierarchy(swarm_id: str, task: str, bus, runner: Callable = run_agent) -> dict:
    """
    MANAGER runs first, produces JSON worker list.
    Workers are inserted into DB with index→ID translation, then run in parallel.
    Returns {"manager_result": str, "worker_results": list}.
    """
    manager_prompt = (
        "You are the MANAGER agent. Decompose the following task into worker subtasks. "
        "Return ONLY a JSON array of objects with keys: agent (string), prompt (string), "
        "depends_on (array of subtask indices, 0-based, or empty array if none). "
        f"Task: {task}"
    )
    manager_result = runner("MANAGER", get_agent("AXIS").primary_model, manager_prompt)

    # Parse MANAGER output
    worker_defs = []
    try:
        text = manager_result.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        worker_defs = json.loads(text)
        if not isinstance(worker_defs, list):
            worker_defs = []
    except (json.JSONDecodeError, ValueError):
        worker_defs = []

    if not worker_defs:
        # MANAGER failed — single fallback worker
        worker_defs = [{"agent": "SCOUT", "prompt": task, "depends_on": []}]

    # Insert worker subtasks with index→ID translation
    workers = []
    for idx, wdef in enumerate(worker_defs):
        worker_id = f"{swarm_id}_{idx}"
        agent = get_agent(wdef.get("agent", "SCOUT"), task_hint=wdef.get("prompt", task))
        # Translate 0-based dependency indices to full subtask IDs
        dep_indices = wdef.get("depends_on", []) or []
        dep_ids = ",".join(f"{swarm_id}_{i}" for i in dep_indices) or None
        prompt = wdef.get("prompt", task)
        bus.insert_subtask(worker_id, swarm_id, agent.codename, agent.primary_model, prompt, dep_ids)
        workers.append({
            "id": worker_id, "swarm_id": swarm_id, "agent": agent.codename,
            "model": agent.primary_model, "prompt": prompt, "depends_on": dep_ids,
            "status": "pending", "result": None,
        })

    # Run workers with dependency polling
    worker_results = []
    remaining = list(workers)
    dispatched = set()

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {}
        while remaining or futures:
            # Dispatch ready workers
            for w in list(remaining):
                dep_status = _deps_satisfied(w, bus)
                if dep_status == "failed":
                    bus.fail_subtask(w["id"])
                    remaining.remove(w)
                    worker_results.append({"id": w["id"], "result": "[SKIPPED: dependency failed]",
                                           "status": "failed"})
                elif dep_status is True and w["id"] not in dispatched:
                    futures[pool.submit(_run_subtask, w, bus, runner)] = w
                    dispatched.add(w["id"])
                    remaining.remove(w)
            # Collect completed
            done = [f for f in list(futures) if f.done()]
            for f in done:
                w = futures.pop(f)
                result = f.result()
                worker_results.append({"id": w["id"], "result": result,
                                        "status": "complete" if not result.startswith("[ERROR]") else "failed"})
            if remaining or futures:
                time.sleep(_DEP_POLL_INTERVAL)

    return {"manager_result": manager_result, "worker_results": worker_results}
