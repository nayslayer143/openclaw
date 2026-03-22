"""Tests for patterns.py — sequential, parallel, debate, hierarchy."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest


@pytest.fixture
def mock_bus(tmp_path):
    """Patch bus with an in-memory instance."""
    from unittest.mock import patch
    import clawteam.bus as bus_mod
    with patch.object(bus_mod, 'DB_PATH', ':memory:'):
        bus_mod._conn = None
        bus_mod._get_conn()  # initialises tables lazily
        yield bus_mod
        bus_mod._conn.close()
        bus_mod._conn = None


def _make_subtask(idx, swarm_id="swarm-test", agent="SCOUT",
                  model="qwen3:30b", prompt="do it", depends_on=None):
    return {
        "id": f"{swarm_id}_{idx}",
        "swarm_id": swarm_id,
        "agent": agent,
        "model": model,
        "prompt": prompt,
        "depends_on": depends_on,
        "status": "pending",
        "result": None,
    }


def test_deps_satisfied_no_deps(mock_bus):
    from clawteam.patterns import _deps_satisfied
    subtask = _make_subtask(0)
    assert _deps_satisfied(subtask, mock_bus) is True


def test_deps_satisfied_dep_complete(mock_bus):
    from clawteam.patterns import _deps_satisfied
    mock_bus.create_swarm("swarm-test", "task", "parallel")
    mock_bus.insert_subtask("swarm-test_0", "swarm-test", "SCOUT", "qwen3:30b", "first", None)
    mock_bus.complete_subtask("swarm-test_0", "done")
    subtask = _make_subtask(1, depends_on="swarm-test_0")
    assert _deps_satisfied(subtask, mock_bus) is True


def test_deps_satisfied_dep_pending_returns_false(mock_bus):
    from clawteam.patterns import _deps_satisfied
    mock_bus.create_swarm("swarm-test", "task", "sequential")
    mock_bus.insert_subtask("swarm-test_0", "swarm-test", "SCOUT", "qwen3:30b", "first", None)
    subtask = _make_subtask(1, depends_on="swarm-test_0")
    assert _deps_satisfied(subtask, mock_bus) is False


def test_deps_cascade_failed(mock_bus):
    from clawteam.patterns import _deps_satisfied
    mock_bus.create_swarm("swarm-test", "task", "sequential")
    mock_bus.insert_subtask("swarm-test_0", "swarm-test", "SCOUT", "qwen3:30b", "first", None)
    mock_bus.fail_subtask("swarm-test_0")
    subtask = _make_subtask(1, depends_on="swarm-test_0")
    # Should return "failed" sentinel, not True/False
    result = _deps_satisfied(subtask, mock_bus)
    assert result == "failed"


def test_sequential_pattern(mock_bus):
    from clawteam.patterns import run_sequential
    subtasks = [_make_subtask(i) for i in range(3)]
    call_log = []
    def mock_runner(agent, model, prompt):
        call_log.append(prompt)
        return f"result-{len(call_log)}"
    results = run_sequential(subtasks, mock_bus, runner=mock_runner)
    assert len(results) == 3
    # Prompt 2+ should include prior result
    assert "result-1" in call_log[1]
    assert "result-2" in call_log[2]


def test_parallel_pattern(mock_bus):
    from clawteam.patterns import run_parallel
    subtasks = [_make_subtask(i) for i in range(3)]
    def mock_runner(agent, model, prompt):
        return f"result-for-{agent}"
    with patch("clawteam.patterns.run_agent", side_effect=mock_runner):
        results = run_parallel(subtasks, mock_bus, runner=mock_runner, synthesizer=lambda x: "synth")
    assert results["synthesis"] == "synth"
    assert len(results["subtask_results"]) == 3


def test_debate_pattern_creates_three_subtasks(mock_bus):
    from clawteam.patterns import run_debate
    mock_bus.create_swarm("swarm-test", "is X good?", "debate")
    call_log = []
    def mock_runner(agent, model, prompt):
        call_log.append({"agent": agent, "prompt": prompt})
        return f"position from {agent}"
    result = run_debate("swarm-test", "is X good?", mock_bus, runner=mock_runner)
    agents_called = [c["agent"] for c in call_log]
    assert "SCOUT" in agents_called   # POSITION_A
    assert "AXIS" in agents_called    # POSITION_B and JUDGE
    assert result  # JUDGE result non-empty


def test_debate_position_prompts_contain_direction(mock_bus):
    from clawteam.patterns import run_debate
    mock_bus.create_swarm("swarm-test", "should we use React?", "debate")
    call_log = []
    def mock_runner(agent, model, prompt):
        call_log.append({"agent": agent, "prompt": prompt})
        return "my position"
    run_debate("swarm-test", "should we use React?", mock_bus, runner=mock_runner)
    prompts = [c["prompt"] for c in call_log]
    assert any("in favor" in p.lower() or "argue for" in p.lower() for p in prompts)
    assert any("against" in p.lower() for p in prompts)


def test_hierarchy_manager_then_workers(mock_bus):
    from clawteam.patterns import run_hierarchy
    import json
    mock_bus.create_swarm("swarm-test", "complex task", "hierarchy")
    manager_output = json.dumps([
        {"agent": "SCOUT", "prompt": "research part A", "depends_on": []},
        {"agent": "SCOUT", "prompt": "research part B", "depends_on": [0]},
    ])
    call_count = {"n": 0}
    def mock_runner(agent, model, prompt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return manager_output  # MANAGER call
        return "worker result"
    result = run_hierarchy("swarm-test", "complex task", mock_bus, runner=mock_runner)
    assert call_count["n"] == 3  # 1 manager + 2 workers
    # Worker subtasks should be in DB
    subtasks = mock_bus.list_subtasks("swarm-test")
    assert len(subtasks) >= 2
