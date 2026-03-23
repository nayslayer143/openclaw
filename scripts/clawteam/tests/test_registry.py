"""Tests for registry.py — hardcoded AgentDef table."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clawteam.registry import get_agent, list_agents, AgentDef, AGENTS


def test_all_agents_present():
    codenames = {a.codename for a in AGENTS.values()}
    assert {"AXIS", "SCOUT", "FORGE", "VIGIL"} <= codenames


def test_agent_def_fields():
    for agent in AGENTS.values():
        assert agent.codename
        assert agent.primary_model
        assert agent.fast_model
        assert isinstance(agent.capabilities, list)
        assert len(agent.capabilities) > 0


def test_get_agent_known():
    agent = get_agent("SCOUT")
    assert agent.codename == "SCOUT"
    assert agent.primary_model == "qwen3:30b"


def test_get_agent_case_insensitive():
    agent = get_agent("scout")
    assert agent.codename == "SCOUT"


def test_get_agent_unknown_defaults_to_scout():
    agent = get_agent("UNKNOWN_BOT", task_hint="research competitors")
    assert agent.codename == "SCOUT"


def test_get_agent_unknown_defaults_to_forge_for_build():
    agent = get_agent("WHATEVER", task_hint="write code for the auth module")
    assert agent.codename == "FORGE"


def test_get_agent_unknown_defaults_to_axis_for_other():
    agent = get_agent("NOPE", task_hint="coordinate everything")
    assert agent.codename == "AXIS"


def test_list_agents_returns_all():
    agents = list_agents()
    assert len(agents) >= 4
