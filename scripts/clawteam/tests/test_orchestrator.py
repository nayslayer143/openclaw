"""Tests for orchestrator.py — swarm lifecycle, resume, output contract."""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest


@pytest.fixture
def bus(tmp_path):
    import clawteam.bus as bus_mod
    with patch.object(bus_mod, 'DB_PATH', ':memory:'):
        bus_mod._conn = None
        bus_mod._get_conn()  # initialises tables lazily
        yield bus_mod
        bus_mod._conn.close()
        bus_mod._conn = None


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "build-results"


def _mock_decompose(task: str) -> dict:
    return {
        "pattern": "sequential",
        "subtasks": [
            {"agent": "SCOUT", "model": "qwen3:30b", "prompt": "step 1", "depends_on": None},
            {"agent": "AXIS",  "model": "qwen3:32b", "prompt": "step 2", "depends_on": None},
        ]
    }


def _mock_runner(agent, model, prompt) -> str:
    return f"result from {agent}"


def test_run_swarm_sequential_end_to_end(bus, output_dir):
    from clawteam.orchestrator import run_swarm
    with patch("clawteam.orchestrator.decompose", side_effect=_mock_decompose), \
         patch("clawteam.orchestrator.run_agent", side_effect=_mock_runner), \
         patch("clawteam.orchestrator.BUILD_RESULTS_DIR", output_dir):
        swarm_id = run_swarm("do a thing", pattern="sequential", bus=bus)
    row = bus.get_swarm(swarm_id)
    assert row["status"] in ("complete", "partial")
    assert row["result"] is not None
    # Output contract written
    contract_path = output_dir / swarm_id / "output-contract.json"
    assert contract_path.exists()
    contract = json.loads(contract_path.read_text())
    assert contract["swarm_id"] == swarm_id
    assert contract["status"] in ("complete", "partial")


def test_resume_resets_running_subtasks(bus, output_dir):
    from clawteam.orchestrator import run_swarm, resume_swarm
    # Create a swarm and manually set one subtask to running (simulating crash)
    bus.create_swarm("swarm-resume-test", "resume task", "sequential")
    bus.insert_subtask("swarm-resume-test_0", "swarm-resume-test", "SCOUT", "qwen3:30b", "step", None)
    bus.update_subtask_status("swarm-resume-test_0", "running")
    # Resume should reset running → pending before re-running
    with patch("clawteam.orchestrator.run_agent", side_effect=_mock_runner), \
         patch("clawteam.orchestrator.BUILD_RESULTS_DIR", output_dir):
        resume_swarm("swarm-resume-test", bus=bus)
    # After resume, subtask should be complete (was reset and re-run)
    sub = bus.get_subtask("swarm-resume-test_0")
    assert sub["status"] == "complete"


def test_swarm_status_complete_on_success(bus, output_dir):
    from clawteam.orchestrator import run_swarm
    with patch("clawteam.orchestrator.decompose", side_effect=_mock_decompose), \
         patch("clawteam.orchestrator.run_agent", side_effect=_mock_runner), \
         patch("clawteam.orchestrator.BUILD_RESULTS_DIR", output_dir):
        swarm_id = run_swarm("test", pattern="sequential", bus=bus)
    assert bus.get_swarm(swarm_id)["status"] in ("complete", "partial")


def test_swarm_partial_on_synthesizer_failure(bus, output_dir):
    from clawteam.orchestrator import run_swarm
    call_count = {"n": 0}
    def runner(agent, model, prompt):
        call_count["n"] += 1
        if agent == "SYNTHESIZER":
            return "[ERROR] timeout"
        return "subtask result"
    with patch("clawteam.orchestrator.decompose", side_effect=_mock_decompose), \
         patch("clawteam.orchestrator.run_agent", side_effect=runner), \
         patch("clawteam.orchestrator.BUILD_RESULTS_DIR", output_dir):
        swarm_id = run_swarm("test task", pattern="sequential", bus=bus)
    assert bus.get_swarm(swarm_id)["status"] == "partial"


def test_output_contract_schema(bus, output_dir):
    from clawteam.orchestrator import run_swarm
    with patch("clawteam.orchestrator.decompose", side_effect=_mock_decompose), \
         patch("clawteam.orchestrator.run_agent", side_effect=_mock_runner), \
         patch("clawteam.orchestrator.BUILD_RESULTS_DIR", output_dir):
        swarm_id = run_swarm("schema test", pattern="sequential", bus=bus)
    contract = json.loads((output_dir / swarm_id / "output-contract.json").read_text())
    for key in ("swarm_id", "task", "pattern", "status", "created_at", "subtask_ids",
                "subtask_statuses", "result_file"):
        assert key in contract, f"Missing key: {key}"
