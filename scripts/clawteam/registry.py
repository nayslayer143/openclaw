#!/usr/bin/env python3
"""
ClawTeam agent registry.
Hardcoded AgentDef table — source of truth is agents/configs/clawteam.md.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class AgentDef:
    codename: str
    role: str
    primary_model: str
    fast_model: str
    capabilities: List[str] = field(default_factory=list)


AGENTS: dict = {
    "AXIS": AgentDef(
        codename="AXIS",
        role="Chief orchestrator — coordination, synthesis, planning",
        primary_model="qwen3:32b",
        fast_model="qwen2.5:7b",
        capabilities=["orchestration", "synthesis", "planning"],
    ),
    "SCOUT": AgentDef(
        codename="SCOUT",
        role="Research agent — intel, analysis, competitive research",
        primary_model="qwen3:30b",
        fast_model="qwen2.5:7b",
        capabilities=["research", "intel", "analysis"],
    ),
    "FORGE": AgentDef(
        codename="FORGE",
        role="Build agent — code, debugging, technical implementation",
        primary_model="qwen3-coder-next",
        fast_model="devstral-small-2",
        capabilities=["code", "build", "debug"],
    ),
    "VIGIL": AgentDef(
        codename="VIGIL",
        role="Ops agent — monitoring, triage, system health",
        primary_model="qwen2.5:7b",
        fast_model="llama3.2:3b",
        capabilities=["ops", "monitoring", "triage"],
    ),
}

_RESEARCH_HINTS = ("research", "intel", "study", "analyze", "competitor", "market", "find")
_BUILD_HINTS    = ("code", "build", "write", "implement", "function", "script", "fix", "debug")


def get_agent(codename: str, task_hint: str = "") -> AgentDef:
    """Return AgentDef for codename (case-insensitive). Falls back by task_hint keywords."""
    upper = codename.upper()
    if upper in AGENTS:
        return AGENTS[upper]
    hint = task_hint.lower()
    if any(kw in hint for kw in _RESEARCH_HINTS):
        return AGENTS["SCOUT"]
    if any(kw in hint for kw in _BUILD_HINTS):
        return AGENTS["FORGE"]
    return AGENTS["AXIS"]


def list_agents() -> List[AgentDef]:
    return list(AGENTS.values())
